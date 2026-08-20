"""
migrate_to_supabase.py
─────────────────────
One-time migration: reads all rows from the local SQLite DB and upserts
them into Supabase (Postgres). Safe to re-run — uses upsert / ignore-on-conflict.

Run from repo root:
    python3 scripts/migrate_to_supabase.py
"""
import sqlite3
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────
PROJ = Path(__file__).resolve().parent.parent
load_dotenv(PROJ / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SQLITE_DB    = PROJ / "data" / "tracker" / "outreach.db"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

if not SQLITE_DB.exists():
    print(f"❌ SQLite DB not found at {SQLITE_DB}")
    sys.exit(1)

from supabase import create_client
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Helpers ───────────────────────────────────────────────────────

def sqlite_rows(conn, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(r) for r in rows]


def clean_row(row: dict, drop_cols: list[str] = None) -> dict:
    """Remove None values and unwanted columns for cleaner upserts."""
    drop = set(drop_cols or [])
    return {k: v for k, v in row.items() if v is not None and k not in drop}


def migrate_table(conn, table: str, id_map: dict = None,
                  remap: dict = None, drop_cols: list[str] = None,
                  on_conflict: str = None) -> dict:
    """
    Migrate one table from SQLite → Supabase.
    - id_map: maps old SQLite id → new Supabase id (built during migration)
    - remap: renames FK columns using the id_map from parent table
    - drop_cols: columns to drop (e.g. removed LinkedIn/X cols)
    Returns: {old_id: new_id}
    """
    rows = sqlite_rows(conn, table)
    if not rows:
        print(f"   {table}: 0 rows (skipped)")
        return {}

    new_id_map = {}
    inserted = 0
    skipped  = 0

    for row in rows:
        old_id = row.get("id")
        r = clean_row(row, drop_cols=["id"] + (drop_cols or []))

        # Remap FK ids using parent id_map
        if remap and id_map:
            for old_col, new_col in remap.items():
                old_fk = r.pop(old_col, None)
                if old_fk is not None and old_fk in id_map:
                    r[new_col] = id_map[old_fk]
                elif old_fk is not None:
                    r[new_col] = old_fk  # keep as-is if not in map

        # Fix boolean fields (SQLite stores 0/1, Postgres needs bool)
        for col in ["email_verified"]:
            if col in r:
                r[col] = bool(r[col])

        try:
            if on_conflict:
                result = sb.table(table).upsert(r, on_conflict=on_conflict).execute()
            else:
                result = sb.table(table).insert(r).execute()

            if result.data:
                new_id = result.data[0]["id"]
                new_id_map[old_id] = new_id
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            err = str(e)
            if "duplicate" in err.lower() or "unique" in err.lower():
                # Already exists — fetch it to get the new id
                try:
                    name = r.get("name", "")
                    domain = r.get("domain", "")
                    if table == "companies" and (name or domain):
                        q = sb.table(table).select("id")
                        if name:
                            q = q.eq("name", name)
                        res = q.limit(1).execute()
                        if res.data:
                            new_id_map[old_id] = res.data[0]["id"]
                except Exception:
                    pass
                skipped += 1
            else:
                print(f"     ⚠️  {table} row {old_id}: {err[:120]}")
                skipped += 1

    print(f"   {table}: {inserted} inserted, {skipped} skipped → {len(new_id_map)} id mappings")
    return new_id_map


# ── Main migration ────────────────────────────────────────────────

def main():
    print("🚀 Outreach Agent — SQLite → Supabase Migration")
    print(f"   Source: {SQLITE_DB}")
    print(f"   Target: {SUPABASE_URL}\n")

    conn = sqlite3.connect(str(SQLITE_DB))

    # 1. Companies (no FKs)
    print("📦 Migrating companies...")
    company_id_map = migrate_table(
        conn, "companies",
        on_conflict="name,domain",
    )

    # 2. Contacts (FK: company_id)
    print("📧 Migrating contacts...")
    contact_id_map = migrate_table(
        conn, "contacts",
        id_map=company_id_map,
        remap={"company_id": "company_id"},
    )

    # 3. Drafts — FK remap needs separate maps for company_id and contact_id
    print("✍️  Migrating drafts...")
    sqlite_drafts = sqlite_rows(conn, "drafts")
    draft_id_map  = {}
    inserted_d = 0
    skipped_d  = 0

    for row in sqlite_drafts:
        old_id          = row["id"]
        old_company_id  = row.get("company_id")
        old_contact_id  = row.get("contact_id")

        new_company_id = company_id_map.get(old_company_id)
        new_contact_id = contact_id_map.get(old_contact_id)

        if not new_company_id or not new_contact_id:
            skipped_d += 1
            continue

        r = {
            "company_id":    new_company_id,
            "contact_id":    new_contact_id,
            "email_subject": row.get("email_subject"),
            "email_body":    row.get("email_body"),
            "status":        row.get("status") or "drafted_ready",
            "telegram_msg_id": row.get("telegram_msg_id"),
            "approved_at":   row.get("approved_at"),
        }
        r = {k: v for k, v in r.items() if v is not None}

        try:
            res = sb.table("drafts").insert(r).execute()
            if res.data:
                draft_id_map[old_id] = res.data[0]["id"]
                inserted_d += 1
        except Exception as e:
            print(f"     ⚠️  drafts row {old_id}: {str(e)[:120]}")
            skipped_d += 1

    print(f"   drafts: {inserted_d} inserted, {skipped_d} skipped → {len(draft_id_map)} id mappings")

    # 4. Sends (FK: draft_id)
    print("📨 Migrating sends...")
    send_id_map = migrate_table(
        conn, "sends",
        id_map=draft_id_map,
        remap={"draft_id": "draft_id"},
    )

    # 5. Follow-ups (FK: send_id)
    print("🔁 Migrating follow_ups...")
    migrate_table(
        conn, "follow_ups",
        id_map=send_id_map,
        remap={"send_id": "send_id"},
    )

    conn.close()

    # ── Verify counts ─────────────────────────────────────────────
    print("\n✅ Migration complete! Verifying Supabase row counts:")
    for table in ["companies", "contacts", "drafts", "sends", "follow_ups"]:
        try:
            res = sb.table(table).select("id", count="exact").execute()
            count = res.count if res.count is not None else len(res.data)
            print(f"   {table}: {count} rows in Supabase")
        except Exception as e:
            print(f"   {table}: ERROR reading count — {e}")


if __name__ == "__main__":
    main()
