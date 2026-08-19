"""
SQLite tracker — one source of truth for every company touched.
Tracks: discovery → research → contact → draft → send → follow-up.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from agents.config import TRACKER_DB


def _conn():
    c = sqlite3.connect(str(TRACKER_DB))
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Create all tables if they don't exist."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            domain      TEXT,
            description TEXT,
            tags        TEXT,           -- JSON array stored as string
            batch       TEXT,           -- YC batch e.g. "Winter 2025"
            github_org  TEXT,
            linkedin_url TEXT,
            twitter_url  TEXT,
            hq_country  TEXT,
            team_size   TEXT,
            funding     TEXT,
            source      TEXT,          -- yc | github_trending | producthunt | wellfound
            tier        TEXT,          -- A | B
            fit_score   REAL,
            pain_point  TEXT,
            evidence_url TEXT,
            suggested_angle TEXT,
            status      TEXT DEFAULT 'queued', -- queued | researched | drafted | sent | skip
            discovered_at TEXT DEFAULT (datetime('now')),
            UNIQUE(name, domain)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id  INTEGER REFERENCES companies(id),
            name        TEXT,
            role        TEXT,
            email       TEXT,
            linkedin_url TEXT,
            twitter_url  TEXT,
            email_verified INTEGER DEFAULT 0,
            email_source TEXT,         -- github | hunter | snovio | minelead | pattern
            found_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS drafts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id      INTEGER REFERENCES companies(id),
            contact_id      INTEGER REFERENCES contacts(id),
            email_subject   TEXT,
            email_body      TEXT,
            linkedin_msg    TEXT,
            x_reply_text    TEXT,
            x_reply_url     TEXT,
            status          TEXT DEFAULT 'pending',  -- pending|approved|edited|skipped
            telegram_msg_id TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            approved_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS sends (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id    INTEGER REFERENCES drafts(id),
            platform    TEXT,          -- email | linkedin | x
            sent_at     TEXT,
            scheduled_for TEXT,
            status      TEXT DEFAULT 'queued',  -- queued|sent|failed
            error       TEXT
        );

        CREATE TABLE IF NOT EXISTS follow_ups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            send_id     INTEGER REFERENCES sends(id),
            due_at      TEXT,
            sent_at     TEXT,
            status      TEXT DEFAULT 'pending'   -- pending|sent|skipped
        );
        """)
    print("✅ Database initialized")


# ── Company helpers ───────────────────────────────────────────────

def upsert_company(data: dict) -> int:
    """Insert or update a company. Returns company id.
    Automatically strips unknown fields and serializes lists to JSON.
    """
    import json as _json

    # All valid DB columns for companies table (excluding id, discovered_at)
    VALID_COLS = {
        "name", "domain", "description", "tags", "batch", "github_org",
        "linkedin_url", "twitter_url", "hq_country", "team_size",
        "funding", "source", "tier", "fit_score", "pain_point",
        "evidence_url", "suggested_angle", "status",
    }

    # Clean: keep only known columns, serialize lists/dicts
    clean = {}
    for k, v in data.items():
        if k not in VALID_COLS:
            continue
        if isinstance(v, (list, dict)):
            clean[k] = _json.dumps(v)
        else:
            clean[k] = v

    conn = _conn()
    try:
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT id FROM companies WHERE name=? OR (domain IS NOT NULL AND domain=?)",
            (clean.get("name"), clean.get("domain"))
        ).fetchone()

        if existing:
            update_data = {k: v for k, v in clean.items() if k not in ("name", "domain")}
            if not update_data:
                return existing["id"]
            cols = ", ".join(f"{k}=?" for k in update_data)
            vals = list(update_data.values()) + [existing["id"]]
            cur.execute(f"UPDATE companies SET {cols} WHERE id=?", vals)
            conn.commit()
            return existing["id"]
        else:
            cols = ", ".join(clean.keys())
            placeholders = ", ".join("?" * len(clean))
            cur.execute(
                f"INSERT INTO companies ({cols}) VALUES ({placeholders})",
                list(clean.values())
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_companies_to_research(limit=45) -> list:
    """Get queued companies from pool ordered by fit score."""
    with _conn() as c:
        return c.execute("""
            SELECT c.* FROM companies c
            LEFT JOIN drafts d ON d.company_id = c.id
            WHERE d.id IS NULL
              AND (c.status IS NULL OR c.status = 'queued' OR c.pain_point IS NULL)
            ORDER BY c.fit_score DESC
            LIMIT ?
        """, (limit,)).fetchall()


def mark_researched(company_id: int, pain_point: str, evidence_url: str,
                     suggested_angle: str, tier: str):
    with _conn() as c:
        c.execute("""
            UPDATE companies
            SET pain_point=?, evidence_url=?, suggested_angle=?, tier=?, status='researched'
            WHERE id=?
        """, (pain_point, evidence_url, suggested_angle, tier, company_id))


# ── Contact helpers ───────────────────────────────────────────────

def save_contact(company_id: int, data: dict) -> int:
    conn = _conn()
    try:
        cur = conn.cursor()
        cols = ", ".join(["company_id"] + list(data.keys()))
        placeholders = ", ".join("?" * (len(data) + 1))
        cur.execute(
            f"INSERT INTO contacts ({cols}) VALUES ({placeholders})",
            [company_id] + list(data.values())
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ── Draft helpers ─────────────────────────────────────────────────

def save_draft(company_id: int, contact_id: int, data: dict) -> int:
    conn = _conn()
    try:
        cur = conn.cursor()
        cols = ", ".join(["company_id", "contact_id"] + list(data.keys()))
        placeholders = ", ".join("?" * (len(data) + 2))
        cur.execute(
            f"INSERT INTO drafts ({cols}) VALUES ({placeholders})",
            [company_id, contact_id] + list(data.values())
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_pending_drafts(limit=50) -> list:
    """Get ready drafts pending Telegram approval (both 'pending' and 'drafted_ready')."""
    with _conn() as c:
        return c.execute("""
            SELECT d.*, co.name as company_name, co.domain,
                   ct.name as contact_name, ct.email, ct.linkedin_url,
                   ct.twitter_url
            FROM drafts d
            JOIN companies co ON co.id = d.company_id
            JOIN contacts  ct ON ct.id = d.contact_id
            WHERE d.status IN ('pending', 'drafted_ready')
            ORDER BY d.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def update_draft_status(draft_id: int, status: str, telegram_msg_id: str = None):
    with _conn() as c:
        approved_at = datetime.now(timezone.utc).isoformat() if status == "approved" else None
        c.execute(
            "UPDATE drafts SET status=?, telegram_msg_id=?, approved_at=? WHERE id=?",
            (status, telegram_msg_id, approved_at, draft_id)
        )


def update_company_status(company_id: int, status: str):
    with _conn() as c:
        c.execute("UPDATE companies SET status=? WHERE id=?", (status, company_id))


# ── Send helpers ──────────────────────────────────────────────────

def queue_send(draft_id: int, platform: str, scheduled_for: str) -> int:
    with _conn() as c:
        c.execute(
            "INSERT INTO sends (draft_id, platform, scheduled_for) VALUES (?,?,?)",
            (draft_id, platform, scheduled_for)
        )
        return c.lastrowid


def mark_sent(send_id: int):
    with _conn() as c:
        c.execute(
            "UPDATE sends SET status='sent', sent_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), send_id)
        )


def already_contacted(domain: str) -> bool:
    """True if we've already sent to this company domain."""
    with _conn() as c:
        row = c.execute("""
            SELECT 1 FROM sends s
            JOIN drafts d  ON d.id = s.draft_id
            JOIN companies co ON co.id = d.company_id
            WHERE co.domain = ? AND s.status = 'sent'
            LIMIT 1
        """, (domain,)).fetchone()
        return row is not None


if __name__ == "__main__":
    init_db()
