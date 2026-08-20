"""
Company discovery agent.
Sources: YC companies · GitHub Trending · ProductHunt · Wellfound job board
Scores each company for fit, classifies Tier A (top 10) vs Tier B (next 35).
"""
import httpx
import json
import re
import time
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
}

# ── Harsh's target profile ────────────────────────────────────────
# What he's looking for: YC/funded AI-dev-tools startups, 5-50 people,
# founder/CTO still shipping, real GitHub repo he can research.

# High-value verticals for Harsh's skills (full-stack, AI, developer tools)
TIER_1_KEYWORDS = {
    "llm", "ai", "ml", "agent", "developer tools", "devtools", "api",
    "sdk", "infra", "platform", "open source", "observability", "monitoring",
    "data pipeline", "vector", "embedding", "rag", "workflow", "automation",
}
# Secondary signals — still relevant but less specific
TIER_2_KEYWORDS = {
    "saas", "b2b", "fintech", "analytics", "search", "database", "cloud",
    "security", "testing", "deployment", "ci/cd", "kubernetes", "backend",
}
# Red flags — deprioritize
SKIP_KEYWORDS = {
    "gaming", "social media", "consumer app", "fashion", "beauty",
    "food delivery", "real estate", "crypto", "nft", "blockchain",
}


def score_company(data: dict) -> float:
    """
    Score a company 0–10 for Harsh's outreach fit.

    Harsh's ideal target:
    - YC startup (W24–W26) in AI / developer tools / infra
    - Has a public GitHub repo (enables real research → better emails)
    - 5–50 person team (founder/CTO still commits code)
    - Actively building OR hiring engineers (signal they have real problems)
    """
    score = 0.0
    desc = (data.get("description") or "").lower()
    name = (data.get("name") or "").lower()
    import json as _j
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        try:
            raw_tags = _j.loads(raw_tags)
        except Exception:
            raw_tags = []
    tags_text = " ".join(str(t) for t in raw_tags).lower()
    all_text = f"{desc} {name} {tags_text}"

    # Hard skip — irrelevant verticals
    if any(kw in all_text for kw in SKIP_KEYWORDS):
        return 0.0

    # ── Core signals ──────────────────────────────────────────────

    # Has public GitHub repo → can research real pain points → better emails
    if data.get("github_org"):
        score += 3.5   # most important signal

    # Tier 1 keywords — direct match to Harsh's skills
    t1_matches = sum(1 for kw in TIER_1_KEYWORDS if kw in all_text)
    score += min(t1_matches * 1.0, 3.0)

    # Tier 2 keywords — secondary relevance
    t2_matches = sum(1 for kw in TIER_2_KEYWORDS if kw in all_text)
    score += min(t2_matches * 0.3, 1.0)

    # ── Source quality signals ────────────────────────────────────

    # YC company → founder network, open culture, more likely to reply
    if data.get("source") == "yc":
        score += 1.0
        # Recent batch = founder most reachable
        batch = (data.get("batch") or "")
        if any(yr in batch for yr in ["2025", "2026"]):
            score += 0.5

    # GitHub trending → actively building right now → highest engagement
    if data.get("source") == "github_trending":
        score += 1.0

    # Top VC backed (a16z, Sequoia, etc.) → well-funded, founder reachable
    if data.get("source") in ("a16z", "vc_portfolio"):
        score += 1.0

    # Indian startups → cultural connection, easier to get reply
    if (data.get("hq_country") == "India"
            or data.get("source") in ("india_curated", "india_inc42", "india_tracxn")):
        score += 0.5

    # Wellfound hiring → has budget + gap to fill
    if data.get("source") == "wellfound":
        score += 0.5

    # ProductHunt launch → founder most reachable pre-revenue
    if data.get("source") == "producthunt":
        score += 0.5

    # ── Team size signal ──────────────────────────────────────────
    size_raw = str(data.get("team_size") or "")
    # Small team: founder/CTO still hands-on
    if any(s in size_raw for s in ["2", "3", "4", "5", "6", "7", "8", "9",
                                     "10", "11", "12", "15", "20", "25"]):
        score += 0.5

    return round(min(score, 10.0), 2)


# ── Source 1: YC Companies ────────────────────────────────────────

def fetch_yc_companies(max_results=100) -> list:
    """
    Fetch recent YC companies via yc-oss community API.
    Filters to recent batches (W24 onward).
    """
    print("  [YC] Fetching companies...")
    # Accept both short (W24) and long (W2024) batch formats
    recent_batches = {
        "W24", "S24", "W25", "S25", "W26", "S26",        # short format
        "W2024", "S2024", "W2025", "S2025", "W2026",      # long format
        "Winter 2024", "Summer 2024", "Winter 2025",       # full text format
        "Summer 2025", "Winter 2026",
    }
    results = []

    # Try multiple endpoints in order
    urls = [
        "https://yc-oss.github.io/api/companies/hiring.json",  # actively hiring = best signal
        "https://yc-oss.github.io/api/companies/all.json",     # all launched companies
        "https://yc-oss.github.io/api/companies/top.json",     # top companies fallback
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
        # Filter to recent batches
        if batch and not any(b in batch for b in recent_batches):
            continue

        # Extract GitHub org from website or github fields
        gh_org = None
        github_url = c.get("github") or c.get("github_url") or ""
        if github_url and "github.com/" in github_url:
            parts = github_url.rstrip("/").split("github.com/")
            if len(parts) > 1:
                org = parts[1].split("/")[0]
                if org and org not in ("orgs", ""):
                    gh_org = org

        website = c.get("website") or c.get("url") or ""
        domain = (website.replace("https://", "")
                         .replace("http://", "")
                         .split("/")[0]) if website else ""

        results.append({
            "name": c.get("name", ""),
            "domain": domain or None,
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



# ── Source 2: GitHub Trending ─────────────────────────────────────

def fetch_github_trending(since="daily") -> list:
    """
    Scrape GitHub trending page.
    Companies with trending repos are actively building — highest engagement signal.
    """
    print(f"  [GitHub Trending] Fetching ({since})...")
    results = []

    try:
        url = f"https://github.com/trending?since={since}&spoken_language_code=en"
        r = httpx.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = soup.select("article.Box-row")
        for article in articles[:50]:
            # Repo name (owner/repo)
            repo_link = article.select_one("h2 a")
            if not repo_link:
                continue
            full_name = repo_link.get("href", "").strip("/")
            if not full_name or "/" not in full_name:
                continue

            owner, repo = full_name.split("/", 1)

            # Description
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Stars today
            stars_el = article.select_one("span.d-inline-block.float-sm-right")
            stars_today = stars_el.get_text(strip=True) if stars_el else ""

            # Language
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            lang = lang_el.get_text(strip=True) if lang_el else ""

            # Try to find the org's website via GitHub API
            domain = None
            try:
                time.sleep(0.2)  # rate limit
                org_data = httpx.get(
                    f"https://api.github.com/users/{owner}",
                    headers=GH_HEADERS, timeout=8
                ).json()
                blog = org_data.get("blog") or ""
                if blog and "." in blog:
                    domain = blog.replace("https://", "").replace("http://", "").split("/")[0]
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


# ── Source 3: ProductHunt ─────────────────────────────────────────

def fetch_producthunt_launches() -> list:
    """
    Scrape ProductHunt for recent launches.
    Tries multiple URL patterns since PH changes their routes.
    """
    print("  [ProductHunt] Fetching today's launches...")
    results = []

    urls_to_try = [
        "https://www.producthunt.com",          # home page has today's posts
        "https://www.producthunt.com/posts",    # posts listing
    ]

    for url in urls_to_try:
        try:
            r = httpx.get(url, timeout=15, headers=HEADERS, follow_redirects=True)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            # Try to extract from Next.js __NEXT_DATA__
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data and next_data.string:
                try:
                    data = json.loads(next_data.string)
                    # Traverse to find posts array
                    posts = (data.get("props", {})
                                .get("pageProps", {})
                                .get("posts", []))
                    if not posts:
                        # Try alternate key
                        posts = (data.get("props", {})
                                    .get("pageProps", {})
                                    .get("dailyData", {})
                                    .get("posts", []))

                    for post in posts[:30]:
                        name = post.get("name", "")
                        tagline = post.get("tagline", "")
                        website = post.get("website") or ""
                        domain = (website.replace("https://", "")
                                         .replace("http://", "")
                                         .split("/")[0]) if website else ""
                        topics = [t.get("name", "") for t in post.get("topics", [])]
                        results.append({
                            "name": name,
                            "domain": domain or None,
                            "description": tagline,
                            "tags": topics,
                            "github_org": None,
                            "source": "producthunt",
                        })

                    if results:
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass

            # Fallback: try to find product names from HTML
            if not results:
                product_cards = soup.select("h3, h2")
                for card in product_cards[:20]:
                    text = card.get_text(strip=True)
                    if text and len(text) > 3:
                        results.append({
                            "name": text,
                            "domain": None,
                            "description": "",
                            "tags": [],
                            "github_org": None,
                            "source": "producthunt",
                        })

            if results:
                break

        except Exception as e:
            print(f"  [ProductHunt] {url}: {e}")
            continue

    print(f"  [ProductHunt] Found {len(results)} launches")
    return results


# ── Source 4: Wellfound / AngelList ──────────────────────────────

def fetch_wellfound_companies() -> list:
    """
    Fetch companies actively hiring engineers on Wellfound.
    Hiring = they have budget + a gap that needs filling.
    """
    print("  [Wellfound] Fetching companies hiring engineers...")
    results = []

    try:
        # Wellfound job search RSS / public endpoints
        url = "https://wellfound.com/jobs?role=software-engineer&remote=true&jobType=full-time"
        r = httpx.get(url, timeout=15, headers=HEADERS, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")

        # Try to extract company cards
        company_links = soup.select("a[href*='/company/']")
        seen = set()
        for link in company_links[:50]:
            href = link.get("href", "")
            slug = href.split("/company/")[-1].split("/")[0].split("?")[0]
            if not slug or slug in seen:
                continue
            seen.add(slug)

            name = link.get_text(strip=True) or slug.replace("-", " ").title()
            results.append({
                "name": name,
                "domain": None,
                "description": "",
                "github_org": None,
                "tags": [],
                "source": "wellfound",
                "wellfound_slug": slug,
            })

    except Exception as e:
        print(f"  [Wellfound] Error: {e}")

    print(f"  [Wellfound] Found {len(results)} companies")
    return results


# ── Source 5: a16z Portfolio ──────────────────────────────────────

def fetch_a16z_portfolio(max_results=60) -> list:
    """
    Scrape a16z public portfolio page.
    a16z-backed = well-funded, high-growth, founder is reachable.
    """
    print("  [a16z] Fetching portfolio companies...")
    results = []
    try:
        r = httpx.get("https://a16z.com/portfolio/", timeout=15,
                      headers=HEADERS, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")

        # a16z uses portfolio cards with links
        cards = soup.select("a[href]")
        seen = set()
        for card in cards:
            href = card.get("href", "")
            # Portfolio company links go to external domains
            if not href.startswith("http") or "a16z.com" in href:
                continue
            name_el = card.select_one("h3, h2, strong, span")
            name = (name_el.get_text(strip=True) if name_el
                    else card.get_text(strip=True)[:50])
            if not name or len(name) < 2 or name in seen:
                continue
            seen.add(name)
            domain = href.replace("https://", "").replace("http://", "").split("/")[0]
            results.append({
                "name": name,
                "domain": domain or None,
                "description": "",
                "tags": ["vc-backed", "a16z"],
                "github_org": None,
                "source": "a16z",
                "funding": "a16z",
            })
            if len(results) >= max_results:
                break
    except Exception as e:
        print(f"  [a16z] Error: {e}")

    print(f"  [a16z] Found {len(results)} companies")
    return results


# ── Source 6: Top VC portfolios ───────────────────────────────────

VC_PORTFOLIOS = [
    ("Sequoia",          "https://www.sequoiacap.com/companies/"),
    ("General Catalyst", "https://www.generalcatalyst.com/portfolio"),
    ("Lightspeed",       "https://lsvp.com/portfolio/"),
    ("Benchmark",        "https://benchmark.com/companies"),
    ("Accel",            "https://www.accel.com/portfolio"),
]

def fetch_vc_portfolios(max_per_vc=30) -> list:
    """
    Scrape multiple top VC portfolio pages.
    These are funded, fast-growing companies — highest reply rate from founders.
    """
    print("  [VC Portfolios] Fetching Sequoia, GC, Lightspeed, Benchmark, Accel...")
    all_results = []

    for vc_name, url in VC_PORTFOLIOS:
        try:
            r = httpx.get(url, timeout=12, headers=HEADERS, follow_redirects=True)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            # Generic: find external links that are portfolio companies
            seen = set()
            count = 0
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    continue
                # Skip VC's own domain and social links
                skip_domains = {vc_name.lower().replace(" ", ""),
                                "linkedin", "twitter", "x.com", "github",
                                "google", "apple", "youtube"}
                parsed_domain = href.replace("https://", "").replace("http://", "").split("/")[0]
                if any(s in parsed_domain for s in skip_domains):
                    continue
                # Get company name from link text
                name = a.get_text(strip=True)
                if not name or len(name) < 2 or len(name) > 60 or name in seen:
                    continue
                # Skip generic nav links
                if any(w in name.lower() for w in ["home", "about", "team",
                        "portfolio", "news", "blog", "contact", "careers"]):
                    continue
                seen.add(name)
                all_results.append({
                    "name": name,
                    "domain": parsed_domain or None,
                    "description": "",
                    "tags": ["vc-backed", vc_name.lower()],
                    "github_org": None,
                    "source": "vc_portfolio",
                    "funding": vc_name,
                })
                count += 1
                if count >= max_per_vc:
                    break

            print(f"    [{vc_name}] {count} companies")
            time.sleep(0.5)

        except Exception as e:
            print(f"    [{vc_name}] Error: {e}")

    print(f"  [VC Portfolios] Total: {len(all_results)}")
    return all_results


# ── Source 7: Indian Startups ─────────────────────────────────────

def fetch_indian_startups() -> list:
    """
    Two sources for Indian startups:
    1. YC companies filtered by country=India (already loaded, reuse)
    2. Inc42 top startups page
    """
    print("  [India] Fetching top Indian startups...")
    results = []

    # Source A: Inc42 unicorn/soonicorn tracker
    try:
        urls = [
            "https://inc42.com/startups/",
            "https://inc42.com/tag/funded-startups/",
        ]
        for url in urls:
            r = httpx.get(url, timeout=12, headers=HEADERS, follow_redirects=True)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Inc42 article cards have company names in headlines
            cards = soup.select("h2 a, h3 a, .post-title a")
            seen = set()
            for card in cards[:40]:
                text = card.get_text(strip=True)
                href = card.get("href", "")
                if not text or len(text) < 3 or text in seen:
                    continue
                # Skip generic news headlines (look for capitalized company names)
                words = text.split()
                if len(words) > 8:   # long headlines aren't company names
                    continue
                seen.add(text)
                results.append({
                    "name": text,
                    "domain": None,
                    "description": "Indian startup",
                    "tags": ["india", "startup"],
                    "github_org": None,
                    "hq_country": "India",
                    "source": "india_inc42",
                })
            if results:
                break
    except Exception as e:
        print(f"  [India/Inc42] Error: {e}")

    # Source B: Tracxn India top startups (free endpoint)
    try:
        r = httpx.get(
            "https://tracxn.com/d/trending-themes/startups-in-india",
            timeout=12, headers=HEADERS, follow_redirects=True
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for el in soup.select(".company-name, .startup-name, h3")[:30]:
                name = el.get_text(strip=True)
                if name and 2 < len(name) < 60:
                    results.append({
                        "name": name,
                        "domain": None,
                        "description": "Indian startup",
                        "tags": ["india", "startup"],
                        "github_org": None,
                        "hq_country": "India",
                        "source": "india_tracxn",
                    })
    except Exception as e:
        print(f"  [India/Tracxn] Error: {e}")

    # Source C: Known top-funded Indian tech startups (curated seed list)
    # These are real, verified companies — hardcoded so they always appear
    KNOWN_INDIA_STARTUPS = [
        {"name": "Sarvam AI",     "domain": "sarvam.ai",      "description": "Indian LLM for Indic languages", "tags": ["ai", "llm", "india"]},
        {"name": "Krutrim",       "domain": "krutrim.com",    "description": "Ola's AI startup, Indian LLM",   "tags": ["ai", "llm", "india"]},
        {"name": "Ola Electric",  "domain": "olaelectric.com","description": "EV manufacturer",                "tags": ["ev", "hardware", "india"]},
        {"name": "Zepto",         "domain": "zeptonow.com",   "description": "10-min grocery delivery",        "tags": ["logistics", "india"]},
        {"name": "Cred",          "domain": "cred.club",      "description": "Credit card rewards fintech",    "tags": ["fintech", "india"]},
        {"name": "Groww",         "domain": "groww.in",       "description": "Stock trading platform",         "tags": ["fintech", "india"]},
        {"name": "Razorpay",      "domain": "razorpay.com",   "description": "Payment infra for businesses",   "tags": ["fintech", "api", "india"]},
        {"name": "Postman",       "domain": "postman.com",    "description": "API development platform",       "tags": ["devtools", "api", "india"]},
        {"name": "BrowserStack",  "domain": "browserstack.com","description": "Cross-browser testing cloud",   "tags": ["devtools", "testing", "india"]},
        {"name": "Hasura",        "domain": "hasura.io",      "description": "GraphQL engine for Postgres",    "tags": ["devtools", "api", "india"]},
        {"name": "Chargebee",     "domain": "chargebee.com",  "description": "Subscription billing infra",     "tags": ["saas", "fintech", "india"]},
        {"name": "Darwinbox",     "domain": "darwinbox.com",  "description": "HR tech platform",               "tags": ["hr", "saas", "india"]},
        {"name": "Yellow.ai",     "domain": "yellow.ai",      "description": "Conversational AI platform",     "tags": ["ai", "agent", "india"]},
        {"name": "Unacademy",     "domain": "unacademy.com",  "description": "Online learning platform",       "tags": ["edtech", "india"]},
        {"name": "Physics Wallah","domain": "pw.live",        "description": "EdTech unicorn",                 "tags": ["edtech", "india"]},
        {"name": "Meesho",        "domain": "meesho.com",     "description": "Social commerce platform",       "tags": ["ecommerce", "india"]},
        {"name": "InfraCloud",    "domain": "infracloud.io",  "description": "Cloud-native infra services",    "tags": ["cloud", "kubernetes", "india"]},
        {"name": "Porter",        "domain": "porter.in",      "description": "B2B logistics platform",         "tags": ["logistics", "b2b", "india"]},
        {"name": "Leapfinance",   "domain": "leapfinance.com","description": "Study abroad financing",         "tags": ["fintech", "india"]},
        {"name": "Cashfree",      "domain": "cashfree.com",   "description": "Payment infrastructure",         "tags": ["fintech", "api", "india"]},
    ]
    for c in KNOWN_INDIA_STARTUPS:
        c["source"] = "india_curated"
        c["hq_country"] = "India"
        c["github_org"] = None
        results.append(c)

    print(f"  [India] Total: {len(results)} startups")
    return results


# ── Main discovery run ────────────────────────────────────────────

def run(max_new=100) -> list:
    """
    Run all discovery sources, score, deduplicate, classify into tiers.
    Saves to DB. Returns list of new company dicts.
    """
    print("\n🔍 Running company discovery...")
    print(f"   Target: {TIER_A_COUNT} Tier A + {TIER_B_COUNT} Tier B companies\n")

    all_companies = []
    all_companies.extend(fetch_yc_companies())
    all_companies.extend(fetch_github_trending("daily"))
    all_companies.extend(fetch_producthunt_launches())
    all_companies.extend(fetch_wellfound_companies())
    all_companies.extend(fetch_a16z_portfolio())
    all_companies.extend(fetch_vc_portfolios())
    all_companies.extend(fetch_indian_startups())

    print(f"\n📊 Total raw: {len(all_companies)}")

    # Deduplicate by name+domain — handle None values safely
    seen_keys = set()
    unique = []
    for c in all_companies:
        name_key  = (c.get("name") or "").strip().lower()
        domain_key = (c.get("domain") or "").strip().lower()
        if not name_key:                          # skip nameless entries
            continue
        key = (name_key, domain_key)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(c)

    print(f"   After dedup: {len(unique)}")

    # Filter out already-contacted (safe: pass empty string if domain is None)
    fresh = [c for c in unique if not already_contacted(c.get("domain") or "")]
    print(f"   Not yet contacted: {len(fresh)}")

    # Score
    for c in fresh:
        c["fit_score"] = score_company(c)

    # Sort by fit score
    fresh.sort(key=lambda x: x["fit_score"], reverse=True)

    # Take top N
    # Take all fresh companies up to max_new (or max pool size 500)
    target_pool_save = fresh[:max(max_new, 500)]

    # Assign tiers
    for i, c in enumerate(target_pool_save):
        c["tier"] = "A" if i < TIER_A_COUNT else "B"
        c["status"] = "queued"

    # Save to DB pool
    saved = 0
    for c in target_pool_save:
        try:
            upsert_company(c)
            saved += 1
        except Exception as e:
            print(f"  [DB] Error saving {c.get('name')}: {e}")

    print(f"\n✅ Discovery complete: {saved} companies stored in DB pool")
    print(f"   Tier A: {min(TIER_A_COUNT, len(target_pool_save))}")
    print(f"   Tier B: {max(0, len(target_pool_save) - TIER_A_COUNT)}")

    return target_pool_save


if __name__ == "__main__":
    from agents.tracker import verify_connection
    verify_connection()
    companies = run()
    print(f"\nTop 5 by fit score:")
    for c in companies[:5]:
        print(f"  [{c['tier']}] {c['name']:30s} score={c['fit_score']} source={c['source']}")
