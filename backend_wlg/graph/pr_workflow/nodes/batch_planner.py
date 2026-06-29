"""Batch planner node — LLM parses user request into ResourceWorkItems."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend_wlg.context.registry import get_supported_resource_types
from backend_wlg.graph.pr_workflow.state import PRWorkflowState, ResourceWorkItem
from backend_wlg.services.llm import get_llm

# ---------------------------------------------------------------------------
# Structured output model
# ---------------------------------------------------------------------------

SUPPORTED_TYPES = Literal["s3", "glue_db", "iam", "resource_policy", "smus_project", "smus_role", "unsupported"]


class ParsedResource(BaseModel):
    """A single resource parsed from the user message."""

    resource_type: SUPPORTED_TYPES
    operation: str = "create"
    user_summary: str = Field(description="Short description of what user wants for this resource")


class BatchPlannerOutput(BaseModel):
    """Structured output from batch planner LLM call."""

    resources: list[ParsedResource] = Field(
        description="List of individual resource requests parsed from the user message. "
        "Empty list if message is too vague to determine specific resources."
    )


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "batch_planner.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------


async def resource_batch_planner_node(state: PRWorkflowState) -> dict:
    """Parse user request into ResourceWorkItems via LLM."""

    # Get the last human message
    messages = state.get("messages", [])
    last_human_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human_msg = msg.content
            break

    if not last_human_msg:
        return {}

    # Build LLM call
    system_prompt = _load_prompt()
    llm = get_llm().with_structured_output(BatchPlannerOutput)

    result: BatchPlannerOutput = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=last_human_msg),
    ])

    # Convert parsed resources into ResourceWorkItems
    resource_queue: list[ResourceWorkItem] = []
    pending_ids: list[str] = []

    for idx, parsed in enumerate(result.resources, start=1):
        resource_id = f"r{idx}"
        item: ResourceWorkItem = {
            "resource_id": resource_id,
            "resource_type": parsed.resource_type,
            "operation": parsed.operation,
            "status": "out_of_scope" if parsed.resource_type == "unsupported" else "pending",
            "extracted_fields": {},
            "derived_fields": {},
            "final_fields": {},
            "missing_fields": [],
            "field_attempts": {},
            "status_reason": f"Unsupported: {parsed.user_summary}" if parsed.resource_type == "unsupported" else None,
            "context_binding": None,
        }
        resource_queue.append(item)
        if parsed.resource_type != "unsupported":
            pending_ids.append(resource_id)

    return {
        "resource_queue": resource_queue,
        "pending_resource_ids": pending_ids,
        "completed_resource_ids": [],
        "blocked_resource_ids": [],
        "dropped_resource_ids": [],
    }
