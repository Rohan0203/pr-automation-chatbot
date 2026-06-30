"""
LLM parse functions — intent detection + field extraction.
"""
from app.llm.client import chat_json
from app.llm.prompts import INTENT_AND_EXTRACT_PROMPT, EXTRACT_PROMPT
from app.collection.context_builder import build_extraction_context
from app.collection.planner import CollectionPlan
from app.models import FieldSpec


async def detect_intent_and_extract(message: str, all_field_specs: dict[str, list[FieldSpec]]) -> dict:
    """
    First message — detect which resources the user wants + extract any values.
    Returns: {"resources": [...], "extracted_fields": {...}, "intent": "create"|"general_question"|"unsupported"}
    """
    lines = []
    for rtype, specs in all_field_specs.items():
        lines.append(f"\n{rtype} fields:")
        for spec in specs:
            if spec.derivable:
                continue
            parts = [f"  - {spec.name}: {spec.description}"]
            if spec.options:
                parts.append(f" [options: {', '.join(spec.options)}]")
            lines.append("".join(parts))

    field_context = "\n".join(lines)
    system_prompt = INTENT_AND_EXTRACT_PROMPT.format(field_context=field_context)

    result = await chat_json(system_prompt, message)
    return result


async def extract_fields(
    message: str,
    plan: CollectionPlan,
    known_fields: dict[str, dict],
    previous_bot_message: str,
) -> dict:
    """
    During collection — extract field values from user response for ALL resources.
    Returns: {"extracted": {"field": {"value": ..., "valid": bool, "applies_to": ..., "issue": ...}}, "intent": "answer"|...}
    """
    context = build_extraction_context(plan, known_fields)
    system_prompt = EXTRACT_PROMPT.format(
        context=context,
        previous_bot_message=previous_bot_message,
        user_message=message,
    )

    result = await chat_json(system_prompt, message)
    return result
