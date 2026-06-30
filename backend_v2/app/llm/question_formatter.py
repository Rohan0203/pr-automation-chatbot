"""
LLM format function — builds helpful question messages for the user.
"""
from app.llm.client import chat
from app.llm.prompts import FORMAT_PROMPT
from app.collection.context_builder import build_format_context
from app.collection.planner import CollectionPlan


async def format_question(
    plan: CollectionPlan,
    known_fields: dict[str, dict],
    errors: dict | None = None,
) -> str:
    """
    Build a natural language question asking user for missing fields across ALL resources.
    Returns: formatted message string.
    """
    context = build_format_context(plan, known_fields, errors or {})
    system_prompt = FORMAT_PROMPT.format(context=context)
    result = await chat(system_prompt, "Generate the question message for the user.")
    return result
