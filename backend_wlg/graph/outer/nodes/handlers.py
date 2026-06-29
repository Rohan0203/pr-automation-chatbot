from __future__ import annotations

from langchain_core.messages import AIMessage

from backend_wlg.graph.outer.state import MainGraphState
from backend_wlg.graph.pr_workflow.graph import build_pr_workflow_graph

CAPABILITIES_MESSAGE = (
    "Hi! I'm MiNi, your data pipeline automation assistant. I can help you with:\n\n"
    "- **Resource Creation** — Provision S3 buckets, Glue databases, IAM roles, "
    "resource policies, SMUS projects, and SMUS roles via automated PRs\n"
    "- **Q&A** — Answer questions about architecture, naming conventions, "
    "and best practices\n"
    "- **Support Tickets** — Create Jira tickets for issues that need human help\n"
    "- **Status Checks** — Check the status of your prior requests and PRs\n\n"
    "What would you like to do?"
)


# ---------------------------------------------------------------------------
# Real handler nodes
# ---------------------------------------------------------------------------


def handle_clarify_node(state: MainGraphState) -> dict:
    """Ask the user to clarify an ambiguous message or confirm an intent switch."""
    classification = state.get("classification") or {}
    reasoning = classification.get("reasoning", "")
    is_switch = classification.get("is_intent_switch", False)
    intent_summary = classification.get("intent_summary", "")
    active_workflow = state.get("active_workflow")

    if is_switch and active_workflow:
        response = (
            f"It looks like you want to switch tasks. "
            f"You currently have an active workflow: **{active_workflow}**.\n\n"
            f"New request: *{intent_summary or reasoning}*\n\n"
            f"Would you like to **abandon** the current workflow and proceed "
            f"with the new request, or **continue** where you left off?"
        )
    else:
        response = (
            f"I'm not sure I understood correctly. {reasoning}\n\n"
            f"Could you clarify what you'd like to do? For example:\n"
            f"- **Create a resource** (S3, Glue DB, IAM, etc.)\n"
            f"- **Ask a question** about conventions or architecture\n"
            f"- **Report a problem** and create a support ticket\n"
            f"- **Check status** of a prior request"
        )

    return {"messages": [AIMessage(content=response)]}


def handle_fallback_node(state: MainGraphState) -> dict:
    """Respond to greetings, thanks, and off-topic messages."""
    return {"messages": [AIMessage(content=CAPABILITIES_MESSAGE)]}


# ---------------------------------------------------------------------------
# Stub handler nodes (to be replaced in later phases)
# ---------------------------------------------------------------------------


def continue_workflow_node(state: MainGraphState) -> dict:
    """Forward follow-up messages to the active workflow agent."""
    active = state.get("active_workflow")
    if active:
        msg = f"[continue_workflow] Forwarding to active workflow: {active}. (Not yet implemented)"
    else:
        msg = "[continue_workflow] No active workflow to continue. Please start a new request."
    return {"messages": [AIMessage(content=msg)]}


async def pr_workflow_entry_node(state: MainGraphState) -> dict:
    """Entry point for infrastructure provisioning via PR — invokes the PR workflow subgraph."""

    # Build initial PRWorkflowState from outer graph state
    pr_state = {
        "messages": state.get("messages", []),
        "user_id": state.get("user_id", ""),
        "thread_id": state.get("thread_id", ""),
        "turn_index": 1,
        "resource_queue": [],
        "pending_resource_ids": [],
        "completed_resource_ids": [],
        "blocked_resource_ids": [],
        "dropped_resource_ids": [],
        "current_batch": [],
        "active_resource_id": None,
        "response_sections": {},
        "suggested_options": {},
    }

    # Invoke subgraph
    pr_graph = build_pr_workflow_graph()
    result = await pr_graph.ainvoke(pr_state)

    # Extract response messages from subgraph
    result_messages = result.get("messages", [])
    # Get only the AI messages added by the subgraph (not the input messages)
    ai_responses = [m for m in result_messages if isinstance(m, AIMessage)]
    last_response = ai_responses[-1] if ai_responses else AIMessage(
        content="PR workflow started but produced no response."
    )

    return {
        "messages": [last_response],
        "active_workflow": "pr_workflow",
    }


def qa_handler_node(state: MainGraphState) -> dict:
    """Answer knowledge and documentation questions."""
    return {
        "messages": [
            AIMessage(
                content=(
                    "I'm not able to help with Q&A queries right now. "
                    "This feature is coming soon. Please check back later "
                    "or reach out to your platform team directly."
                )
            )
        ]
    }


def ticket_handler_node(state: MainGraphState) -> dict:
    """Create a support ticket in Jira."""
    return {
        "messages": [
            AIMessage(
                content=(
                    "I'm not able to help with support ticket creation right now. "
                    "This feature is coming soon. Please create a ticket manually "
                    "or contact your platform team for assistance."
                )
            )
        ]
    }


def status_handler_node(state: MainGraphState) -> dict:
    """Check status of prior requests or PRs."""
    return {
        "messages": [
            AIMessage(
                content=(
                    "I'm not able to help with status checks right now. "
                    "This feature is coming soon. Please check your PR "
                    "status directly in GitHub."
                )
            )
        ]
    }
