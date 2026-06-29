from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from backend_wlg.graph.outer.models import ClassifierOutput
from backend_wlg.graph.outer.state import MainGraphState
from backend_wlg.services.llm import get_llm

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

_classifier_llm = None


def _get_classifier_llm():
    """Lazily build the classifier LLM with structured output."""
    global _classifier_llm
    if _classifier_llm is None:
        _classifier_llm = get_llm().with_structured_output(ClassifierOutput)
    return _classifier_llm


def _build_context_message(state: MainGraphState) -> str:
    """Build the context block that gives the classifier situational awareness."""
    messages = state.get("messages", [])
    active_workflow = state.get("active_workflow")
    last_question = state.get("last_agent_question")

    prior = messages[-6:-1] if len(messages) > 1 else []
    conversation_lines = []
    for msg in prior:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        conversation_lines.append(f"{role}: {content}")
    conversation_summary = "\n".join(conversation_lines) if conversation_lines else "No prior messages"

    latest = messages[-1].content if messages else ""

    return (
        f"Active Workflow: {active_workflow or 'None (idle)'}\n"
        f"Last Agent Question: {last_question or 'None'}\n"
        f"\nRecent Conversation:\n{conversation_summary}\n"
        f"\nLatest User Message: {latest}"
    )


async def intent_classifier_node(state: MainGraphState) -> dict:
    """Classify the user's latest message into a route."""
    system_prompt = (PROMPTS_DIR / "intent_classifier.md").read_text(encoding="utf-8")
    context_message = _build_context_message(state)

    result: ClassifierOutput = await _get_classifier_llm().ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context_message),
    ])

    return {"classification": result.model_dump()}
