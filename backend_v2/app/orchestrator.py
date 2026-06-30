"""
Orchestrator — pure code state machine.
Routes messages based on (session.mode, resource statuses).
Makes targeted LLM calls, updates state, returns response.
"""
from app.models import Session, SessionMode, Resource, ResourceStatus
from app.collection.spec_registry import get_field_specs, get_all_field_specs, get_supported_resources
from app.collection.planner import get_askable_fields, is_collection_complete, build_collection_plan
from app.llm.intent_parser import detect_intent_and_extract, extract_fields
from app.llm.question_formatter import format_question

MAX_RETRIES = 3


async def process_message(session: Session, message: str) -> str:
    """
    Main entry point. Takes user message, routes by state, returns bot response.
    """
    session.add_message("user", message)

    if session.mode == SessionMode.IDLE:
        response = await _handle_idle(session, message)
    elif session.mode == SessionMode.WORKING:
        response = await _handle_working(session, message)
    else:
        response = "Something went wrong. Type /reset to start over."

    session.add_message("assistant", response)
    return response


async def _handle_idle(session: Session, message: str) -> str:
    """User hasn't started anything yet. Detect intent."""
    result = await detect_intent_and_extract(message, get_all_field_specs())

    intent = result.get("intent", "general_question")
    resources = result.get("resources", [])
    extracted = result.get("extracted_fields", {})

    if intent == "general_question" or not resources:
        return "I can help you create S3 buckets and Glue databases. Just tell me what you need — for example: 'I need an S3 bucket and Glue DB in dev for AGTR'."

    if intent == "unsupported":
        return "I currently only support S3 buckets and Glue databases. Let me know if you need one of those."

    # Create resources
    for rtype in resources:
        if rtype in get_supported_resources():
            session.resources.append(Resource(resource_type=rtype, status=ResourceStatus.COLLECTING))

    if not session.resources:
        return "I couldn't identify a supported resource type. I support: S3 bucket, Glue database."

    session.mode = SessionMode.WORKING

    # Pre-fill extracted values into matching resources
    if extracted:
        _apply_extracted_fields(session, extracted)

    # Start collection loop — ask across all resources
    return await _run_collection_cycle(session)


async def _handle_working(session: Session, message: str) -> str:
    """In collection mode — extract fields from user response for all resources."""
    # Build collection plan across all resources
    active_resources = [r for r in session.resources if r.status == ResourceStatus.COLLECTING]
    if not active_resources:
        session.mode = SessionMode.IDLE
        return "All resources are done!"

    plan = build_collection_plan(active_resources)

    # Get the last bot message for context
    previous_bot = ""
    for msg in reversed(session.history):
        if msg["role"] == "assistant":
            previous_bot = msg["content"]
            break

    # Build known fields per resource
    known_fields = {r.resource_type: r.fields.copy() for r in active_resources}

    # Extract fields from user message
    result = await extract_fields(message, plan, known_fields, previous_bot)

    intent = result.get("intent", "answer")
    extracted = result.get("extracted", {})

    # Handle non-answer intents
    if intent == "drop":
        for r in active_resources:
            r.status = ResourceStatus.DROPPED
        session.mode = SessionMode.IDLE
        return "Resources dropped. Let me know if you want to start again."

    if intent == "question":
        return "I'm here to help! Let me know the field values when you're ready. " \
               "If you want to abandon, say 'drop'."

    # Apply valid extractions to the right resources
    errors = {}
    for field_name, info in extracted.items():
        # Handle per-resource field names like "intake_id_s3"
        actual_field = field_name
        applies_to = info.get("applies_to", "all")

        # Clean up field name if it has resource suffix
        for rtype in get_supported_resources():
            if field_name.endswith(f"_{rtype}"):
                actual_field = field_name[: -(len(rtype) + 1)]
                applies_to = rtype
                break

        if info.get("valid", False):
            # Apply to matching resources
            for r in active_resources:
                if applies_to == "all" or applies_to == r.resource_type:
                    # Only apply if this resource actually has this field
                    spec_names = {s.name for s in get_field_specs(r.resource_type)}
                    if actual_field in spec_names:
                        r.fields[actual_field] = info["value"]
                        r.retry_counts.pop(actual_field, None)
        else:
            issue = info.get("issue", "Invalid value")
            errors[actual_field] = issue
            for r in active_resources:
                if applies_to == "all" or applies_to == r.resource_type:
                    r.retry_counts[actual_field] = r.retry_counts.get(actual_field, 0) + 1

    # Check for blocked fields (retry threshold exceeded)
    for r in active_resources:
        for field_name, count in r.retry_counts.items():
            if count >= MAX_RETRIES:
                r.status = ResourceStatus.BLOCKED
                return f"I'm having trouble with '{field_name}' for {r.resource_type} after {MAX_RETRIES} attempts. " \
                       f"Say 'skip' to move on or 'drop' to abandon."

    # Run collection cycle
    return await _run_collection_cycle(session, errors)


async def _run_collection_cycle(session: Session, errors: dict | None = None) -> str:
    """Check what's missing across ALL resources, ask in one unified message."""
    # Check completeness for each resource
    done_messages = []
    for r in session.resources:
        if r.status == ResourceStatus.COLLECTING and is_collection_complete(r):
            r.status = ResourceStatus.DONE
            done_messages.append(f"✓ {r.resource_type} — all fields collected!")

    # Check if everything is done
    active_resources = [r for r in session.resources if r.status == ResourceStatus.COLLECTING]
    if not active_resources:
        session.mode = SessionMode.IDLE
        prefix = "\n".join(done_messages) + "\n\n" if done_messages else ""
        return prefix + "All resources complete! Ready for YAML generation."

    # Build unified collection plan
    plan = build_collection_plan(active_resources)

    if plan.all_done:
        session.mode = SessionMode.IDLE
        return "All resources complete! Ready for YAML generation."

    # Build known fields for context
    known_fields = {r.resource_type: r.fields.copy() for r in active_resources}

    # Format unified question
    question = await format_question(plan=plan, known_fields=known_fields, errors=errors)

    prefix = "\n".join(done_messages) + "\n\n" if done_messages else ""
    return prefix + question


def _apply_extracted_fields(session: Session, extracted: dict):
    """Apply extracted fields from intent detection to matching resources."""
    for resource in session.resources:
        specs = get_field_specs(resource.resource_type)
        spec_names = {s.name for s in specs if not s.derivable}
        for field_name, value in extracted.items():
            if field_name in spec_names:
                resource.fields[field_name] = value
