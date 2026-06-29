"""Scheduler node — selects pending resources for this turn's processing batch."""
from __future__ import annotations

from backend_wlg.graph.pr_workflow.state import PRWorkflowState


async def resource_scheduler_node(state: PRWorkflowState) -> dict:
    """Pick schedulable resources from the queue.

    Selects all pending items that are not blocked/dropped/completed.
    Sets current_batch with the resource_ids to process this turn.
    """
    resource_queue = state.get("resource_queue", [])
    pending_ids = state.get("pending_resource_ids", [])

    # Select resources that are still pending
    schedulable = []
    for item in resource_queue:
        if item["resource_id"] in pending_ids and item["status"] == "pending":
            schedulable.append(item["resource_id"])

    return {
        "current_batch": schedulable,
        "active_resource_id": schedulable[0] if schedulable else None,
    }
