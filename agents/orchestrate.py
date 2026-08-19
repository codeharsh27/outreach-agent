"""
Main orchestrator — runs the full pipeline end-to-end.
Called daily by cron or manually.

Pipeline:
  init_db → discover → research → contact → draft → approve → send
"""
import sys
import time
from datetime import datetime, timezone

from agents.tracker import init_db
from agents import discover, research, contact, draft, approve, send


def run_pipeline(skip_approval: bool = False):
    """
    Full pipeline run. Set skip_approval=True only for testing.
    """
    start = datetime.now(timezone.utc)
    print("=" * 55)
    print(f" Outreach Agent — Daily Run")
    print(f" Started: {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    # Step 0: Init DB (idempotent)
    init_db()

    # Step 1: Discover companies (only if pool is low)
    print("\n[1/6] DISCOVERY (Checking pool...)")
    import sqlite3
    from agents.config import TRACKER_DB
    conn = sqlite3.connect(str(TRACKER_DB))
    queued_count = conn.execute("SELECT COUNT(*) FROM companies WHERE status='queued' OR status IS NULL").fetchone()[0]
    conn.close()
    
    if queued_count < 45:
        print(f"   Pool has {queued_count} queued companies — topping up pool...")
        discover.run(max_new=200)
    else:
        print(f"   Pool has {queued_count} queued companies ready — pulling top 45!")
    time.sleep(1)

    # Step 2: Research
    print("\n[2/6] RESEARCH")
    research.run(limit=45)
    time.sleep(2)

    # Step 3: Find contacts
    print("\n[3/6] CONTACT FINDING")
    contact.run()
    time.sleep(2)

    # Step 4: Draft
    print("\n[4/6] DRAFTING")
    draft.run()
    time.sleep(2)

    # Step 5: Approval gate
    print("\n[5/6] TELEGRAM APPROVAL")
    if skip_approval:
        print("   (skipped for testing)")
        # Auto-approve first 3 for testing
        import sqlite3
        from agents.config import TRACKER_DB
        conn = sqlite3.connect(str(TRACKER_DB))
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM drafts WHERE status='pending' LIMIT 3"
        ).fetchall()]
        for i in ids:
            conn.execute("UPDATE drafts SET status='approved' WHERE id=?", (i,))
        conn.commit()
        conn.close()
        approved_ids = ids
    else:
        approved_ids = approve.run()
    time.sleep(2)

    # Step 6: Send
    print("\n[6/6] SENDING")
    send.run(approved_ids)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"\n{'='*55}")
    print(f" Pipeline complete in {int(elapsed//60)}m {int(elapsed%60)}s")
    print(f" Approved: {len(approved_ids)} emails sent")
    print(f"{'='*55}\n")


def run_minibatch(batch_size=15):
    """Run a small background mini-batch: discovery top-up + research + contact search."""
    init_db()
    import sqlite3
    from agents.config import TRACKER_DB
    conn = sqlite3.connect(str(TRACKER_DB))
    queued_count = conn.execute("SELECT COUNT(*) FROM companies WHERE status='queued' OR status IS NULL").fetchone()[0]
    conn.close()

    if queued_count < 30:
        print("   Topping up company pool...")
        discover.run(max_new=100)

    print(f"\n⚡ Running mini-batch ({batch_size} companies)...")
    research.run(limit=batch_size)
    contact.run(limit=batch_size)
    print(f"✅ Mini-batch complete!")


def run_draft_night(limit=45):
    """Night job: generate drafts for all pre-staged companies using Gemini 3.6 Flash."""
    init_db()
    print(f"\n🌙 Running night drafting for up to {limit} pre-staged companies...")
    draft.run(limit=limit)
    print(f"✅ Night drafting complete — drafts ready for morning delivery!")


def run_morning_push():
    """Morning job (8 AM): push all pre-staged draft cards to Telegram for review."""
    init_db()
    print("\n🌅 Running morning Telegram push...")
    approved_ids = approve.run()
    if approved_ids:
        print("\n📨 Sending approved emails...")
        send.run(approved_ids)


def show_stats():
    """Print pipeline stats from the DB."""
    import sqlite3
    from agents.config import TRACKER_DB

    conn = sqlite3.connect(str(TRACKER_DB))
    print("\n📊 Outreach Pipeline Stats")
    print("─" * 40)

    tables = {
        "companies":   "Companies discovered",
        "contacts":    "Contacts found",
        "drafts":      "Drafts generated",
    }
    for table, label in tables.items():
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {label:25s}: {count}")

    # Drafts by status
    print("\n  Drafts by status:")
    for row in conn.execute("SELECT status, COUNT(*) FROM drafts GROUP BY status"):
        print(f"    {row[0]:12s}: {row[1]}")

    # Sends by status
    print("\n  Sends by status:")
    for row in conn.execute("SELECT status, COUNT(*) FROM sends GROUP BY status"):
        print(f"    {row[0]:12s}: {row[1]}")

    # Companies by tier
    print("\n  Companies by tier:")
    for row in conn.execute("SELECT tier, COUNT(*) FROM companies WHERE tier IS NOT NULL GROUP BY tier"):
        print(f"    Tier {row[0]:8s}: {row[1]}")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Outreach Agent Orchestrator")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "discover", "research", "draft", "contact", "minibatch", "draft_night", "morning_push", "stats", "test"],
                        help="Command to run")
    args = parser.parse_args()

    if args.command == "run":
        run_pipeline()
    elif args.command == "test":
        print("⚠️  TEST MODE — skipping approval, auto-approving 3 drafts")
        run_pipeline(skip_approval=True)
    elif args.command == "minibatch":
        run_minibatch()
    elif args.command == "draft_night":
        run_draft_night()
    elif args.command == "morning_push":
        run_morning_push()
    elif args.command == "discover":
        init_db()
        run_discovery_only()
    elif args.command == "research":
        run_research_only()
    elif args.command == "draft":
        init_db()
        run_draft_only()
    elif args.command == "contact":
        init_db()
        contact.run(limit=45)
    elif args.command == "stats":
        show_stats()
