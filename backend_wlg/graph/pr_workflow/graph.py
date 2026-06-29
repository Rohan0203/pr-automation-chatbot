"""PR Workflow subgraph — resource provisioning pipeline.

Phase 1 flow:
  START → resource_batch_planner → resource_scheduler → response_aggregator → END

Later phases will add per-resource collection loop between scheduler and aggregator.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend_wlg.graph.pr_workflow.nodes.batch_planner import resource_batch_planner_node
from backend_wlg.graph.pr_workflow.nodes.response_aggregator import response_aggregator_node
from backend_wlg.graph.pr_workflow.nodes.scheduler import resource_scheduler_node
from backend_wlg.graph.pr_workflow.state import PRWorkflowState


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_pr_workflow_graph():
    """Assemble and compile the PR workflow subgraph."""
    graph = StateGraph(PRWorkflowState)

    # --- Phase 1 nodes ---
    graph.add_node("resource_batch_planner", resource_batch_planner_node)
    graph.add_node("resource_scheduler", resource_scheduler_node)
    graph.add_node("response_aggregator", response_aggregator_node)

    # --- Edges ---
    # START → parse request into work items
    graph.add_edge(START, "resource_batch_planner")
    # → schedule which ones to process
    graph.add_edge("resource_batch_planner", "resource_scheduler")
    # → build unified response (Phase 2+ will add collection loop between scheduler and aggregator)
    graph.add_edge("resource_scheduler", "response_aggregator")
    # → done
    graph.add_edge("response_aggregator", END)

    return graph.compile()
