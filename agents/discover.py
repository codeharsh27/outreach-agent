"""
discover.py — Hardened Company Discovery Agent
Fixes applied:
- V4: urllib.parse URL scheme validation (prevents file:// / javascript: URI bugs)
- V17: GITHUB_TOKEN status check to prevent unauthenticated 60 req/hr rate limits
- V19: Multi-selector fallback for ProductHunt scraping
"""
import httpx
import json
import re
import time
from urllib.parse import urlparse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from agents.config import GITHUB_TOKEN, TIER_A_COUNT, TIER_B_COUNT
from agents.tracker import upsert_company, already_contacted

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
} if GITHUB_TOKEN else {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
}

TIER_1_KEYWORDS = {
    "llm", "ai", "ml", "agent", "developer tools", "devtools", "api",
    "sdk", "infra", "platform", "open source", "observability", "monitoring",
    "data pipeline", "vector", "embedding", "rag", "workflow", "automation",
}
TIER_2_KEYWORDS = {
    "saas", "b2b", "fintech", "analytics", "search", "database", "cloud",
    "security", "testing", "deployment", "ci/cd", "kubernetes", "backend",
}
SKIP_KEYWORDS = {
    "gaming", "social media", "consumer app", "fashion", "beauty",
    "food delivery", "real estate", "crypto", "nft", "blockchain",
}


def clean_domain(url_or_domain: str) -> str | None:
    """Fix V4: Safe URL scheme parsing via urllib.parse to prevent malicious URI execution."""
    if not url_or_domain:
        return None
    url = url_or_domain.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        netloc = parsed.netloc.split(":")[0].lower()
        if "." in netloc and not netloc.startswith("."):
            return netloc
    except Exception:
        pass
    return None


def score_company(data: dict) -> float:
    score = 0.0
    desc = (data.get("description") or "").lower()
    name = (data.get("name") or "").lower()
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except Exception:
            raw_tags = []
    tags_text = " ".join(str(t) for t in raw_tags).lower()
    all_text = f"{desc} {name} {tags_text}"

    if any(kw in all_text for kw in SKIP_KEYWORDS):
        return 0.0

    if data.get("github_org"):
        score += 3.5

    t1_matches = sum(1 for kw in TIER_1_KEYWORDS if kw in all_text)
    score += min(t1_matches * 1.0, 3.0)

    t2_matches = sum(1 for kw in TIER_2_KEYWORDS if kw in all_text)
    score += min(t2_matches * 0.3, 1.0)

    if data.get("source") == "yc":
        score += 1.0
        batch = (data.get("batch") or "")
        if any(yr in batch for yr in ["2025", "2026"]):
            score += 0.5

    if data.get("source") == "github_trending":
        score += 1.0

    if data.get("source") in ("a16z", "vc_portfolio"):
        score += 1.0

    if data.get("hq_country") == "India" or data.get("source") in ("india_curated", "india_inc42", "india_tracxn"):
        score += 0.5

    if data.get("source") == "wellfound":
        score += 0.5

    if data.get("source") == "producthunt":
        score += 0.5

    size_raw = str(data.get("team_size") or "")
    if any(s in size_raw for s in ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "15", "20", "25"]):
        score += 0.5

    return round(min(score, 10.0), 2)


def fetch_yc_companies(max_results=100) -> list:
    print("  [YC] Fetching companies...")
    recent_batches = {
        "W24", "S24", "W25", "S25", "W26", "S26",
        "W2024", "S2024", "W2025", "S2025", "W2026",
        "Winter 2024", "Summer 2024", "Winter 2025",
        "Summer 2025", "Winter 2026",
    }
    results = []

    urls = [
        "https://yc-oss.github.io/api/companies/hiring.json",
        "https://yc-oss.github.io/api/companies/all.json",
        "https://yc-oss.github.io/api/companies/top.json",
    ]

    companies = []
    for url in urls:
        try:
            r = httpx.get(url, timeout=15, headers=HEADERS)
            r.raise_for_status()
            companies = r.json()
            print(f"  [YC] Loaded {len(companies)} companies from {url.split('/')[-1]}")
            break
        except Exception as e:
            print(f"  [YC] {url.split('/')[-1]} failed: {e}")
            continue

    for c in companies:
        batch = c.get("batch", "")
        if batch and not any(b in batch for b in recent_batches):
            continue

        gh_org = None
        github_url = c.get("github") or c.get("github_url") or ""
        if github_url and "github.com/" in github_url:
            parts = github_url.rstrip("/").split("github.com/")
            if len(parts) > 1:
                org = parts[1].split("/")[0]
                if org and org not in ("orgs", ""):
                    gh_org = org

        domain = clean_domain(c.get("website") or c.get("url") or "")

        results.append({
            "name": c.get("name", ""),
            "domain": domain,
            "description": c.get("one_liner") or c.get("description", ""),
            "tags": c.get("tags", []),
            "github_org": gh_org,
            "hq_country": c.get("country", ""),
            "source": "yc",
            "batch": batch,
            "team_size": c.get("team_size", ""),
        })

        if len(results) >= max_results:
            break

    print(f"  [YC] Found {len(results)} recent companies")
    return results


def fetch_github_trending(since="daily") -> list:
    """Fix V17: Authenticated & rate-limit check for GitHub API requests."""
    print(f"  [GitHub Trending] Fetching ({since})...")
    results = []

    try:
        url = f"https://github.com/trending?since={since}&spoken_language_code=en"
        r = httpx.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = soup.select("article.Box-row")
        for article in articles[:50]:
            repo_link = article.select_one("h2 a")
            if not repo_link:
                continue
            full_name = repo_link.get("href", "").strip("/")
            if not full_name or "/" not in full_name:
                continue

            owner, repo = full_name.split("/", 1)
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            stars_el = article.select_one("span.d-inline-block.float-sm-right")
            stars_today = stars_el.get_text(strip=True) if stars_el else ""

            lang_el = article.select_one("[itemprop='programmingLanguage']")
            lang = lang_el.get_text(strip=True) if lang_el else ""

            domain = None
            if GITHUB_TOKEN:
                try:
                    time.sleep(0.2)
                    org_data = httpx.get(
                        f"https://api.github.com/users/{owner}",
                        headers=GH_HEADERS, timeout=8
                    ).json()
                    blog = org_data.get("blog") or ""
                    domain = clean_domain(blog)
                except Exception:
                    pass

            results.append({
                "name": owner,
                "domain": domain or f"{owner}.com",
                "description": description,
                "github_org": owner,
                "tags": [lang] if lang else [],
                "source": "github_trending",
                "trending_repo": repo,
                "stars_today": stars_today,
            })

    except Exception as e:
        print(f"  [GitHub Trending] Error: {e}")

    print(f"  [GitHub Trending] Found {len(results)} repos")
    return results


def fetch_producthunt_launches() -> list:
    """Fix V19: Robust ProductHunt scraper with multiple DOM fallbacks."""
    print("  [ProductHunt] Fetching today's launches...")
    results = []

    try:
        url = "https://www.producthunt.com"
        r = httpx.get(url, timeout=15, headers=HEADERS, follow_redirects=True)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data and next_data.string:
                try:
                    data = json.loads(next_data.string)
                    posts = (data.get("props", {}).get("pageProps", {}).get("posts", []))
                    if not posts:
                        posts = (data.get("props", {}).get("pageProps", {}).get("dailyData", {}).get("posts", []))

                    for post in posts[:30]:
                        name = post.get("name", "")
                        tagline = post.get("tagline", "")
                        domain = clean_domain(post.get("website") or "")
                        topics = [t.get("name", "") for t in post.get("topics", [])]
                        results.append({
                            "name": name,
                            "domain": domain,
                            "description": tagline,
                            "tags": topics,
                            "github_org": None,
                            "source": "producthunt",
                        })
                except Exception:
                    pass

            if not results:
                for card in soup.select("a[href^='/posts/']")[:25]:
                    name = card.get_text(strip=True)
                    if name and len(name) > 2:
                        results.append({
                            "name": name[:50],
                            "domain": None,
                            "description": "ProductHunt launch",
                            "tags": [],
                            "github_org": None,
                            "source": "producthunt",
                        })
    except Exception as e:
        print(f"  [ProductHunt] Error: {e}")

    print(f"  [ProductHunt] Found {len(results)} launches")
    return results


def run(max_new=100) -> list:
    print("\n🔍 Running company discovery...")
    print(f"   Target: {TIER_A_COUNT} Tier A + {TIER_B_COUNT} Tier B companies\n")

    all_companies = []
    all_companies.extend(fetch_yc_companies())
    all_companies.extend(fetch_github_trending("daily"))
    all_companies.extend(fetch_producthunt_launches())

    print(f"\n📊 Total raw: {len(all_companies)}")

    seen_keys = set()
    unique = []
    for c in all_companies:
        name_key   = (c.get("name") or "").strip().lower()
        domain_key = (c.get("domain") or "").strip().lower()
        if not name_key:
            continue
        key = (name_key, domain_key)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(c)

    fresh = [c for c in unique if not already_contacted(c.get("domain") or "")]
    print(f"   Not yet contacted: {len(fresh)}")

    for c in fresh:
        c["fit_score"] = score_company(c)

    fresh.sort(key=lambda x: x["fit_score"], reverse=True)
    target_pool_save = fresh[:max(max_new, 500)]

    for i, c in enumerate(target_pool_save):
        c["tier"] = "A" if i < TIER_A_COUNT else "B"
        c["status"] = "queued"

    saved = 0
    for c in target_pool_save:
        try:
            upsert_company(c)
            saved += 1
        except Exception as e:
            print(f"  [DB] Error saving {c.get('name')}: {e}")

    print(f"\n✅ Discovery complete: {saved} companies stored in DB pool")
    return target_pool_save


if __name__ == "__main__":
    from agents.tracker import verify_connection
    verify_connection()
    companies = run()
