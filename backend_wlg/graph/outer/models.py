from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """A single detected intent within a user message."""

    intent: Literal["pr_workflow", "qa", "support_ticket", "status_check"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str


class ClassifierOutput(BaseModel):
    """Structured output from the intent classifier LLM call."""

    route: Literal[
        "continue_workflow",
        "pr_workflow",
        "qa",
        "support_ticket",
        "status_check",
        "clarify",
        "fallback",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    is_intent_switch: bool = False
    reasoning: str
    intent_summary: str | None = None
    intents: list[IntentResult] | None = None
