from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MainGraphState(TypedDict):
    """Top-level graph state for the intent classification layer."""

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    thread_id: str

    # Workflow tracking
    active_workflow: str | None
    last_agent_question: str | None
    workflow_paused: bool

    # Classifier output (stored as dict from ClassifierOutput.model_dump())
    classification: dict | None
