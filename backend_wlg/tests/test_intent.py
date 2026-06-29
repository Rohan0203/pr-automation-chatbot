"""Console test for the intent classifier graph.

Usage:
    # Run all predefined test cases
    python -m backend_wlg.tests.test_intent

    # Interactive chat mode
    python -m backend_wlg.tests.test_intent --chat
"""

from __future__ import annotations

import sys
from pathlib import Path

import asyncio

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from backend_wlg.graph.outer.graph import build_main_graph, ROUTE_TO_NODE

# Load .env — try project root first, fall back to backend/
_root = Path(__file__).resolve().parent.parent.parent
_env_path = _root / ".env"
if not _env_path.exists():
    _env_path = _root / "backend" / ".env"
load_dotenv(_env_path)


# ── predefined test cases ───────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "1. Clear PR workflow",
        "input": "Create an S3 bucket for protein team",
        "state": {},
        "expected": "pr_workflow",
    },
    {
        "name": "2. Clear Q&A",
        "input": "What naming convention do we use for Glue DBs?",
        "state": {},
        "expected": "qa",
    },
    {
        "name": "3. Clear support ticket",
        "input": "My pipeline is broken, I need help",
        "state": {},
        "expected": "support_ticket",
    },
    {
        "name": "4. Clear status check",
        "input": "What's the status of my last PR?",
        "state": {},
        "expected": "status_check",
    },
    {
        "name": "5. Follow-up (continue workflow)",
        "input": "dev",
        "state": {
            "active_workflow": "miw_agent.collect_resource",
            "last_agent_question": "What environment should this be in? (dev/staging/prod)",
        },
        "expected": "continue_workflow",
    },
    {
        "name": "6. Intent switch",
        "input": "forget this, just create a ticket because my pipeline broke",
        "state": {
            "active_workflow": "miw_agent.collect_resource",
            "last_agent_question": "What environment should this be in?",
        },
        "expected": "handle_clarify",
    },
    {
        "name": "7. Side question during workflow",
        "input": "btw what's the S3 naming convention?",
        "state": {
            "active_workflow": "miw_agent.collect_resource",
            "last_agent_question": "What environment should this be in?",
        },
        "expected": "qa",
    },
    {
        "name": "8. Multi-intent",
        "input": "Create S3 bucket and also explain IAM policies",
        "state": {},
        "expected": "pr_workflow",
    },
    {
        "name": "9. Fallback (greeting)",
        "input": "hello",
        "state": {},
        "expected": "fallback",
    },
    {
        "name": "10. Ambiguous",
        "input": "help me with S3",
        "state": {},
        "expected": "clarify",
    },
]


def _node_name_for_route(route: str) -> str:
    """Convert classifier route to the node name the graph actually routes to."""
    return ROUTE_TO_NODE.get(route, route)


async def run_tests() -> None:
    graph = build_main_graph()
    passed = 0
    failed = 0

    for tc in TEST_CASES:
        thread_id = f"test-{tc['name']}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "messages": [HumanMessage(content=tc["input"])],
            "user_id": "test_user",
            "thread_id": thread_id,
            "active_workflow": tc["state"].get("active_workflow"),
            "last_agent_question": tc["state"].get("last_agent_question"),
            "workflow_paused": False,
            "classification": None,
        }

        result = await graph.ainvoke(initial_state, config)
        classification = result.get("classification") or {}
        raw_route = classification.get("route", "NONE")
        is_switch = classification.get("is_intent_switch", False)

        if is_switch and raw_route not in ("continue_workflow", "clarify", "fallback"):
            actual_node = "handle_clarify"
        else:
            actual_node = _node_name_for_route(raw_route)

        expected_node = _node_name_for_route(tc["expected"]) if tc["expected"] in (
            "pr_workflow", "qa", "support_ticket", "status_check",
            "continue_workflow", "clarify", "fallback",
        ) else tc["expected"]

        ok = actual_node == expected_node
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {tc['name']}")
        print(f"       Route: {raw_route} | Node: {actual_node} | Expected: {expected_node}")
        print(f"       Confidence: {classification.get('confidence', 'N/A')}")
        print(f"       Switch: {is_switch}")
        print(f"       Reasoning: {classification.get('reasoning', 'N/A')}")
        if classification.get("intents"):
            print(f"       Multi-intent: {classification['intents']}")
        ai_messages = [m for m in result.get("messages", []) if getattr(m, "type", "") == "ai"]
        if ai_messages:
            print(f"       Response: {ai_messages[-1].content[:120]}...")
        print()

    print(f"Results: {passed}/{passed + failed} passed")


async def interactive_chat() -> None:
    """Interactive console chat for manual testing."""
    graph = build_main_graph()
    config = {"configurable": {"thread_id": "interactive-session"}}

    active_workflow = None
    last_question = None

    print("MiNi Intent Classifier — Interactive Mode")
    print("Type 'quit' to exit, 'reset' to clear state\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            config = {"configurable": {"thread_id": f"interactive-{id(object())}"}}
            active_workflow = None
            last_question = None
            print("State reset.\n")
            continue

        state = {
            "messages": [HumanMessage(content=user_input)],
            "user_id": "interactive_user",
            "thread_id": config["configurable"]["thread_id"],
            "active_workflow": active_workflow,
            "last_agent_question": last_question,
            "workflow_paused": False,
            "classification": None,
        }

        result = await graph.ainvoke(state, config)
        classification = result.get("classification") or {}

        # Persist workflow state across turns
        active_workflow = result.get("active_workflow")
        last_question = result.get("last_agent_question")

        print(f"\n  ┌── State ──────────────────────────────────────")
        print(f"  │ active_workflow:   {result.get('active_workflow')}")
        print(f"  │ last_agent_question: {result.get('last_agent_question')}")
        print(f"  │ workflow_paused:   {result.get('workflow_paused')}")
        print(f"  │ thread_id:        {result.get('thread_id')}")
        print(f"  │ messages count:   {len(result.get('messages', []))}")
        print(f"  └────────────────────────────────────────────────")

        print(f"  ┌── Classification ───────────────────────────────")
        print(f"  │ route:       {classification.get('route', 'N/A')}")
        print(f"  │ confidence:  {classification.get('confidence', 'N/A')}")
        print(f"  │ switch:      {classification.get('is_intent_switch', False)}")
        print(f"  │ reasoning:   {classification.get('reasoning', 'N/A')}")
        if classification.get("intent_summary"):
            print(f"  │ summary:    {classification.get('intent_summary')}")
        if classification.get("intents"):
            print(f"  │ intents:    {classification.get('intents')}")
        print(f"  └────────────────────────────────────────────────")

        ai_messages = [m for m in result.get("messages", []) if getattr(m, "type", "") == "ai"]
        if ai_messages:
            print(f"\n  MiNi: {ai_messages[-1].content}")
        print()


if __name__ == "__main__":
    if "--chat" in sys.argv:
        asyncio.run(interactive_chat())
    else:
        asyncio.run(run_tests())
