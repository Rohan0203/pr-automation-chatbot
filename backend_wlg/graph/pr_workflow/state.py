from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ResourceWorkItem(TypedDict):
    """Tracks a single resource through the collection pipeline."""

    resource_id: str                     # e.g. "r1", "r2"
    resource_type: str                   # "s3", "glue_db", "iam", etc.
    operation: str                       # "create"
    status: str                          # "pending" | "collecting" | "completed" | "blocked" | "dropped"
    extracted_fields: dict               # user-provided values
    derived_fields: dict                 # rule-derived values
    final_fields: dict                   # merged confirmed values
    missing_fields: list[str]            # what's still needed
    field_attempts: dict[str, int]       # retry count per field
    status_reason: str | None            # why blocked/dropped
    context_binding: str | None          # which resource doc is bound


class PRWorkflowState(TypedDict):
    """State for the PR workflow subgraph."""

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    thread_id: str
    turn_index: int

    # Resource tracking
    resource_queue: list[ResourceWorkItem]
    pending_resource_ids: list[str]
    completed_resource_ids: list[str]
    blocked_resource_ids: list[str]
    dropped_resource_ids: list[str]

    # Current turn
    current_batch: list[str]             # resource_ids being processed this turn
    active_resource_id: str | None       # which one is in the per-resource loop

    # Response building
    response_sections: dict              # aggregated response parts
    suggested_options: dict              # field → option list from context_option_builder
