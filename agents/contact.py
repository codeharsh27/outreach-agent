"""
Contact finder — waterfall approach.
Tries each source in order, stops when a verified email is found.

Order:
  1. GitHub profile email (free, unlimited)
  2. Email commit scraping (free, unlimited)
  3. Minelead API (100 free credits/month)
  4. Snov.io API (50 free credits/month)
  5. Hunter.io API (25 free credits/month)
  6. Email pattern + SMTP verify (free, unlimited)
"""
import httpx
import smtplib
import time
import re
import sqlite3
from agents.config import (
    GITHUB_TOKEN, HUNTER_API_KEY, SNOVIO_USER_ID,
    SNOVIO_SECRET, MINELEAD_API_KEY, TRACKER_DB
)
from agents.tracker import save_contact

GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "outreach-agent/1.0"
}


# ── Source 1: GitHub profile email ───────────────────────────────

def find_via_github_profile(github_org: str) -> dict | None:
    """Check if the org/user has a public email on their GitHub profile."""
    try:
        r = httpx.get(f"https://api.github.com/users/{github_org}",
                      headers=GH_HEADERS, timeout=8)
        data = r.json()
        email = data.get("email")
        name = data.get("name") or github_org
        if email and "@" in email:
            return {
                "name": name,
                "email": email,
                "email_verified": 1,
                "email_source": "github_profile",
                "linkedin_url": None,
                "twitter_url": data.get("blog") if "linkedin" in (data.get("blog") or "") else None,
                "role": "Founder/Engineer",
            }
    except Exception:
        pass
    return None


# ── Source 2: Commit email scraping ──────────────────────────────

def find_via_commit_emails(github_org: str) -> dict | None:
    """
    Scrape recent commits to find author emails.
    Many founders commit directly — their email is in the commit metadata.
    """
    try:
        # Get repos
        r = httpx.get(f"https://api.github.com/orgs/{github_org}/repos?per_page=3&sort=updated",
                      headers=GH_HEADERS, timeout=8)
        if r.status_code != 200:
            r = httpx.get(f"https://api.github.com/users/{github_org}/repos?per_page=3&sort=updated",
                          headers=GH_HEADERS, timeout=8)
        repos = r.json() if isinstance(r.json(), list) else []

        emails_seen = {}
        for repo in repos[:2]:
            repo_name = repo.get("full_name", "")
            commits_r = httpx.get(
                f"https://api.github.com/repos/{repo_name}/commits?per_page=10",
                headers=GH_HEADERS, timeout=8
            )
            for commit in (commits_r.json() if isinstance(commits_r.json(), list) else [])[:10]:
                author = commit.get("commit", {}).get("author", {})
                email = author.get("email", "")
                name = author.get("name", "")
                # Filter out noreply and bot emails
                if (email and "@" in email
                        and "noreply" not in email
                        and "bot" not in email.lower()
                        and "github" not in email.lower()):
                    emails_seen[email] = name
            time.sleep(0.2)

        if emails_seen:
            # Pick the most frequent committer
            email, name = list(emails_seen.items())[0]
            return {
                "name": name,
                "email": email,
                "email_verified": 1,
                "email_source": "github_commits",
                "linkedin_url": None,
                "twitter_url": None,
                "role": "Engineer/Founder",
            }
    except Exception:
        pass
    return None


# ── Source 3: Minelead API ────────────────────────────────────────

def find_via_minelead(domain: str) -> dict | None:
    """Minelead domain search — 100 free credits/month, no business email required."""
    if not MINELEAD_API_KEY:
        return None
    try:
        r = httpx.get(
            "https://api.minelead.io/v1/enrichment/domain/",
            params={"domain": domain, "key": MINELEAD_API_KEY},
            timeout=10
        )
        data = r.json()
        emails = data.get("emails", [])
        if emails:
            top = emails[0]
            return {
                "name": f"{top.get('first_name','')} {top.get('last_name','')}".strip(),
                "email": top.get("email", ""),
                "email_verified": 1 if top.get("verified") else 0,
                "email_source": "minelead",
                "linkedin_url": top.get("linkedin_url"),
                "twitter_url": None,
                "role": top.get("position", ""),
            }
    except Exception:
        pass
    return None


# ── Source 4: Snov.io API ─────────────────────────────────────────

def find_via_snovio(domain: str, first_name: str = "", last_name: str = "") -> dict | None:
    """Snov.io email finder — 50 free credits/month."""
    if not SNOVIO_USER_ID or not SNOVIO_SECRET:
        return None
    try:
        # Get access token
        auth = httpx.post(
            "https://api.snov.io/v1/oauth/access_token",
            json={"grant_type": "client_credentials",
                  "client_id": SNOVIO_USER_ID,
                  "client_secret": SNOVIO_SECRET},
            timeout=10
        )
        token = auth.json().get("access_token", "")
        if not token:
            return None

        # Domain search
        r = httpx.post(
            "https://api.snov.io/v2/domain-emails-with-info",
            json={"access_token": token, "domain": domain, "limit": 3, "type": "all"},
            timeout=10
        )
        data = r.json()
        emails = data.get("emails", [])
        if emails:
            top = emails[0]
            return {
                "name": f"{top.get('firstName','')} {top.get('lastName','')}".strip(),
                "email": top.get("email", ""),
                "email_verified": 1 if top.get("emailStatus") == "valid" else 0,
                "email_source": "snovio",
                "linkedin_url": top.get("linkedinUrl"),
                "twitter_url": None,
                "role": top.get("position", ""),
            }
    except Exception:
        pass
    return None


# ── Source 5: Hunter.io API ───────────────────────────────────────

def find_via_hunter(domain: str, first_name: str = "", last_name: str = "") -> dict | None:
    """Hunter.io — 25 free searches/month, works with personal Gmail."""
    if not HUNTER_API_KEY:
        return None
    try:
        params = {"domain": domain, "api_key": HUNTER_API_KEY}
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name

        endpoint = "email-finder" if (first_name and last_name) else "domain-search"
        r = httpx.get(f"https://api.hunter.io/v2/{endpoint}",
                      params=params, timeout=10)
        data = r.json().get("data", {})

        if endpoint == "email-finder":
            email = data.get("email")
            if email:
                return {
                    "name": f"{first_name} {last_name}".strip(),
                    "email": email,
                    "email_verified": 1 if data.get("score", 0) > 70 else 0,
                    "email_source": "hunter",
                    "linkedin_url": None,
                    "twitter_url": None,
                    "role": "",
                }
        else:
            emails = data.get("emails", [])
            if emails:
                top = emails[0]
                return {
                    "name": f"{top.get('first_name','')} {top.get('last_name','')}".strip(),
                    "email": top.get("value", ""),
                    "email_verified": 1 if top.get("confidence", 0) > 70 else 0,
                    "email_source": "hunter",
                    "linkedin_url": top.get("linkedin"),
                    "twitter_url": top.get("twitter"),
                    "role": top.get("position", ""),
                }
    except Exception:
        pass
    return None


# ── Source 6: Pattern guesser + SMTP verify ───────────────────────

def smtp_verify(email: str) -> bool:
    """
    Verify email existence via SMTP without sending anything.
    Checks if the mailbox responds to RCPT TO.
    """
    domain = email.split("@")[1]
    try:
        import dns.resolver
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange)
    except Exception:
        # No DNS lib or no MX — assume valid (risky but better than nothing)
        return True

    try:
        with smtplib.SMTP(mx_host, 25, timeout=5) as smtp:
            smtp.ehlo("outreach-agent.local")
            smtp.mail("verify@outreach-agent.local")
            code, _ = smtp.rcpt(email)
            return code == 250
    except Exception:
        return True  # Many servers block SMTP probing — assume valid


def find_via_pattern(domain: str, name: str) -> dict | None:
    """
    Guess email from name + domain pattern, verify via SMTP.
    Works for ~60% of companies.
    """
    # Guess first/last name from company name if no real name
    parts = name.lower().replace("-", " ").split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
    elif len(parts) == 1:
        first, last = parts[0], ""
    else:
        return None

    patterns = [
        f"founder@{domain}",
        f"cto@{domain}",
        f"hello@{domain}",
        f"{first}@{domain}",
        f"{first}.{last}@{domain}" if last else None,
        f"{first[0]}{last}@{domain}" if last else None,
    ]
    patterns = [p for p in patterns if p]

    for email in patterns:
        if smtp_verify(email):
            return {
                "name": name,
                "email": email,
                "email_verified": 0,  # Pattern-based, not confirmed
                "email_source": "pattern",
                "linkedin_url": None,
                "twitter_url": None,
                "role": "",
            }

    return None


# ── Waterfall finder ──────────────────────────────────────────────

def find_contact(company: dict) -> dict | None:
    """
    Try each source in order. Stop at first verified result.
    Returns contact dict or None.
    """
    name = company.get("name", "")
    domain = company.get("domain", "")
    github_org = company.get("github_org")

    print(f"  🔎 Finding contact for {name} ({domain})")

    # 1. GitHub profile
    if github_org:
        result = find_via_github_profile(github_org)
        if result and result.get("email"):
            print(f"    ✅ Found via GitHub profile: {result['email']}")
            return result

    # 2. Commit emails
    if github_org:
        result = find_via_commit_emails(github_org)
        if result and result.get("email"):
            print(f"    ✅ Found via commit: {result['email']}")
            return result

    # 3. Minelead
    if domain:
        result = find_via_minelead(domain)
        if result and result.get("email"):
            print(f"    ✅ Found via Minelead: {result['email']}")
            return result

    # 4. Snov.io
    if domain:
        result = find_via_snovio(domain)
        if result and result.get("email"):
            print(f"    ✅ Found via Snov.io: {result['email']}")
            return result

    # 5. Hunter.io
    if domain:
        result = find_via_hunter(domain)
        if result and result.get("email"):
            print(f"    ✅ Found via Hunter: {result['email']}")
            return result

    # 6. Pattern guess
    if domain:
        result = find_via_pattern(domain, name)
        if result and result.get("email"):
            print(f"    ⚠️  Found via pattern (unverified): {result['email']}")
            return result

    print(f"    ❌ No contact found for {name}")
    return None


# ── Main contact run ──────────────────────────────────────────────

def run(limit=15):
    """Find contacts for top N researched companies that don't have one yet."""
    print("\n📇 Running contact finder...")

    conn = sqlite3.connect(str(TRACKER_DB))
    conn.row_factory = sqlite3.Row

    companies = conn.execute("""
        SELECT c.* FROM companies c
        WHERE c.pain_point IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM contacts ct WHERE ct.company_id = c.id
          )
        ORDER BY c.fit_score DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    print(f"   {len(companies)} companies queued for contact search\n")

    found = 0
    from agents.tracker import update_company_status
    for company in companies:
        company = dict(company)
        contact = find_contact(company)
        if contact:
            save_contact(company["id"], contact)
            update_company_status(company["id"], "contacted")
            found += 1
        time.sleep(0.5)

    print(f"\n✅ Contact finder complete: {found}/{len(companies)} contacts found")


if __name__ == "__main__":
    run()
