"""
research.py — Fast Light Research Agent
Fixes applied:
- V18: Deprecated Nitter proxy scraping requests to avoid 8s HTTP timeout hangs
"""
import httpx
import time
import json
import re
from agents.config import GITHUB_TOKEN
from agents.tracker import get_companies_to_research, mark_researched

GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
} if GITHUB_TOKEN else {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
}

ANGLE_TEMPLATES = {
    "yc":              "YC {batch} — building fast, scaling engineering team",
    "github_trending": "Repository trending on GitHub — active open-source engineering",
    "a16z":            "a16z-backed startup — high growth & scaling infrastructure",
    "india_curated":   "Top Indian tech startup — building core products",
    "wellfound":       "Actively hiring engineers — key engineering gap to fill",
    "producthunt":     "Recently launched product — early adopter & product feedback focus",
    "vc_portfolio":    "{funding}-backed startup — scaling product & tech stack",
    "default":         "Building in {tag} — interesting technical challenges",
}


def fetch_github_readme(github_org: str) -> str | None:
    """Fetch first paragraph/300 chars of main repo README via GitHub API."""
    if not github_org:
        return None
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
            lines = [l.strip() for l in decoded.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("![")]
            text = " ".join(lines)[:300]
            return text if len(text) > 20 else None
    except Exception:
        pass
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
    """Fast 2-layer research per company."""
    name = company["name"]
    domain = company.get("domain", "")
    github_org = company.get("github_org")

    desc = company.get("description") or f"{name} is building software products"
    suggested_angle = pick_angle_template(company)
    evidence_url = f"https://{domain}" if domain else (f"https://github.com/{github_org}" if github_org else "https://google.com")
    pain_point = desc

    if github_org:
        readme_text = fetch_github_readme(github_org)
        if readme_text:
            pain_point = f"Building: {readme_text}"
            evidence_url = f"https://github.com/{github_org}"

    return {
        "pain_point": pain_point,
        "evidence_url": evidence_url,
        "suggested_angle": suggested_angle
    }


def run(limit=45):
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
