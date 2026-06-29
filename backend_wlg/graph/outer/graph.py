from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend_wlg.graph.outer.nodes.handlers import (
    continue_workflow_node,
    handle_clarify_node,
    handle_fallback_node,
    pr_workflow_entry_node,
    qa_handler_node,
    status_handler_node,
    ticket_handler_node,
)
from backend_wlg.graph.outer.nodes.intent_classifier import intent_classifier_node
from backend_wlg.graph.outer.state import MainGraphState

# Maps classifier route values → graph node names
ROUTE_TO_NODE = {
    "continue_workflow": "continue_workflow",
    "pr_workflow": "pr_workflow_entry",
    "qa": "qa_handler",
    "support_ticket": "ticket_handler",
    "status_check": "status_handler",
    "clarify": "handle_clarify",
    "fallback": "handle_fallback",
}


def route_by_classification(state: MainGraphState) -> str:
    """Conditional edge: read classifier output and pick the next node."""
    classification = state.get("classification")
    if not classification:
        return "handle_fallback"

    route = classification.get("route", "fallback")
    is_switch = classification.get("is_intent_switch", False)

    # Intent switches need user confirmation — but NOT if the user is
    # staying in the same workflow type (e.g., adding resources to pr_workflow)
    active_workflow = state.get("active_workflow")
    if is_switch and route not in ("continue_workflow", "clarify", "fallback"):
        if active_workflow != route:
            return "handle_clarify"

    return ROUTE_TO_NODE.get(route, "handle_fallback")


def build_main_graph() -> StateGraph:
    """Assemble and compile the top-level intent routing graph."""
    graph = StateGraph(MainGraphState)

    # --- nodes ---
    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("continue_workflow", continue_workflow_node)
    graph.add_node("pr_workflow_entry", pr_workflow_entry_node)
    graph.add_node("qa_handler", qa_handler_node)
    graph.add_node("ticket_handler", ticket_handler_node)
    graph.add_node("status_handler", status_handler_node)
    graph.add_node("handle_clarify", handle_clarify_node)
    graph.add_node("handle_fallback", handle_fallback_node)

    # --- edges ---
    graph.add_edge(START, "intent_classifier")

    graph.add_conditional_edges(
        "intent_classifier",
        route_by_classification,
        {
            "continue_workflow": "continue_workflow",
            "pr_workflow_entry": "pr_workflow_entry",
            "qa_handler": "qa_handler",
            "ticket_handler": "ticket_handler",
            "status_handler": "status_handler",
            "handle_clarify": "handle_clarify",
            "handle_fallback": "handle_fallback",
        },
    )

    # All handler nodes terminate the graph invocation
    for node_name in ROUTE_TO_NODE.values():
        graph.add_edge(node_name, END)

    # --- compile ---
    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)
