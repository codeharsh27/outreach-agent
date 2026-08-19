"""
Fast 3-Layer Light Research Agent.
Eliminates slow Ollama & issue-scraping bottlenecks.
Layer 1: Description + tags template angle (0s, instant)
Layer 2: GitHub README first 300 chars (1 API call, ~1s) if available
Layer 3: Founder's recent tweet via Nitter (~1s) if Twitter handle available
"""
import httpx
import time
import json
import re
from bs4 import BeautifulSoup
from agents.config import GITHUB_TOKEN
from agents.tracker import get_companies_to_research, mark_researched

GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
}
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

ANGLE_TEMPLATES = {
    "yc":              "YC {batch} — building fast, scaling engineering team",
    "github_trending": "Repository trending on GitHub — active open-source engineering",
    "a16z":            "a16z-backed startup — high growth & scaling infrastructure",
    "india_curated":   "Top Indian tech startup — building core products",
    "india_inc42":     "Fast-growing Indian tech startup",
    "india_tracxn":    "Trending Indian tech startup",
    "wellfound":       "Actively hiring engineers — key engineering gap to fill",
    "producthunt":     "Recently launched product — early adopter & product feedback focus",
    "vc_portfolio":    "{funding}-backed startup — scaling product & tech stack",
    "default":         "Building in {tag} — interesting technical challenges",
}


def fetch_github_readme(github_org: str) -> str | None:
    """Fetch first paragraph/300 chars of main repo README via GitHub API."""
    try:
        url = f"https://api.github.com/orgs/{github_org}/repos?sort=updated&per_page=1"
        r = httpx.get(url, headers=GH_HEADERS, timeout=5)
        if r.status_code != 200:
            url = f"https://api.github.com/users/{github_org}/repos?sort=updated&per_page=1"
            r = httpx.get(url, headers=GH_HEADERS, timeout=5)
        repos = r.json()
        if not isinstance(repos, list) or not repos:
            return None

        repo_name = repos[0].get("full_name", "")
        readme_url = f"https://api.github.com/repos/{repo_name}/readme"
        rr = httpx.get(readme_url, headers=GH_HEADERS, timeout=5)
        if rr.status_code == 200:
            import base64
            content = rr.json().get("content", "")
            decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
            # Strip markdown headers/badges
            lines = [l.strip() for l in decoded.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("![")]
            text = " ".join(lines)[:300]
            return text if len(text) > 20 else None
    except Exception:
        pass
    return None


def fetch_last_tweet(twitter_url: str) -> dict | None:
    """Fetch recent tweet via Nitter proxy."""
    if not twitter_url:
        return None
    handle = twitter_url.replace("https://x.com/", "").replace("https://twitter.com/", "").strip("/").split("/")[0]
    if not handle:
        return None

    nitter_instances = ["https://nitter.net", "https://nitter.privacydev.net"]
    for instance in nitter_instances:
        try:
            r = httpx.get(f"{instance}/{handle}", timeout=4, headers=HTTP_HEADERS)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                tweets = soup.select(".tweet-content")
                links = soup.select(".tweet-link")
                if tweets and links:
                    text = tweets[0].get_text(strip=True)
                    tweet_path = links[0].get("href", "")
                    return {"text": text[:280], "url": f"https://x.com{tweet_path}"}
        except Exception:
            continue
    return None


def pick_angle_template(company: dict) -> str:
    source = company.get("source", "default")
    batch = company.get("batch") or "recent batch"
    funding = company.get("funding") or "top VC"
    
    tags = company.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    tag = tags[0] if tags else "tech"

    template = ANGLE_TEMPLATES.get(source, ANGLE_TEMPLATES["default"])
    return template.format(batch=batch, funding=funding, tag=tag)


def light_research(company: dict) -> dict:
    """Fast 3-layer research per company (< 2 seconds total)."""
    name = company["name"]
    domain = company.get("domain", "")
    github_org = company.get("github_org")
    twitter_url = company.get("twitter_url")

    # Layer 1: Base description & template angle (0s)
    desc = company.get("description") or f"{name} is building software products"
    suggested_angle = pick_angle_template(company)
    evidence_url = f"https://{domain}" if domain else (f"https://github.com/{github_org}" if github_org else "https://google.com")
    pain_point = desc

    # Layer 2: GitHub README (1s)
    if github_org:
        readme_text = fetch_github_readme(github_org)
        if readme_text:
            pain_point = f"Building: {readme_text}"
            evidence_url = f"https://github.com/{github_org}"

    # Layer 3: Recent Tweet (1s)
    if twitter_url:
        tweet = fetch_last_tweet(twitter_url)
        if tweet and tweet.get("text"):
            pain_point = f"Recent update: {tweet['text']}"
            evidence_url = tweet["url"]

    return {
        "pain_point": pain_point,
        "evidence_url": evidence_url,
        "suggested_angle": suggested_angle
    }


def run(limit=45):
    """Run fast light research for all queued companies in DB."""
    print("\n🔬 Running fast light-research agent...")
    companies = get_companies_to_research(limit=limit)
    print(f"   {len(companies)} companies queued for research\n")

    for company in companies:
        company = dict(company)
        try:
            result = light_research(company)
            mark_researched(
                company_id=company["id"],
                pain_point=result["pain_point"],
                evidence_url=result["evidence_url"],
                suggested_angle=result["suggested_angle"],
                tier=company.get("tier", "B"),
            )
            print(f"    ⚡ {company['name']}: {result['pain_point'][:60]}...")
        except Exception as e:
            print(f"    ❌ {company['name']}: {e}")

    print(f"\n✅ Light research complete for {len(companies)} companies")


if __name__ == "__main__":
    run()
