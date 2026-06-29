"""Response aggregator — builds unified user-facing response from all resource states."""
from __future__ import annotations

from langchain_core.messages import AIMessage

from backend_wlg.context.registry import get_supported_resource_types
from backend_wlg.graph.pr_workflow.state import PRWorkflowState

# Friendly display names for resource types
_DISPLAY_NAMES = {
    "s3": "S3 Bucket",
    "glue_db": "Glue Database",
    "iam": "IAM Role",
    "resource_policy": "Resource Policy",
    "smus_project": "SMUS Project",
    "smus_role": "SMUS Role",
}


async def response_aggregator_node(state: PRWorkflowState) -> dict:
    """Build one response summarizing all resource states for this turn."""
    resource_queue = state.get("resource_queue", [])
    current_batch = state.get("current_batch", [])

    if not resource_queue:
        return {
            "messages": [AIMessage(content=(
                "I couldn't identify any specific resources to provision from your message. "
                "Could you clarify what you'd like to create? "
                "I support: S3 buckets, Glue databases, IAM roles, Resource Policies, "
                "SMUS Projects, and SMUS Roles."
            ))],
        }

    # Categorize resources
    accepted = []
    out_of_scope = []
    completed = []
    blocked = []

    for item in resource_queue:
        status = item["status"]
        display = _DISPLAY_NAMES.get(item["resource_type"], item["resource_type"])
        if status == "out_of_scope":
            out_of_scope.append(item)
        elif status == "completed":
            completed.append(item)
        elif status == "blocked":
            blocked.append(item)
        elif status in ("pending", "collecting"):
            accepted.append(item)

    # Build response sections
    sections: list[str] = []

    # Accepted resources
    if accepted:
        lines = [f"I'll collect information for {len(accepted)} resource{'s' if len(accepted) > 1 else ''}:"]
        for item in accepted:
            display = _DISPLAY_NAMES.get(item["resource_type"], item["resource_type"])
            lines.append(f"  📋 **{display}** — {item['operation']}")
        lines.append("")
        lines.append("I'll need some details for each resource to proceed. (Field collection coming next)")
        sections.append("\n".join(lines))

    # Out of scope
    if out_of_scope:
        supported_list = ", ".join(
            _DISPLAY_NAMES.get(rt, rt) for rt in get_supported_resource_types()
        )
        lines = []
        for item in out_of_scope:
            reason = item.get("status_reason", item["resource_type"])
            lines.append(f"  ⚠️ **Not supported:** {reason}")
        lines.append(f"  Supported resources: {supported_list}")
        sections.append("\n".join(lines))

    # Completed
    if completed:
        lines = ["✅ **Completed:**"]
        for item in completed:
            display = _DISPLAY_NAMES.get(item["resource_type"], item["resource_type"])
            lines.append(f"  - {display}")
        sections.append("\n".join(lines))

    # Blocked
    if blocked:
        lines = ["🚫 **Blocked:**"]
        for item in blocked:
            display = _DISPLAY_NAMES.get(item["resource_type"], item["resource_type"])
            reason = item.get("status_reason", "unknown reason")
            lines.append(f"  - {display}: {reason}")
        sections.append("\n".join(lines))

    response_text = "\n\n".join(sections)

    return {
        "messages": [AIMessage(content=response_text)],
        "response_sections": {
            "accepted": [i["resource_id"] for i in accepted],
            "out_of_scope": [i["resource_id"] for i in out_of_scope],
            "completed": [i["resource_id"] for i in completed],
            "blocked": [i["resource_id"] for i in blocked],
        },
    }
