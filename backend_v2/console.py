"""
Console REPL — test harness for the collection flow.

Commands:
  /state   - Print full session state
  /reset   - Reset session
  /fields  - Show collected fields per resource
  /config  - Print supported resource types
  /quit    - Exit

Any other input is treated as a user message sent to the orchestrator.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import Session, SessionMode, ResourceStatus
from app.store import get_session, reset_session
from app.orchestrator import process_message
from app.collection.spec_registry import get_all_field_specs
from app.db.init_db import init_db
from app.db.connection import close_db


SESSION_ID = "console-test"


def print_state(session: Session):
    print("\n┌─── STATE ───────────────────────────────────")
    print(f"│ Mode: {session.mode.value}")
    print(f"│ Active: resource[{session.active_resource_idx}]")
    if session.resources:
        for i, r in enumerate(session.resources):
            marker = "→" if i == session.active_resource_idx else " "
            print(f"│ {marker} [{i}] {r.resource_id} ({r.status.value})")
            if r.fields:
                for k, v in r.fields.items():
                    print(f"│       {k}: {v}")
            if r.retry_counts:
                print(f"│       retries: {r.retry_counts}")
    else:
        print("│ Resources: (none)")
    print(f"│ History: {len(session.history)} messages")
    print("└──────────────────────────────────────────────\n")


def print_fields(session: Session):
    if not session.resources:
        print("No resources yet.")
        return
    for i, r in enumerate(session.resources):
        print(f"\n[{i}] {r.resource_id} ({r.status.value}):")
        if r.fields:
            for k, v in r.fields.items():
                print(f"  {k}: {v}")
        else:
            print("  (no fields collected)")


def print_config():
    print("\nSupported resource types:")
    for rtype, specs in get_all_field_specs().items():
        askable = [s.name for s in specs if not s.derivable]
        print(f"  {rtype}: {len(askable)} fields to collect")
        for name in askable:
            print(f"    - {name}")


async def main():
    print("=" * 50)
    print("  PR Automation Chatbot — Console (v2)")
    print("  Commands: /state /fields /reset /config /quit")
    print("=" * 50)

    # Initialize database (creates tables if missing)
    try:
        await init_db()
        print("  [DB connected]")
    except Exception as e:
        print(f"  [DB unavailable: {e}] — running without persistence")

    session = get_session(SESSION_ID)
    print_state(session)

    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        if user_input == "/state":
            print_state(session)
            continue
        elif user_input == "/fields":
            print_fields(session)
            continue
        elif user_input == "/reset":
            session = reset_session(SESSION_ID)
            print("[Session reset]")
            print_state(session)
            continue
        elif user_input == "/config":
            print_config()
            continue
        elif user_input == "/quit":
            print("Bye!")
            break

        # Send to orchestrator
        try:
            response = await process_message(session, user_input)
            print(f"\nBot > {response}")
        except Exception as e:
            print(f"\n[ERROR] {type(e).__name__}: {e}")

        print_state(session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Clean up DB connection
        asyncio.run(close_db())

