"""
Main orchestrator — runs the full pipeline end-to-end.
Called daily by cron or manually.

Pipeline:
  verify_connection → discover → research → contact → draft → approve → send
"""
import sys
import time
from datetime import datetime, timezone

from agents.tracker import verify_connection, print_stats, _sb
from agents import discover, research, contact, draft, approve, send


def run_pipeline(skip_approval: bool = False):
    """Full pipeline run. Set skip_approval=True only for testing."""
    start = datetime.now(timezone.utc)
    print("=" * 55)
    print(f" Outreach Agent — Daily Run")
    print(f" Started: {start.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    # Step 0: Verify Supabase connection
    verify_connection()

    # Step 1: Discover companies (top up if pool is low)
    print("\n[1/6] DISCOVERY")
    try:
        res = _sb().table("companies") \
            .select("id", count="exact") \
            .in_("status", ["queued", "researched"]) \
            .execute()
        queued_count = res.count or 0
    except Exception:
        queued_count = 0

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
        print("   (TEST MODE — auto-approving first 3 drafts)")
        try:
            res = _sb().table("drafts") \
                .select("id") \
                .eq("status", "drafted_ready") \
                .limit(3) \
                .execute()
            ids = [r["id"] for r in (res.data or [])]
            for draft_id in ids:
                _sb().table("drafts").update({"status": "approved"}).eq("id", draft_id).execute()
            approved_ids = ids
        except Exception as e:
            print(f"   Auto-approve error: {e}")
            approved_ids = []
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


def run_minibatch(batch_size: int = 15):
    """Background mini-batch: top up pool + research + contact search."""
    verify_connection()

    try:
        res = _sb().table("companies") \
            .select("id", count="exact") \
            .in_("status", ["queued"]) \
            .execute()
        queued_count = res.count or 0
    except Exception:
        queued_count = 0

    if queued_count < 30:
        print("   Topping up company pool...")
        discover.run(max_new=100)

    print(f"\n⚡ Running mini-batch ({batch_size} companies)...")
    research.run(limit=batch_size)
    contact.run(limit=batch_size)
    print(f"✅ Mini-batch complete!")


def run_draft_night(limit: int = 45):
    """Night job: generate email drafts for all pre-staged companies."""
    verify_connection()
    print(f"\n🌙 Running night drafting for up to {limit} pre-staged companies...")
    draft.run(limit=limit)
    print(f"✅ Night drafting complete — drafts ready for morning delivery!")


def run_morning_push():
    """Morning job (8 AM): push all pre-staged draft cards to Telegram for review."""
    verify_connection()
    print("\n🌅 Running morning Telegram push...")
    approved_ids = approve.run()
    if approved_ids:
        print("\n📨 Sending approved emails...")
        send.run(approved_ids)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Outreach Agent Orchestrator")
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["run", "discover", "research", "draft", "contact",
                 "minibatch", "draft_night", "morning_push", "stats", "test"],
        help="Command to run",
    )
    args = parser.parse_args()

    if args.command == "run":
        run_pipeline()
    elif args.command == "test":
        print("⚠️  TEST MODE — auto-approving 3 drafts")
        run_pipeline(skip_approval=True)
    elif args.command == "minibatch":
        run_minibatch()
    elif args.command == "draft_night":
        run_draft_night()
    elif args.command == "morning_push":
        run_morning_push()
    elif args.command == "discover":
        verify_connection()
        discover.run(max_new=200)
    elif args.command == "research":
        verify_connection()
        research.run(limit=45)
    elif args.command == "draft":
        verify_connection()
        draft.run()
    elif args.command == "contact":
        verify_connection()
        contact.run(limit=45)
    elif args.command == "stats":
        verify_connection()
        print_stats()
