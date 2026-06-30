"""
Orchestrator — pure code state machine.
Routes messages based on (session.mode, resource statuses).
Makes targeted LLM calls, updates state, returns response.
"""
import logging

from app.models import Session, SessionMode, Resource, ResourceStatus
from app.collection.spec_registry import get_field_specs, get_all_field_specs, get_supported_resources
from app.collection.planner import get_askable_fields, is_collection_complete, build_collection_plan
from app.collection.derivation_context_loader import load_derivation_context
from app.llm.intent_parser import detect_intent_and_extract, extract_fields
from app.llm.derivation import derive_resource_fields
from app.llm.question_formatter import format_question
from app.persistence import init_session, flush, end_session

MAX_RETRIES = 3
logger = logging.getLogger(__name__)

# Display names for resource types (driven by YAML specs)
_RESOURCE_DISPLAY_NAMES = {
    "s3": "S3 bucket",
    "glue_db": "Glue database",
    "iam": "IAM role",
    "resource_policy": "Resource policy",
    "smus_role": "SMUS role",
    "smus_project": "SMUS project",
}


def _supported_resources_text() -> str:
    """Build a comma-separated display string of all supported resource types."""
    supported = get_supported_resources()
    names = [_RESOURCE_DISPLAY_NAMES.get(r, r) for r in supported]
    return ", ".join(names)


async def process_message(session: Session, message: str) -> str:
    """
    Main entry point. Takes user message, routes by state, returns bot response.
    """
    session.add_message("user", message)

    if session.mode == SessionMode.IDLE:
        response = await _handle_idle(session, message)
    elif session.mode == SessionMode.WORKING:
        # If all non-terminal resources are in CONFIRMING, handle confirmation
        pending_states = [r.status for r in session.resources if r.status not in (ResourceStatus.DONE, ResourceStatus.DROPPED)]
        if pending_states and all(s == ResourceStatus.CONFIRMING for s in pending_states):
            response = await _handle_confirming(session, message)
        else:
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
        return f"I can help you create: {_supported_resources_text()}. Just tell me what you need — for example: 'I need an S3 bucket and Glue DB in dev for AGTR'."

    if intent == "unsupported":
        return f"I currently support: {_supported_resources_text()}. Let me know if you need one of those."

    # Create resources with unique IDs
    for rtype in resources:
        if rtype in get_supported_resources():
            count = sum(1 for r in session.resources if r.resource_type == rtype)
            rid = f"{rtype}_{count}"
            session.resources.append(Resource(resource_id=rid, resource_type=rtype, status=ResourceStatus.COLLECTING))

    if not session.resources:
        return f"I couldn't identify a supported resource type. I support: {_supported_resources_text()}."

    session.mode = SessionMode.WORKING

    # Pre-fill extracted values into matching resources
    if extracted:
        _apply_extracted_fields(session, extracted)

    # Persist: session created with resources
    await init_session(session)
    await flush(session)

    # Start collection loop — ask across all resources
    return await _run_collection_cycle(session)


async def _handle_working(session: Session, message: str) -> str:
    """In collection mode — extract fields from user response for all resources."""
    # Build collection plan across all resources (include BLOCKED so skip/drop can reach them)
    active_resources = [r for r in session.resources if r.status in (ResourceStatus.COLLECTING, ResourceStatus.BLOCKED)]
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

    # Build known fields per resource (keyed by resource_id)
    known_fields = {r.resource_id: r.fields.copy() for r in active_resources}

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

    if intent == "skip":
        # Skip blocked fields — mark as None (deliberately skipped), unblock resource
        for r in active_resources:
            if r.status == ResourceStatus.BLOCKED:
                for field_name, count in list(r.retry_counts.items()):
                    if count >= MAX_RETRIES:
                        r.fields[field_name] = None  # sentinel: skipped
                        del r.retry_counts[field_name]
                r.status = ResourceStatus.COLLECTING
        return await _run_collection_cycle(session)

    if intent == "edit":
        # Remove extracted field names from resources so they get re-asked
        fields_to_edit = list(extracted.keys())
        if not fields_to_edit:
            return "Which field would you like to change? Tell me the field name and new value."
        for r in active_resources:
            for fname in fields_to_edit:
                r.fields.pop(fname, None)
                r.retry_counts.pop(fname, None)
        return await _run_collection_cycle(session)

    # Apply valid extractions to the right resources
    errors = {}
    for field_name, info in extracted.items():
        actual_field = field_name
        applies_to = info.get("applies_to", "all")

        # Clean up field name if it has resource_id suffix (e.g. "intake_id_s3_0")
        for r in active_resources:
            if field_name.endswith(f"_{r.resource_id}"):
                actual_field = field_name[: -(len(r.resource_id) + 1)]
                applies_to = r.resource_id
                break

        if info.get("valid", False):
            # Apply to matching resources
            for r in active_resources:
                if applies_to == "all" or applies_to == r.resource_id:
                    spec_names = {s.name for s in get_field_specs(r.resource_type)}
                    if actual_field in spec_names:
                        r.fields[actual_field] = info["value"]
                        r.retry_counts.pop(actual_field, None)
        else:
            issue = info.get("issue", "Invalid value")
            errors[actual_field] = issue
            for r in active_resources:
                if applies_to == "all" or applies_to == r.resource_id:
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
    # Check completeness for each resource → derive → move to CONFIRMING
    confirming_messages = []
    for r in session.resources:
        if r.status == ResourceStatus.COLLECTING and is_collection_complete(r):
            derivation = await _derive_fields_for_resource(r)
            r.status = ResourceStatus.CONFIRMING
            derived_fields = derivation.get("derived_fields", [])
            unresolved = derivation.get("unresolved", [])

            if derived_fields:
                confirming_messages.append(
                    f"✓ {r.resource_id} — fields collected. Derived: {', '.join(derived_fields)}"
                )
            else:
                confirming_messages.append(f"✓ {r.resource_id} — all fields collected!")

    # Persist if any resource moved to confirming
    if confirming_messages:
        await flush(session)

    # Check if anything still needs collection
    active_resources = [r for r in session.resources if r.status == ResourceStatus.COLLECTING]
    confirming_resources = [r for r in session.resources if r.status == ResourceStatus.CONFIRMING]

    # If nothing left to collect and we have confirming resources, show confirmation
    if not active_resources and confirming_resources:
        prefix = "\n".join(confirming_messages) + "\n\n" if confirming_messages else ""
        return prefix + await _build_confirmation_message(confirming_resources)

    # If nothing active at all
    if not active_resources and not confirming_resources:
        session.mode = SessionMode.IDLE
        await end_session(session)
        return "All resources complete! Ready for YAML generation."

    # Build unified collection plan for remaining
    plan = build_collection_plan(active_resources)

    if plan.all_done:
        # Edge case — planner says done but status wasn't caught above
        for r in active_resources:
            r.status = ResourceStatus.CONFIRMING
        return await _build_confirmation_message(
            [r for r in session.resources if r.status == ResourceStatus.CONFIRMING]
        )

    # Build known fields for context (keyed by resource_id)
    known_fields = {r.resource_id: r.fields.copy() for r in active_resources}

    # Format unified question
    question = await format_question(plan=plan, known_fields=known_fields, errors=errors)

    prefix = "\n".join(confirming_messages) + "\n\n" if confirming_messages else ""
    return prefix + question


def _apply_extracted_fields(session: Session, extracted: dict):
    """Apply extracted fields from intent detection to matching resources."""
    for resource in session.resources:
        specs = get_field_specs(resource.resource_type)
        spec_names = {s.name for s in specs if not s.derivable}
        for field_name, value in extracted.items():
            if field_name in spec_names:
                resource.fields[field_name] = value


async def _derive_fields_for_resource(resource: Resource) -> dict:
    """Derive missing derivable fields after required collection completes."""
    specs = get_field_specs(resource.resource_type)
    missing_derivable = [
        spec.name
        for spec in specs
        if spec.derivable and spec.name not in resource.fields
    ]

    if not missing_derivable:
        return {"derived_fields": [], "unresolved": []}

    try:
        selected_context = load_derivation_context(resource.resource_type, missing_derivable)
        result = await derive_resource_fields(resource, selected_context)
    except Exception as exc:
        logger.exception("Derivation failed for %s: %s", resource.resource_type, exc)
        return {"derived_fields": [], "unresolved": missing_derivable}

    derived_values = result.get("derived", {})
    for field_name, value in derived_values.items():
        resource.fields[field_name] = value

    return {
        "derived_fields": sorted(derived_values.keys()),
        "unresolved": result.get("unresolved", []),
    }


async def _handle_confirming(session: Session, message: str) -> str:
    """Handle user response during confirmation review (edit or confirm)."""
    from app.llm.client import chat_json

    confirming_resources = [r for r in session.resources if r.status == ResourceStatus.CONFIRMING]

    # Quick intent detection for confirm/edit/drop
    intent_prompt = (
        "The user is reviewing their resource configuration. Determine their intent.\n"
        "Return JSON: {\"intent\": \"confirm\"|\"edit\"|\"drop\", \"fields\": [\"field_name\", ...], "
        "\"values\": {\"field_name\": \"new_value\"}, \"applies_to\": \"all\"|\"resource_id\"}\n"
        "- confirm: user approves the configuration\n"
        "- edit: user wants to change field(s) — extract which fields and new values if given\n"
        "- drop: user wants to abandon\n"
        f"\nResources being confirmed: {[r.resource_id for r in confirming_resources]}\n"
        f"User message: {message}"
    )
    result = await chat_json(intent_prompt, message)

    intent = result.get("intent", "confirm")

    if intent == "confirm":
        for r in confirming_resources:
            r.status = ResourceStatus.DONE
        session.mode = SessionMode.IDLE
        await end_session(session)
        done_list = ", ".join(r.resource_id for r in confirming_resources)
        return f"✓ Confirmed! {done_list} finalized. Ready for YAML generation."

    if intent == "drop":
        for r in confirming_resources:
            r.status = ResourceStatus.DROPPED
        session.mode = SessionMode.IDLE
        return "Resources dropped. Let me know if you want to start again."

    if intent == "edit":
        fields_to_edit = result.get("fields", [])
        new_values = result.get("values", {})
        applies_to = result.get("applies_to", "all")

        if not fields_to_edit:
            return "Which field would you like to change? Tell me the field name and new value."

        # Determine which resources to edit
        targets = confirming_resources
        if applies_to != "all":
            targets = [r for r in confirming_resources if r.resource_id == applies_to]

        for r in targets:
            specs = get_field_specs(r.resource_type)
            derivable_names = {s.name for s in specs if s.derivable}

            has_collected_edit = False
            for fname in fields_to_edit:
                if fname in derivable_names:
                    # Editing a derived field — just overwrite or clear for re-derivation
                    if fname in new_values:
                        r.fields[fname] = new_values[fname]
                    else:
                        r.fields.pop(fname, None)
                else:
                    # Editing a collected field — need to re-collect and re-derive
                    has_collected_edit = True
                    if fname in new_values:
                        r.fields[fname] = new_values[fname]
                    else:
                        r.fields.pop(fname, None)

            if has_collected_edit:
                # Clear all derived fields (they depend on collected values)
                for spec in specs:
                    if spec.derivable:
                        r.fields.pop(spec.name, None)
                r.status = ResourceStatus.COLLECTING

        # If any resource went back to COLLECTING, run collection cycle
        collecting = [r for r in session.resources if r.status == ResourceStatus.COLLECTING]
        if collecting:
            return await _run_collection_cycle(session)

        # Otherwise still in CONFIRMING — re-derive edited derived fields and re-show
        for r in targets:
            if r.status == ResourceStatus.CONFIRMING:
                await _derive_fields_for_resource(r)

        return await _build_confirmation_message(
            [r for r in session.resources if r.status == ResourceStatus.CONFIRMING]
        )

    return await _build_confirmation_message(confirming_resources)


async def _build_confirmation_message(resources: list[Resource]) -> str:
    """Build a review message showing all fields for CONFIRMING resources."""
    from app.llm.prompts import CONFIRM_PROMPT
    from app.llm.client import chat

    specs_by_type: dict[str, set] = {}
    for r in resources:
        if r.resource_type not in specs_by_type:
            specs = get_field_specs(r.resource_type)
            specs_by_type[r.resource_type] = {s.name for s in specs if s.derivable}

    lines = []
    for r in resources:
        derivable_names = specs_by_type[r.resource_type]
        lines.append(f"\n[{r.resource_id} ({r.resource_type})]")
        for fname, value in r.fields.items():
            source = "derived" if fname in derivable_names else "collected"
            lines.append(f"  {fname}: {value}  ({source})")

    context = "\n".join(lines)
    prompt = CONFIRM_PROMPT.format(context=context)
    return await chat(prompt, "Generate the confirmation message for the user.")
