"""
Console Chat Client — interact with the backend directly from terminal.

Usage:
    python console_chat.py

Commands:
    /state   — show current session state
    /fields  — show collected fields
    /batch   — show batch contents
    /flow    — show structured flow state
    /history — show conversation history (last 10)
    /reset   — reset session (start fresh)
    /quit    — exit
"""
import asyncio
import json
import logging
import sys
import uuid

# ── Bootstrap the app so all modules load ──
sys.path.insert(0, ".")

# Configure logging BEFORE imports so we capture init logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

from app.agents.orchestrator import Orchestrator
from app.agents.session_state import get_session, delete_session

# Silence noisy loggers — keep only our agent logs
for name in ["httpx", "httpcore", "urllib3", "openai", "sqlalchemy", "uvicorn"]:
    logging.getLogger(name).setLevel(logging.WARNING)

orchestrator = Orchestrator()

SEPARATOR = "─" * 70
BOLD_SEP = "━" * 70


def print_state(session):
    """Print a compact view of the current session state."""
    agent = session.current_agent
    flow = session.structured_flow

    print(f"\n{'STATE':─^70}")
    print(f"  agent_phase    : {agent.phase if agent else 'None (no agent)'}")
    print(f"  resource_type  : {agent.resource_type if agent else '-'}")
    print(f"  fields_count   : {len(agent.collected_fields) if agent else 0}")
    if agent and agent.collected_fields:
        for k, v in agent.collected_fields.items():
            print(f"    {k:25s}: {v}")
    print(f"  has_yaml       : {bool(agent and agent.generated_yaml)}")
    print(f"  review_attempts: {agent.review_attempts if agent else 0}")
    print(f"  flow_phase     : {flow.phase if flow else '-'}")
    if flow:
        print(f"    environment  : {flow.environment}")
        print(f"    resources    : {flow.selected_resources}")
        print(f"    enterprise   : {flow.selected_enterprise}")
        print(f"    conditionals : cdp={flow.cdp_flag}, placement={flow.account_placement}")
    print(f"  batch_size     : {len(session.batch)}")
    print(f"  completed      : {len(session.completed_resources)}")
    print(f"  history_len    : {len(session.conversation_history)}")
    print(SEPARATOR)


def print_response(resp: dict):
    """Print the agent response in a readable format."""
    print(f"\n{'RESPONSE':━^70}")
    print(f"  resource_type  : {resp.get('resource_type')}")
    print(f"  resource_status: {resp.get('resource_status')}")
    print(f"  needs_confirm  : {resp.get('needs_confirmation', False)}")
    if resp.get("options"):
        print(f"  options        : {json.dumps(resp['options'], indent=2)}")
    if resp.get("pr_url"):
        print(f"  pr_url         : {resp['pr_url']}")
    if resp.get("review_result"):
        print(f"  review_result  : {json.dumps(resp['review_result'], indent=2)}")
    print(SEPARATOR)
    print()
    # Print the actual message
    print(resp.get("message", "(empty message)"))
    if resp.get("generated_yaml"):
        print(f"\n{'YAML PREVIEW':─^70}")
        print(resp["generated_yaml"])
    print()
    print(BOLD_SEP)


async def main():
    session_id = f"console-{uuid.uuid4().hex[:8]}"
    print(BOLD_SEP)
    print("  MiNi Console Chat — type messages to interact with the backend")
    print(f"  Session: {session_id}")
    print("  Commands: /state /fields /batch /flow /history /reset /quit")
    print(BOLD_SEP)

    while True:
        try:
            user_input = input("\n[YOU] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue

        # ── Meta commands ──
        if user_input.startswith("/"):
            cmd = user_input.lower()
            session = get_session(session_id)

            if cmd == "/quit" or cmd == "/exit":
                print("Bye!")
                break
            elif cmd == "/state":
                print_state(session)
            elif cmd == "/fields":
                agent = session.current_agent
                if agent and agent.collected_fields:
                    print(json.dumps(agent.collected_fields, indent=2))
                else:
                    print("  (no fields collected)")
            elif cmd == "/batch":
                if session.batch:
                    for i, b in enumerate(session.batch, 1):
                        print(f"  {i}. {b.get('resource_type','?')} — {b.get('resource_name','?')}")
                else:
                    print("  (batch empty)")
            elif cmd == "/flow":
                flow = session.structured_flow
                if flow:
                    print(f"  phase      : {flow.phase}")
                    print(f"  environment: {flow.environment}")
                    print(f"  resources  : {flow.selected_resources}")
                    print(f"  enterprise : {flow.selected_enterprise}")
                    print(f"  cdp_flag   : {flow.cdp_flag}")
                    print(f"  placement  : {flow.account_placement}")
                    print(f"  data_construct: {flow.data_construct}")
                    print(f"  account_id : {getattr(flow, 'account_id', None)}")
                else:
                    print("  (no active flow)")
            elif cmd == "/history":
                history = session.conversation_history[-20:]
                for msg in history:
                    role = msg.get("role", "?").upper()
                    content = msg.get("content", "")[:120].replace("\n", " ")
                    print(f"  [{role}] {content}")
                if not history:
                    print("  (no history)")
            elif cmd == "/reset":
                delete_session(session_id)
                session_id = f"console-{uuid.uuid4().hex[:8]}"
                print(f"  Session reset. New session: {session_id}")
            else:
                print("  Unknown command. Try: /state /fields /batch /flow /history /reset /quit")
            continue

        # ── Send message to orchestrator ──
        print(f"\n  Processing...\n")

        try:
            response = await orchestrator.process_message(session_id, user_input)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue

        print_response(response)

        # Auto-show state after every message
        session = get_session(session_id)
        print_state(session)


if __name__ == "__main__":
    asyncio.run(main())
