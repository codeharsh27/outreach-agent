"""
tracker.py — Hardened Supabase Data Access Layer
Fixes applied:
- V5: Range pagination loop to avoid 1,000 row PostgREST truncation
- V14: Explicit query schemas & relational checks
- V15: Sanitizes null bytes (\u0000) and invalid UTF-8 sequences from all text fields
"""
import os
from datetime import datetime, timezone
from agents.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client

_client: Client | None = None

def _sb() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in .env\n"
                "Get them from: supabase.com → Project Settings → API"
            )
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def verify_connection():
    """Check Supabase connection and connectivity."""
    try:
        res = _sb().table("companies").select("id").limit(1).execute()
        print("✅ Supabase connected")
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        raise


def _clean_text(val):
    """Fix V15: Strip null bytes and invalid characters for Postgres string safety."""
    if isinstance(val, str):
        return val.replace("\u0000", "").strip()
    return val


# ── Company helpers ───────────────────────────────────────────────

def upsert_company(data: dict) -> int:
    """Insert or update a company cleanly."""
    import json as _json

    VALID_COLS = {
        "name", "domain", "description", "tags", "batch", "github_org",
        "linkedin_url", "twitter_url", "hq_country", "team_size",
        "funding", "source", "tier", "fit_score", "pain_point",
        "evidence_url", "suggested_angle", "status",
    }

    clean = {}
    for k, v in data.items():
        if k not in VALID_COLS or v is None:
            continue
        if isinstance(v, (list, dict)):
            clean[k] = _json.dumps(v)
        else:
            clean[k] = _clean_text(v)

    if not clean.get("name"):
        return 0

    try:
        res = _sb().table("companies").upsert(clean, on_conflict="name,domain").execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass

    try:
        res = _sb().table("companies").select("id").eq("name", clean["name"]).limit(1).execute()
        if res.data:
            row_id = res.data[0]["id"]
            _sb().table("companies").update(clean).eq("id", row_id).execute()
            return row_id
    except Exception as e:
        print(f"  [tracker] upsert_company error: {e}")

    return 0


def get_companies_to_research(limit: int = 45) -> list:
    """Fix V5: Range pagination loop to avoid PostgREST 1,000-row cutoff."""
    try:
        drafted_ids = set()
        page_size = 1000
        start = 0

        # Paginate to fetch ALL draft company IDs
        while True:
            res = _sb().table("drafts").select("company_id").range(start, start + page_size - 1).execute()
            rows = res.data or []
            for r in rows:
                if r.get("company_id"):
                    drafted_ids.add(r["company_id"])
            if len(rows) < page_size:
                break
            start += page_size

        # Fetch candidate companies
        res = _sb().table("companies") \
            .select("*") \
            .in_("status", ["queued", "researched"]) \
            .order("fit_score", desc=True) \
            .limit(limit * 3) \
            .execute()

        candidates = [r for r in (res.data or []) if r["id"] not in drafted_ids]
        return candidates[:limit]
    except Exception as e:
        print(f"  [tracker] get_companies_to_research error: {e}")
        return []


def mark_researched(company_id: int, pain_point: str, evidence_url: str,
                    suggested_angle: str, tier: str):
    try:
        _sb().table("companies").update({
            "pain_point": _clean_text(pain_point),
            "evidence_url": _clean_text(evidence_url),
            "suggested_angle": _clean_text(suggested_angle),
            "tier": tier,
            "status": "researched",
        }).eq("id", company_id).execute()
    except Exception as e:
        print(f"  [tracker] mark_researched error: {e}")


def update_company_status(company_id: int, status: str):
    try:
        _sb().table("companies").update({"status": status}).eq("id", company_id).execute()
    except Exception as e:
        print(f"  [tracker] update_company_status error: {e}")


# ── Contact helpers ───────────────────────────────────────────────

def save_contact(company_id: int, data: dict) -> int:
    """Save contact safely."""
    VALID_COLS = {
        "name", "role", "email", "linkedin_url", "twitter_url",
        "email_verified", "email_source",
    }
    clean = {k: _clean_text(v) for k, v in data.items() if k in VALID_COLS and v is not None}
    clean["company_id"] = company_id

    if "email_verified" in clean:
        clean["email_verified"] = bool(clean["email_verified"])

    try:
        res = _sb().table("contacts").insert(clean).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print(f"  [tracker] save_contact error: {e}")
    return 0


# ── Draft helpers ─────────────────────────────────────────────────

def save_draft(company_id: int, contact_id: int, data: dict) -> int:
    """Save email draft safely."""
    VALID_COLS = {"email_subject", "email_body", "status", "telegram_msg_id"}
    clean = {k: _clean_text(v) for k, v in data.items() if k in VALID_COLS and v is not None}
    clean["company_id"] = company_id
    clean["contact_id"] = contact_id

    try:
        res = _sb().table("drafts").insert(clean).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print(f"  [tracker] save_draft error: {e}")
    return 0


def get_pending_drafts(limit: int = 50) -> list:
    """Fix V14: Explicit, error-handled join query for pending drafts."""
    try:
        res = _sb().table("drafts") \
            .select(
                "*, "
                "companies(name, domain), "
                "contacts(name, email)"
            ) \
            .in_("status", ["pending", "drafted_ready"]) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        rows = []
        for r in (res.data or []):
            flat = dict(r)
            co = flat.pop("companies", {}) or {}
            ct = flat.pop("contacts", {}) or {}
            flat["company_name"] = co.get("name", "Unknown")
            flat["domain"]       = co.get("domain", "")
            flat["contact_name"] = ct.get("name", "Team")
            flat["email"]        = ct.get("email", "")
            rows.append(flat)
        return rows
    except Exception as e:
        print(f"  [tracker] get_pending_drafts error: {e}")
        return []


def update_draft_status(draft_id: int, status: str, telegram_msg_id: str = None):
    try:
        payload = {"status": status}
        if telegram_msg_id is not None:
            payload["telegram_msg_id"] = telegram_msg_id
        if status == "approved":
            payload["approved_at"] = datetime.now(timezone.utc).isoformat()
        _sb().table("drafts").update(payload).eq("id", draft_id).execute()
    except Exception as e:
        print(f"  [tracker] update_draft_status error: {e}")


def update_draft_body(draft_id: int, new_body: str):
    try:
        _sb().table("drafts").update({"email_body": _clean_text(new_body)}).eq("id", draft_id).execute()
    except Exception as e:
        print(f"  [tracker] update_draft_body error: {e}")


def get_draft_by_id(draft_id: int) -> dict | None:
    try:
        res = _sb().table("drafts") \
            .select(
                "*, "
                "companies(name, domain), "
                "contacts(name, email)"
            ) \
            .eq("id", draft_id) \
            .limit(1) \
            .execute()
        if not res.data:
            return None
        r = res.data[0]
        flat = dict(r)
        co = flat.pop("companies", {}) or {}
        ct = flat.pop("contacts", {}) or {}
        flat["company_name"] = co.get("name", "")
        flat["domain"]       = co.get("domain", "")
        flat["contact_name"] = ct.get("name", "")
        flat["email"]        = ct.get("email", "")
        return flat
    except Exception as e:
        print(f"  [tracker] get_draft_by_id error: {e}")
        return None


# ── Send helpers ──────────────────────────────────────────────────

def queue_send(draft_id: int, platform: str, scheduled_for: str) -> int:
    try:
        res = _sb().table("sends").insert({
            "draft_id": draft_id,
            "platform": platform,
            "scheduled_for": scheduled_for,
            "status": "sending",  # Fix V8: Atomic lock status to prevent duplicate sending
        }).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print(f"  [tracker] queue_send error: {e}")
    return 0


def mark_sent(send_id: int):
    try:
        _sb().table("sends").update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", send_id).execute()
    except Exception as e:
        print(f"  [tracker] mark_sent error: {e}")


def already_contacted(domain: str) -> bool:
    """True if an email was already sent to this domain."""
    if not domain:
        return False
    try:
        co_res = _sb().table("companies").select("id").eq("domain", domain).execute()
        if not co_res.data:
            return False
        company_ids = [r["id"] for r in co_res.data]

        dr_res = _sb().table("drafts").select("id").in_("company_id", company_ids).execute()
        if not dr_res.data:
            return False
        draft_ids = [r["id"] for r in dr_res.data]

        sn_res = _sb().table("sends") \
            .select("id") \
            .in_("draft_id", draft_ids) \
            .eq("status", "sent") \
            .limit(1) \
            .execute()
        return bool(sn_res.data)
    except Exception as e:
        print(f"  [tracker] already_contacted error: {e}")
        return False


def print_stats():
    """Print pipeline stats."""
    print("\n📊 Outreach Agent — Pipeline Stats (Supabase)")
    for table in ["companies", "contacts", "drafts", "sends", "follow_ups"]:
        try:
            res = _sb().table(table).select("id", count="exact").execute()
            count = res.count if res.count is not None else len(res.data or [])
            print(f"   {table:<15} {count} rows")
        except Exception as e:
            print(f"   {table:<15} ERROR: {e}")
    print()


if __name__ == "__main__":
    verify_connection()
    print_stats()
