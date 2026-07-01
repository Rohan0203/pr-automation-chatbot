"""
MiNi — Console Interface
Interactive REPL for testing the agent.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
import logging
from pathlib import Path

# Add backend_v3 to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.state import Session
from db.connection import set_db_path, init_db, close_db
from db.repository import save_session
from tools.session_tools import bind_session
from agent.loop import run_agent_turn

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)
# Set agent logger to DEBUG for tool visibility
logging.getLogger("agent.loop").setLevel(logging.DEBUG)


def _print_banner():
    print("=" * 56)
    print("  MiNi — Minerva Provisioning Assistant (v3)")
    print("  Commands: /state /reset /debug /quit")
    print("=" * 56)


def _print_state(session: Session):
    print("\n┌─── STATE ─────────────────────────────────────────")
    print(f"│ Session: {session.session_id[:8]}...")
    print(f"│ Resources: {len(session.resources)}")
    for r in session.resources:
        fields_str = ", ".join(f"{k}={v}" for k, v in r.collected_fields.items())
        derived_str = ", ".join(f"{k}={v}" for k, v in r.derived_fields.items())
        print(f"│   [{r.resource_id}] status={r.status.value}")
        if fields_str:
            print(f"│     collected: {fields_str}")
        if derived_str:
            print(f"│     derived: {derived_str}")
        if r.yaml_output:
            print(f"│     yaml: generated ✓")
    print(f"│ Messages: {len(session.messages)}")
    print("└───────────────────────────────────────────────────\n")


async def main():
    # Setup database
    db_path = Path(__file__).parent / "mini.db"
    set_db_path(db_path)
    await init_db()
    print("  [DB ready]")

    # Create a new session
    session = Session(session_id=str(uuid.uuid4()))
    await save_session(session)
    bind_session(session)

    _print_banner()
    _print_state(session)

    # Main loop
    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/quit":
                break
            elif cmd == "/state":
                _print_state(session)
                continue
            elif cmd == "/reset":
                session = Session(session_id=str(uuid.uuid4()))
                await save_session(session)
                bind_session(session)
                print("  [Session reset]")
                _print_state(session)
                continue
            elif cmd == "/debug":
                # Toggle debug logging
                agent_logger = logging.getLogger("agent.loop")
                if agent_logger.level == logging.DEBUG:
                    agent_logger.setLevel(logging.WARNING)
                    print("  [Debug OFF]")
                else:
                    agent_logger.setLevel(logging.DEBUG)
                    print("  [Debug ON]")
                continue
            else:
                print(f"  Unknown command: {user_input}")
                continue

        # Process through agent
        try:
            response = await run_agent_turn(session, user_input)
            print(f"\nBot > {response}")
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            logging.getLogger(__name__).exception("Agent error")

        _print_state(session)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
