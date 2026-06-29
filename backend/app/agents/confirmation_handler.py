"""
Confirmation Handler — handles user response to YAML preview
and manages the finalization + review flow.

Extracted from the monolithic GeneratorAgent.
"""
import json
import logging
from typing import Optional

from app.agents.prompts import CONFIRMATION_PROMPT, REVIEW_FAILED_PROMPT
from app.agents.session_state import AgentState, SessionState
from app.agents.response_decorator import build_response
from app.agents.yaml_utils import generate_yaml
from app.agents.reviewer_agent import reviewer_agent
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry

logger = logging.getLogger(__name__)


async def handle_confirmation(
    session: SessionState,
    user_message: str,
    build_messages_fn,
    cancel_fn,
    after_review_fn,
) -> dict:
    """
    Handle user response to YAML preview.

    Args:
        session: current session state
        user_message: the user's message
        build_messages_fn: callable(session, prompt) -> list[dict]
        cancel_fn: callable(session) -> dict  — cancel handler
        after_review_fn: async callable(session, agent, prefix_message) -> dict
    """
    agent = session.current_agent
    msg_lower = user_message.strip().lower()

    # Fast path for simple confirm/cancel
    confirm_words = {"confirm", "yes", "approve", "looks good", "lgtm", "ok", "okay", "y", "accept"}
    cancel_words = {"cancel", "no", "discard", "abort", "stop", "quit", "n"}

    if msg_lower in confirm_words:
        logger.info("[CONFIRM] → finalize_resource (user confirmed, resource=%s)", agent.resource_type)
        return await finalize_resource(session, agent, after_review_fn)

    if msg_lower in cancel_words:
        logger.info("[CONFIRM] → cancel (user cancelled, resource=%s)", agent.resource_type)
        return cancel_fn(session)

    # LLM path for edits, questions, or ambiguous input
    resource_context = schema_registry.get_resource_context(agent.resource_type)

    prompt = CONFIRMATION_PROMPT.format(
        resource_type=agent.resource_type,
        resource_context=resource_context,
        yaml_preview=agent.generated_yaml or "",
        collected_fields=json.dumps(agent.collected_fields, indent=2),
        user_message=user_message,
    )

    messages = build_messages_fn(session, prompt)

    try:
        result = await llm_client.extract_json(messages)
    except Exception:
        return build_response(
            "Please respond with **confirm**, **edit**, or **cancel**.",
            resource_type=agent.resource_type,
            resource_status="awaiting_confirmation",
            needs_confirmation=True,
        )

    action = result.get("action", "question")
    extracted = result.get("extracted_fields", {})
    invalid = result.get("invalid_fields", {})
    message = result.get("message", "")

    logger.info("[CONFIRM] LLM confirmation action=%s, extracted=%s, invalid=%s",
                action, list(extracted.keys()) if extracted else [], list(invalid.keys()) if invalid else [])

    if action == "confirm":
        return await finalize_resource(session, agent, after_review_fn)

    if action == "cancel":
        return cancel_fn(session)

    if action == "edit":
        if extracted and isinstance(extracted, dict):
            agent.collected_fields.update(extracted)

        if invalid:
            return build_response(
                message,
                resource_type=agent.resource_type,
                resource_status="awaiting_confirmation",
                needs_confirmation=True,
            )

        # Valid edits applied — regenerate YAML
        return await generate_yaml(
            session, agent, build_messages_fn, prefix_message=message
        )

    # question or anything else
    return build_response(
        message,
        resource_type=agent.resource_type,
        resource_status="awaiting_confirmation",
        needs_confirmation=True,
    )


async def finalize_resource(
    session: SessionState,
    agent: AgentState,
    after_review_fn,
) -> dict:
    """YAML confirmed — run organizational review before PR setup."""
    # Multi-resource preview confirm: add all generated resources at once
    multi_entries = getattr(agent, "multi_preview_entries", None)
    if isinstance(multi_entries, list) and multi_entries:
        logger.info("[FINALIZE] multi-resource confirm: %d entries", len(multi_entries))
        added_count = 0
        for entry in multi_entries:
            fields = (entry.get("fields") or {}).copy()
            resource_type = entry.get("resource_type")
            resource_name = (
                fields.get("bucket_name")
                or fields.get("database_name")
                or fields.get("role_name")
                or "unknown"
            )
            intake_id = fields.get("intake_id", "unknown")

            exists = any(
                b.get("resource_type") == resource_type
                and b.get("resource_name") == resource_name
                and b.get("intake_id") == intake_id
                for b in session.batch
            )
            if exists:
                continue

            batch_agent = AgentState()
            batch_agent.resource_type = resource_type
            batch_agent.collected_fields = fields
            batch_agent.generated_yaml = entry.get("yaml")
            session.add_to_batch(batch_agent)
            added_count += 1

        session.current_agent = None
        total = len(session.batch)
        return build_response(
            f"✅ Added **{added_count}** resource configuration"
            f"{'s' if added_count != 1 else ''} to batch ({total} total).\n\n"
            f"Add another resource, **\"show batch\"**, or **\"create PR\"** to submit all.",
            resource_status="batch_prompt",
        )

    # If reviewer has rules for this resource type, run review
    if reviewer_agent.has_rules(agent.resource_type):
        logger.info("[FINALIZE] → reviewing (resource=%s, has_rules=True)", agent.resource_type)
        agent.phase = "reviewing"
        return await handle_reviewing(session, agent, after_review_fn)

    # No reviewer rules — add to batch directly
    logger.info("[FINALIZE] → batch directly (resource=%s, has_rules=False)", agent.resource_type)
    return await after_review_fn(session, agent)


async def handle_reviewing(
    session: SessionState,
    agent: AgentState,
    after_review_fn,
) -> dict:
    """Run the reviewer agent on the confirmed YAML."""
    rtype = (agent.resource_type or "unknown").upper()

    agent.review_attempts += 1
    result = await reviewer_agent.review(agent.generated_yaml, agent.resource_type)
    agent.review_result = result

    logger.info(
        "[REVIEWER] review result: passed=%s, errors=%d, warnings=%d, attempt=%d, resource=%s",
        result.passed, len(result.errors), len(result.warnings), agent.review_attempts, rtype,
    )

    show_escape_hatches = not result.passed and agent.review_attempts >= 3

    if result.passed:
        if result.warnings:
            warning_lines = []
            for i, w in enumerate(result.warnings, 1):
                fields_str = ", ".join(w.fields)
                warning_lines.append(f"{i}. **{fields_str}** — {w.root_cause}")
            warnings_text = "\n".join(warning_lines)
            msg = (
                f"✅ **{rtype} configuration review passed!**\n\n"
                f"⚠️ **Warnings (non-blocking):**\n{warnings_text}\n\n"
            )
        else:
            msg = f"✅ **{rtype} configuration passed organizational review!**\n\n"

        return await after_review_fn(session, agent, prefix_message=msg)

    # Review failed — show violations
    agent.phase = "review_failed"

    errors = result.errors
    warnings = result.warnings

    parts = [f"🔍 **{rtype} Review Complete — {'Issues Found' if errors else 'Warnings Only'}**\n"]
    parts.append(f"**Your current configuration:**\n```yaml\n{agent.generated_yaml}\n```\n")

    if errors:
        parts.append("❌ **Errors** _(must fix before PR creation)_:\n")
        for i, e in enumerate(errors, 1):
            fields_str = ", ".join(e.fields)
            rules_str = ", ".join(e.rules)
            parts.append(f"**{i}. [{rules_str}] — {fields_str}**")
            parts.append(f"{e.root_cause}\n")

            if e.fix_options:
                parts.append("**Possible fixes:**")
                for j, opt in enumerate(e.fix_options, 1):
                    label = opt.get("label", f"Option {j}")
                    changes = opt.get("changes", {})
                    change_lines = [f"  - **{k}** → {v}" for k, v in changes.items()]
                    parts.append(f"**Option {j}: {label}**")
                    parts.append("\n".join(change_lines))
                parts.append("")

    if warnings:
        parts.append("\n⚠️ **Warnings** _(non-blocking, for your awareness)_:\n")
        for i, w in enumerate(warnings, 1):
            fields_str = ", ".join(w.fields)
            parts.append(f"{i}. **{fields_str}** — {w.root_cause}")

    if show_escape_hatches:
        parts.append(
            f"\n🔄 _This configuration has been reviewed {agent.review_attempts} times. "
            f"You may **skip review** to proceed with issues noted in the PR._"
        )

    parts.append("")
    if errors:
        skip_line = (
            "\nOr type **skip review** to proceed with current config (issues will be noted in PR)."
            if show_escape_hatches else ""
        )
        parts.append(
            "**What would you like to do?**\n"
            "Pick a fix option above, or tell me your own corrected values.\n"
            f"Or type **cancel** to discard this configuration.{skip_line}"
        )
    else:
        parts.append(
            "**What would you like to do?**\n"
            "1. **Fix** — tell me the corrected values\n"
            "2. **Override** — proceed with warnings noted\n"
            "3. **Cancel** — discard this configuration"
        )

    return build_response(
        "\n\n".join(parts),
        resource_type=agent.resource_type,
        resource_status="review_failed",
        generated_yaml=agent.generated_yaml,
        review_result=result.to_dict(),
    )


async def handle_review_failed(
    session: SessionState,
    user_message: str,
    build_messages_fn,
    cancel_fn,
    after_review_fn,
    match_fix_option_fn,
) -> dict:
    """Handle user response to review violations."""
    agent = session.current_agent
    msg_lower = user_message.strip().lower()

    cancel_words = {"cancel", "discard", "abort", "stop", "quit", "no", "n"}
    override_words = {"override", "proceed anyway", "skip review", "force", "ignore"}

    if msg_lower in cancel_words:
        return cancel_fn(session)

    if msg_lower in override_words or msg_lower.startswith("override"):
        if agent.review_result and agent.review_result.errors:
            return build_response(
                "❌ Cannot override — there are **error-level violations** that must be fixed first.\n\n"
                "Please fix the errors, or cancel the configuration.",
                resource_type=agent.resource_type,
                resource_status="review_failed",
                generated_yaml=agent.generated_yaml,
                review_result=agent.review_result.to_dict() if agent.review_result else None,
            )
        return await after_review_fn(
            session, agent,
            prefix_message="⚠️ Proceeding with warnings noted. They will be included in the PR description.\n\n",
        )

    skip_words = {"skip", "skip this", "skip this one", "skip resource"}
    if msg_lower in skip_words:
        session.current_agent = None
        batch_count = len(session.batch)
        if batch_count > 0:
            return build_response(
                f"Skipped. Your batch still has {batch_count} resource{'s' if batch_count != 1 else ''}.\n"
                f"Add another resource, or **\"create PR\"** to submit.",
                resource_status="batch_prompt",
            )
        return build_response("Resource skipped. Let me know if you'd like to start over.")

    # Option shortcut: "option 1", "1", etc.
    option_match = match_fix_option_fn(msg_lower, agent)
    if option_match:
        agent.collected_fields.update(option_match)
        agent.phase = "collecting"
        applied = ", ".join(f"**{k}**" for k in option_match)
        return await generate_yaml(
            session, agent, build_messages_fn,
            prefix_message=f"Applied fix: updated {applied}. Regenerating YAML...",
        )

    # LLM path
    violations_text = ""
    if agent.review_result:
        lines = []
        for v in agent.review_result.errors:
            fields_str = ", ".join(v.fields)
            rules_str = ", ".join(v.rules)
            lines.append(f"- [ERROR] [{rules_str}] {fields_str}: {v.root_cause}")
            for j, opt in enumerate(v.fix_options, 1):
                label = opt.get("label", f"Option {j}")
                changes = opt.get("changes", {})
                changes_str = ", ".join(f"{k}={val}" for k, val in changes.items())
                lines.append(f"  Option {j}: {label} → {changes_str}")
        for v in agent.review_result.warnings:
            fields_str = ", ".join(v.fields)
            lines.append(f"- [WARNING] {fields_str}: {v.root_cause}")
        violations_text = "\n".join(lines)

    resource_context = schema_registry.get_resource_context(agent.resource_type)

    prompt = REVIEW_FAILED_PROMPT.format(
        resource_type=agent.resource_type,
        resource_context=resource_context,
        violations_text=violations_text,
        user_message=user_message,
    )

    messages = build_messages_fn(session, prompt)

    try:
        result = await llm_client.extract_json(messages)
    except Exception:
        return build_response(
            "Please choose:\n1. **Fix** — tell me what to change\n2. **Override** (warnings only)\n3. **Cancel**",
            resource_type=agent.resource_type,
            resource_status="review_failed",
            generated_yaml=agent.generated_yaml,
            review_result=agent.review_result.to_dict() if agent.review_result else None,
        )

    action = result.get("action", "question")
    extracted = result.get("extracted_fields", {})
    message = result.get("message", "")

    logger.info("[REVIEW_FAILED] LLM action=%s, extracted=%s",
                action, list(extracted.keys()) if extracted else [])

    if action == "cancel":
        return cancel_fn(session)

    if action == "override":
        if agent.review_result and agent.review_result.errors:
            return build_response(
                "❌ Cannot override — there are **error-level violations**. Please fix them first.",
                resource_type=agent.resource_type,
                resource_status="review_failed",
                generated_yaml=agent.generated_yaml,
                review_result=agent.review_result.to_dict() if agent.review_result else None,
            )
        return await after_review_fn(
            session, agent,
            prefix_message="⚠️ Proceeding with warnings noted.\n\n",
        )

    if action == "fix" and extracted:
        agent.collected_fields.update(extracted)
        agent.phase = "collecting"
        return await generate_yaml(
            session, agent, build_messages_fn,
            prefix_message=message or "Updated fields. Regenerating YAML...",
        )

    return build_response(
        message or "Please choose:\n1. **Fix** — tell me what to change\n2. **Override** (warnings only)\n3. **Cancel**",
        resource_type=agent.resource_type,
        resource_status="review_failed",
        generated_yaml=agent.generated_yaml,
        review_result=agent.review_result.to_dict() if agent.review_result else None,
    )
