"""
Generator Agent — LLM-Driven State Machine for Resource Configuration

DESIGN:
- Resource MD files are the single source of truth for all behavior.
- The LLM handles extraction, validation, normalization, and YAML generation
  using the MD file as context.
- Python code is a thin state machine that routes messages and manages state.
- NO hardcoded validation rules, regex, normalization dicts, or YAML builders.
- History is abstracted via SummaryHistoryProvider — hybrid in-memory + DB summary.

State machine:
  IDLE → DETECTING → COLLECTING → AWAITING_CONFIRMATION → PR_SETUP → DONE

Module structure:
  session_state.py  — AgentState, SessionState, session store, branch helpers
  pr_handler.py     — PR setup presentation, user response handling, PR execution
  generator_agent.py — this file: state machine routing + LLM interactions
  prompts.py        — all prompt templates
  history_provider.py — conversation history management
"""
import json
import logging
import re
import time
from typing import Optional
from collections import Counter

from app.agents.prompts import (
    SYSTEM_PROMPT,
    RESOURCE_ACTION_PROMPT,
    YAML_GENERATION_PROMPT,
    CONFIRMATION_PROMPT,
    ROUTING_PROMPT,
    REVIEW_FAILED_PROMPT,
)
from app.agents.session_state import (
    AgentState,
    SessionState,
    StructuredFlow,
    RESOURCE_OPTIONS,
    ENTERPRISE_SUBGROUPS,
    get_session,
    delete_session,
)
from app.agents.pr_handler import (
    present_pr_setup,
    handle_pr_setup,
    execute_batch_pr_creation,
    resume_pr_from_pause,
)
from app.agents.yaml_validator import validate_yaml
from app.agents.reviewer_agent import reviewer_agent
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry
from app.services.scm_adapter import check_fork_status
from app.agents.history_provider import SummaryHistoryProvider
from app.config import settings

logger = logging.getLogger(__name__)

# Default: use summary history provider
_history_provider = SummaryHistoryProvider()


# ═══════════════════════════════════════════════════════════════
# GENERATOR AGENT
# ═══════════════════════════════════════════════════════════════

class GeneratorAgent:
    """
    Thin state machine that routes messages to the LLM with resource context.
    The LLM + MD files handle all extraction, validation, and YAML generation.
    """

    async def process_message(self, session_id: str, user_message: str) -> dict:
        """Process a user message and return the agent's response."""
        # Guard: empty/whitespace messages
        if not user_message or not user_message.strip():
            return self._response("It looks like you sent an empty message. How can I help you?")

        session = get_session(session_id)

        # Lightweight session resume: if in-memory state is empty but DB has data
        if not session.current_agent and not session.conversation_history:
            await self._try_resume_from_db(session)

        _history_provider.add_message(session, "user", user_message)

        agent = session.current_agent

        try:
            # ── Structured flow intercept ──
            # If a structured flow is active, route through it
            if session.structured_flow and agent is None:
                result = await self._handle_structured_flow(session, user_message)
                _history_provider.add_message(session, "assistant", result["message"])
                return result

            # ── Batch command intercept ──
            # If no active agent but batch exists, check for batch commands first
            if agent is None and session.batch:
                batch_keywords = ["create pr", "show batch", "remove ", "edit ",
                                  "submit", "make pr", "batch", "proceed"]
                if any(kw in user_message.strip().lower() for kw in batch_keywords):
                    result = await self._handle_batch_prompt(session, user_message)
                    _history_provider.add_message(session, "assistant", result["message"])
                    return result

            if agent is None or agent.phase == "idle":
                # If there are completed resources and user might be referencing one,
                # route through post-completion handler first
                if agent is None and session.completed_resources:
                    post_result = await self._try_post_completion(session, user_message)
                    if post_result:
                        result = post_result
                    else:
                        result = await self._handle_idle(session, user_message)
                else:
                    result = await self._handle_idle(session, user_message)
            elif agent.phase == "detecting":
                # Ambiguous detection from a previous turn — re-route through idle
                session.current_agent = None
                result = await self._handle_idle(session, user_message)
            elif agent.phase == "collecting":
                result = await self._handle_collecting(session, user_message)
            elif agent.phase == "awaiting_confirmation":
                result = await self._handle_confirmation(session, user_message)
            elif agent.phase == "reviewing":
                # Review is automatic — this shouldn't receive user messages
                # but handle gracefully
                result = self._response(
                    "⏳ Your configuration is being reviewed. Please wait...",
                    resource_type=agent.resource_type,
                    resource_status="reviewing",
                )
            elif agent.phase == "review_failed":
                result = await self._handle_review_failed(session, user_message)
            elif agent.phase == "batch_prompt":
                result = await self._handle_batch_prompt(session, user_message)
            elif agent.phase == "pr_setup":
                result = await handle_pr_setup(session, user_message)
                # Check if pr_handler signaled an edit_config request
                if result.get("resource_status") == "edit_config_requested":
                    extracted = result.pop("_extracted_fields", {})
                    result = await self._handle_config_edit_from_pr(
                        session, agent, extracted, result.get("message", "")
                    )
            elif agent.phase == "done":
                result = await self._handle_post_completion(session, user_message)
            else:
                result = await self._handle_idle(session, user_message)
        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            result = self._response(
                f"I encountered an error: {str(e)}. Please try again.",
                resource_type=agent.resource_type if agent else None,
            )

        _history_provider.add_message(session, "assistant", result["message"])
        return result

    # ─── STATE HANDLERS ────────────────────────────────────────

    async def _handle_idle(self, session: SessionState, user_message: str) -> dict:
        """Route: is this a resource request, session end, or general chat?
        
        Starts the structured Q1→Q2→Q3 flow for resource creation.
        Falls back to LLM routing for ambiguous or general messages.
        """
        msg_lower = user_message.strip().lower()

        # Session end keywords (cheap check, always correct)
        end_keywords = {"done", "bye", "exit", "goodbye", "finished",
                        "no more", "nothing else", "all done", "i'm done",
                        "im done", "that's all", "that is all", "end"}
        if msg_lower in end_keywords or any(kw in msg_lower for kw in
                ["that's all", "that is all", "no more", "all done", "i'm done"]):
            return await self._handle_session_end(session)

        # PR status keywords (cheap check before LLM)
        pr_status_triggers = {"show my prs", "my prs", "pr status", "show prs",
                              "list prs", "check pr", "pr list", "my pull requests"}
        if msg_lower in pr_status_triggers or any(t in msg_lower for t in
                ["show my pr", "pr status", "my pull request", "check my pr"]):
            return await self._handle_pr_status(session)

        # ── Check for resource creation intent ──
        # Start structured flow for resource requests, or use LLM for general chat
        create_triggers = [
            "create", "set up", "setup", "configure", "provision", "make", "build",
            "need", "want", "new", "add", "get started", "start", "help me create",
            "s3", "glue", "iam", "bucket", "database", "role",
            "source", "dataproduct", "scripts", "engassets", "curated", "serving",
            "raw", "internal", "resource", "infrastructure", "yaml", "config",
        ]
        is_resource_intent = any(t in msg_lower for t in create_triggers)

        if is_resource_intent:
            # Start the structured guided flow
            return self._start_structured_flow(session)

        # ── General conversation — use LLM routing ──
        messages = self._build_messages(session, ROUTING_PROMPT.format(
            resource_triggers=schema_registry.get_triggers_summary(),
            user_message=user_message,
        ))

        try:
            result = await llm_client.extract_json(messages)
        except Exception as e:
            logger.error(f"Routing LLM call failed: {e}")
            return self._start_structured_flow(session)

        intent = result.get("intent", "general")
        detected_type = result.get("detected_resource_type")
        confidence = result.get("confidence", 0)
        extracted = result.get("extracted_fields", {})
        general_response = result.get("general_response")

        # If LLM detects resource intent, start structured flow
        if intent == "resource" and detected_type and confidence >= 0.6:
            return self._start_structured_flow(session, detected_type, extracted)

        # General conversation — answer or offer help
        if detected_type and schema_registry.get_resource_context(detected_type):
            resource_context = schema_registry.get_resource_context(detected_type)
            help_prompt = (
                f"The user asked a question about **{detected_type}** resource configuration.\n\n"
                f"RESOURCE GUIDE (use this to answer — includes templates, fields, allowed values):\n"
                f"{resource_context}\n\n"
                f"User question: \"{user_message}\"\n\n"
                f"Answer the question using the resource guide. If they asked for an example "
                f"or template, show one from the Templates section. If they asked about fields, "
                f"explain them with constraints. After answering, ask if they'd like to create "
                f"a {detected_type} configuration.\n\n"
                f"Respond in plain text (not JSON)."
            )
            try:
                help_response = await llm_client.chat(
                    [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": help_prompt}],
                    temperature=0.1,
                )
                return self._response(help_response)
            except Exception:
                pass

        if general_response:
            return self._response(general_response)

        # Default: offer to start the guided flow
        return self._response(
            "Hi! I help create infrastructure YAML configurations and raise PRs.\n\n"
            "I support **S3 buckets** and **Glue databases**.\n\n"
            "Ready to get started?",
            options=[
                {"label": "🚀 Get Started", "value": "get started"},
                {"label": "❓ What can you do?", "value": "what can you do"},
            ],
        )

    async def _handle_collecting(self, session: SessionState, user_message: str) -> dict:
        """Extract fields, validate, ask for next missing field — all via LLM."""
        agent = session.current_agent

        resource_context = schema_registry.get_resource_context(agent.resource_type)

        prompt = RESOURCE_ACTION_PROMPT.format(
            resource_type=agent.resource_type,
            resource_context=resource_context,
            collected_fields=json.dumps(agent.collected_fields, indent=2),
            phase=agent.phase,
            is_first_turn=not agent.initial_listing_shown,
            optional_fields_offered=agent.optional_fields_offered,
            field_retries=json.dumps(agent.field_retries),
            user_message=user_message,
        )

        # Mark first turn as shown after building the prompt
        if not agent.initial_listing_shown:
            agent.initial_listing_shown = True

        messages = self._build_messages(session, prompt)

        try:
            result = await llm_client.extract_json(messages, max_tokens=4096)
        except Exception as e:
            logger.error(f"Collection LLM call failed: {e}")
            return self._response(
                "I had trouble processing that. Could you try again?",
                resource_type=agent.resource_type,
                resource_status="collecting",
            )

        # Process LLM response
        extracted = result.get("extracted_fields", {})
        invalid = result.get("invalid_fields", {})
        next_action = result.get("next_action", "ask_field")
        next_field = result.get("next_field")
        message = result.get("message", "")
        yaml_output = result.get("yaml_output")
        retries = result.get("field_retries", {})

        # Update state
        if extracted and isinstance(extracted, dict):
            agent.collected_fields.update(extracted)
        if retries and isinstance(retries, dict):
            agent.field_retries.update(retries)
        if next_field:
            agent.current_field = next_field

        # Route based on next_action
        if next_action == "cancel":
            return self._cancel_current_resource(session)

        if next_action == "abort":
            session.current_agent = None
            return self._response(
                message or "Session aborted due to too many invalid attempts. Please restart."
            )

        if next_action == "confirm":
            # Safety net: if optional fields haven't been offered yet, force the phase
            # BUT only if the resource guide actually has optional fields
            # Skip this for guides that use Field Classification (Class D = auto-defaults)
            resource_context = schema_registry.get_resource_context(agent.resource_type) or ""
            has_optional_fields = "No optional fields" not in resource_context
            uses_field_classification = "Field Classification" in resource_context
            if not agent.optional_fields_offered and has_optional_fields and not uses_field_classification:
                agent.optional_fields_offered = True
                logger.info("LLM jumped to confirm before optional phase — forcing optional fields prompt")
                return await self._handle_collecting(
                    session,
                    "[System: All mandatory fields collected. Present optional fields with defaults per the guide.]"
                )
            # All fields collected — generate YAML
            agent.optional_fields_offered = True  # mark done even if no optional fields
            return await self._generate_yaml(session, agent, message)

        if next_action == "ask_optional":
            agent.optional_fields_offered = True
            return self._response(
                message,
                resource_type=agent.resource_type,
                resource_status="collecting",
            )

        if next_action == "generate_yaml" and yaml_output:
            agent.generated_yaml = yaml_output
            agent.phase = "awaiting_confirmation"
            # Don't pass LLM message as prefix — it often duplicates the YAML listing
            return self._show_yaml_preview(agent)

        # Default: ask_field or answer_question — just show the message
        return self._response(
            message,
            resource_type=agent.resource_type,
            resource_status="collecting",
        )

    async def _generate_yaml(self, session: SessionState, agent: AgentState,
                             prefix_message: str = "") -> dict:
        """Ask LLM to generate final YAML, validate, retry once if invalid."""
        resource_context = schema_registry.get_resource_context(agent.resource_type)

        prompt = YAML_GENERATION_PROMPT.format(
            resource_type=agent.resource_type,
            resource_context=resource_context,
            collected_fields=json.dumps(agent.collected_fields, indent=2),
        )

        messages = self._build_messages(session, prompt)

        logger.info(f"YAML generation prompt length: {len(prompt)} chars, messages count: {len(messages)}")
        for i, m in enumerate(messages):
            logger.info(f"  msg[{i}] role={m['role']} len={len(m['content'])}")

        for attempt in range(2):  # attempt 0 = first try, attempt 1 = retry
            try:
                result = await llm_client.extract_json(messages, max_tokens=4096)
                yaml_output = result.get("yaml_output", "")
                logger.info(f"YAML generation attempt {attempt}: yaml_output length={len(yaml_output)}, content='{yaml_output[:200]}'")
                logger.info(f"YAML generation full result keys: {list(result.keys())}")

                # ── Safety net: LLM sometimes splits YAML lines across JSON keys ──
                # Detect: if result has extra keys beyond yaml_output and message,
                # the LLM split the YAML into separate JSON key-value pairs.
                expected_keys = {"yaml_output", "message"}
                extra_keys = set(result.keys()) - expected_keys
                if extra_keys:
                    logger.warning(f"LLM split YAML across JSON keys! Reassembling from {len(extra_keys)} extra keys")
                    # Reassemble: yaml_output has the first line, then alternating key:value pairs
                    lines = [yaml_output.rstrip("\n")]
                    for key in result:
                        if key in expected_keys:
                            continue
                        # Each extra key is a YAML line, its value is also a YAML line
                        lines.append(key.rstrip("\n"))
                        val = result[key]
                        if isinstance(val, str) and val.strip():
                            lines.append(val.rstrip("\n"))
                    yaml_output = "\n".join(lines) + "\n"
                    logger.info(f"Reassembled YAML ({len(yaml_output)} chars): {yaml_output[:300]}")

                if not yaml_output:
                    if attempt == 0:
                        # Retry with explicit instruction
                        messages.append({"role": "assistant", "content": json.dumps(result)})
                        messages.append({"role": "user", "content": "yaml_output was empty. Please generate the complete YAML."})
                        continue
                    return self._response(
                        "Failed to generate YAML. Please try again.",
                        resource_type=agent.resource_type,
                        resource_status="collecting",
                    )

                # ── Validate YAML before showing to user ──
                validation = validate_yaml(yaml_output, agent.resource_type, agent.collected_fields)

                if validation.valid:
                    agent.generated_yaml = yaml_output
                    agent.phase = "awaiting_confirmation"
                    warning_text = ""
                    if validation.warnings:
                        warning_text = "⚠️ " + "; ".join(validation.warnings) + "\n\n"
                    return self._show_yaml_preview(agent, (prefix_message + "\n\n" + warning_text).strip() if warning_text else prefix_message)

                # Invalid — retry once with error feedback
                if attempt == 0:
                    logger.warning(f"YAML validation failed (attempt 1), retrying: {validation.error_summary}")
                    messages.append({"role": "assistant", "content": json.dumps(result)})
                    messages.append({"role": "user", "content":
                        f"The generated YAML has errors: {validation.error_summary}. "
                        f"Please fix these issues and regenerate the complete YAML."
                    })
                    continue

                # Second attempt also failed — show with warning
                logger.warning(f"YAML validation failed after retry: {validation.error_summary}")
                agent.generated_yaml = yaml_output
                agent.phase = "awaiting_confirmation"
                warning = f"⚠️ Note: {validation.error_summary}"
                combined = f"{prefix_message}\n\n{warning}" if prefix_message else warning
                return self._show_yaml_preview(agent, combined.strip())

            except Exception as e:
                logger.error(f"YAML generation failed: {e}")
                if attempt == 0:
                    continue
                return self._response(
                    f"Failed to generate YAML: {e}. Please try again.",
                    resource_type=agent.resource_type,
                    resource_status="collecting",
                )

        # Should not reach here, but safety net
        return self._response(
            "Failed to generate YAML after multiple attempts. Please try again.",
            resource_type=agent.resource_type,
            resource_status="collecting",
        )

    def _show_yaml_preview(self, agent: AgentState, prefix: str = "") -> dict:
        """Build the YAML preview response."""
        preview = f"```yaml\n{agent.generated_yaml}\n```\n\n"
        preview += "**Confirm**, **edit**, or **cancel**?"

        full_message = ""
        if prefix:
            full_message = prefix + "\n\n"
        full_message += preview

        return self._response(
            full_message,
            resource_type=agent.resource_type,
            resource_status="awaiting_confirmation",
            generated_yaml=agent.generated_yaml,
            needs_confirmation=True,
        )

    async def _handle_confirmation(self, session: SessionState, user_message: str) -> dict:
        """Handle user response to YAML preview."""
        agent = session.current_agent
        msg_lower = user_message.strip().lower()

        # Fast path for simple confirm/cancel
        confirm_words = {"confirm", "yes", "approve", "looks good", "lgtm", "ok", "okay", "y", "accept"}
        cancel_words = {"cancel", "no", "discard", "abort", "stop", "quit", "n"}

        if msg_lower in confirm_words:
            return await self._finalize_resource(session, agent)

        if msg_lower in cancel_words:
            return self._cancel_current_resource(session)

        # LLM path for edits, questions, or ambiguous input
        resource_context = schema_registry.get_resource_context(agent.resource_type)

        prompt = CONFIRMATION_PROMPT.format(
            resource_type=agent.resource_type,
            resource_context=resource_context,
            yaml_preview=agent.generated_yaml or "",
            collected_fields=json.dumps(agent.collected_fields, indent=2),
            user_message=user_message,
        )

        messages = self._build_messages(session, prompt)

        try:
            result = await llm_client.extract_json(messages)
        except Exception:
            return self._response(
                "Please respond with **confirm**, **edit**, or **cancel**.",
                resource_type=agent.resource_type,
                resource_status="awaiting_confirmation",
                needs_confirmation=True,
            )

        action = result.get("action", "question")
        extracted = result.get("extracted_fields", {})
        invalid = result.get("invalid_fields", {})
        message = result.get("message", "")

        if action == "confirm":
            return await self._finalize_resource(session, agent)

        if action == "cancel":
            return self._cancel_current_resource(session)

        if action == "edit":
            if extracted and isinstance(extracted, dict):
                agent.collected_fields.update(extracted)

            if invalid:
                # Some edits were invalid — show errors, stay in confirmation
                return self._response(
                    message,
                    resource_type=agent.resource_type,
                    resource_status="awaiting_confirmation",
                    needs_confirmation=True,
                )

            # Valid edits applied — regenerate YAML via Python
            return await self._generate_yaml(session, agent, message)

        # question or anything else
        return self._response(
            message,
            resource_type=agent.resource_type,
            resource_status="awaiting_confirmation",
            needs_confirmation=True,
        )

    async def _finalize_resource(self, session: SessionState, agent: AgentState) -> dict:
        """YAML confirmed — run organizational review before PR setup."""
        # Multi-resource preview confirm: add all generated resources once.
        multi_entries = getattr(agent, "multi_preview_entries", None)
        if isinstance(multi_entries, list) and multi_entries:
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
            return self._response(
                f"✅ Added **{added_count}** resource configuration"
                f"{'s' if added_count != 1 else ''} to batch ({total} total).\n\n"
                f"Add another resource, **\"show batch\"**, or **\"create PR\"** to submit all.",
                resource_status="batch_prompt",
            )

        # If reviewer has rules for this resource type, run review first
        if reviewer_agent.has_rules(agent.resource_type):
            agent.phase = "reviewing"
            return await self._handle_reviewing(session, agent)

        # No reviewer rules for this resource type — add to batch directly
        return await self._after_review_passed(session, agent)

    async def _handle_reviewing(self, session: SessionState, agent: AgentState) -> dict:
        """Run the reviewer agent on the confirmed YAML."""
        rtype = (agent.resource_type or "unknown").upper()

        agent.review_attempts += 1
        result = await reviewer_agent.review(agent.generated_yaml, agent.resource_type)
        agent.review_result = result

        # Loop detection flag: after 3+ failed reviews, offer escape hatches
        # alongside the normal violation display (not instead of it)
        show_escape_hatches = (not result.passed and agent.review_attempts >= 3)

        if result.passed:
            # Review passed — add to batch
            # Include warnings in the message if any
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

            # Add to batch (replaces direct _proceed_to_pr_setup)
            return await self._after_review_passed(session, agent, prefix_message=msg)

        # Review failed — show violations and present options
        agent.phase = "review_failed"

        # ── Build a clean, grouped review output ──
        errors = result.errors
        warnings = result.warnings

        parts = [f"🔍 **{rtype} Review Complete — {'Issues Found' if errors else 'Warnings Only'}**\n"]

        # Show the current YAML so user has context for the violations
        parts.append(f"**Your current configuration:**\n```yaml\n{agent.generated_yaml}\n```\n")

        # ERRORS section — blocking, must fix
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
                    parts.append("")  # blank line after fix options

        # WARNINGS section — non-blocking, advisory
        if warnings:
            parts.append("\n⚠️ **Warnings** _(non-blocking, for your awareness)_:\n")
            for i, w in enumerate(warnings, 1):
                fields_str = ", ".join(w.fields)
                parts.append(f"{i}. **{fields_str}** — {w.root_cause}")

        # Loop detection banner
        if show_escape_hatches:
            parts.append(
                f"\n🔄 _This configuration has been reviewed {agent.review_attempts} times. "
                f"You may **skip review** to proceed with issues noted in the PR._"
            )

        # Action options — context-dependent
        parts.append("")  # blank line
        if errors:
            skip_line = "\nOr type **skip review** to proceed with current config (issues will be noted in PR)." if show_escape_hatches else ""
            parts.append(
                "**What would you like to do?**\n"
                "Pick a fix option above, or tell me your own corrected values.\n"
                f"Or type **cancel** to discard this configuration.{skip_line}"
            )
        else:
            # Only warnings — allow override
            parts.append(
                "**What would you like to do?**\n"
                "1. **Fix** — tell me the corrected values\n"
                "2. **Override** — proceed with warnings noted\n"
                "3. **Cancel** — discard this configuration"
            )

        return self._response(
            "\n\n".join(parts),
            resource_type=agent.resource_type,
            resource_status="review_failed",
            generated_yaml=agent.generated_yaml,
            review_result=result.to_dict(),
        )

    async def _handle_review_failed(self, session: SessionState, user_message: str) -> dict:
        """Handle user response to review violations."""
        agent = session.current_agent
        msg_lower = user_message.strip().lower()

        # Quick keyword paths
        cancel_words = {"cancel", "discard", "abort", "stop", "quit", "no", "n"}
        override_words = {"override", "proceed anyway", "skip review", "force", "ignore"}

        if msg_lower in cancel_words:
            return self._cancel_current_resource(session)

        if msg_lower in override_words or msg_lower.startswith("override"):
            # Only allow override if no ERROR-level violations
            if agent.review_result and agent.review_result.errors:
                return self._response(
                    "❌ Cannot override — there are **error-level violations** that must be fixed first.\n\n"
                    "Please fix the errors, or cancel the configuration.",
                    resource_type=agent.resource_type,
                    resource_status="review_failed",
                    generated_yaml=agent.generated_yaml,
                    review_result=agent.review_result.to_dict() if agent.review_result else None,
                )
            # Only warnings — allow override
            return await self._after_review_passed(
                session, agent,
                prefix_message="⚠️ Proceeding with warnings noted. They will be included in the PR description.\n\n",
            )

        # ── Skip resource (batch-aware): discard current, keep batch ──
        skip_words = {"skip", "skip this", "skip this one", "skip resource"}
        if msg_lower in skip_words:
            session.current_agent = None
            batch_count = len(session.batch)
            if batch_count > 0:
                return self._response(
                    f"Skipped. Your batch still has {batch_count} resource{'s' if batch_count != 1 else ''}.\n"
                    f"Add another resource, or **\"create PR\"** to submit.",
                    resource_status="batch_prompt",
                )
            return self._response("Resource skipped. Let me know if you'd like to start over.")

        # ── Option shortcut: "option 1", "go with 2", "fix 1", "1" ──
        option_match = self._match_fix_option(msg_lower, agent)
        if option_match:
            agent.collected_fields.update(option_match)
            agent.phase = "collecting"
            applied = ", ".join(f"**{k}**" for k in option_match)
            return await self._generate_yaml(
                session, agent,
                prefix_message=f"Applied fix: updated {applied}. Regenerating YAML...",
            )

        # LLM path for fix requests, questions, or ambiguous input
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

        messages = self._build_messages(session, prompt)

        try:
            result = await llm_client.extract_json(messages)
        except Exception:
            return self._response(
                "Please choose:\n1. **Fix** — tell me what to change\n2. **Override** (warnings only)\n3. **Cancel**",
                resource_type=agent.resource_type,
                resource_status="review_failed",
                generated_yaml=agent.generated_yaml,
                review_result=agent.review_result.to_dict() if agent.review_result else None,
            )

        action = result.get("action", "question")
        extracted = result.get("extracted_fields", {})
        message = result.get("message", "")

        if action == "cancel":
            return self._cancel_current_resource(session)

        if action == "override":
            if agent.review_result and agent.review_result.errors:
                return self._response(
                    "❌ Cannot override — there are **error-level violations**. Please fix them first.",
                    resource_type=agent.resource_type,
                    resource_status="review_failed",
                    generated_yaml=agent.generated_yaml,
                    review_result=agent.review_result.to_dict() if agent.review_result else None,
                )
            return await self._after_review_passed(
                session, agent,
                prefix_message="⚠️ Proceeding with warnings noted.\n\n",
            )

        if action == "fix" and extracted:
            # User wants to fix fields — update collected_fields, regenerate YAML, re-review
            agent.collected_fields.update(extracted)
            agent.phase = "collecting"
            # Regenerate YAML with the fixed fields, then it will go back through
            # confirmation → finalize → review again
            return await self._generate_yaml(
                session, agent,
                prefix_message=message or "Updated fields. Regenerating YAML...",
            )

        # Question or unrecognized
        return self._response(
            message or "Please choose:\n1. **Fix** — tell me what to change\n2. **Override** (warnings only)\n3. **Cancel**",
            resource_type=agent.resource_type,
            resource_status="review_failed",
            generated_yaml=agent.generated_yaml,
            review_result=agent.review_result.to_dict() if agent.review_result else None,
        )

    # ─── STRUCTURED FLOW HANDLERS ─────────────────────────────

    def _start_structured_flow(self, session: SessionState,
                               detected_type: str = None,
                               extracted_fields: dict = None) -> dict:
        """Start the guided Q1→Q2→Q3 flow. Returns Q1 prompt."""
        flow = StructuredFlow()
        session.structured_flow = flow

        # If user provided enough detail upfront (e.g. "raw Glue DB for Concur in FOOD dev"),
        # try to pre-fill from extracted_fields and skip ahead
        if extracted_fields and detected_type:
            self._prefill_flow_from_extracted(flow, detected_type, extracted_fields)
            if flow.environment:
                # Environment already known — skip Q1
                flow.phase = "q2_resource"
                return self._present_q2_resources(session)

        # Q1: Ask environment
        return self._present_q1_environment(session)

    def _prefill_flow_from_extracted(self, flow: StructuredFlow,
                                     detected_type: str, fields: dict):
        """Pre-fill structured flow from LLM-extracted fields."""
        # Environment
        env = fields.get("data_env") or fields.get("environment")
        if env and env.lower() in ("dev", "prd"):
            flow.environment = env.lower()

        # Enterprise
        ent = fields.get("enterprise_or_func_name")
        if ent and ent.upper() in ("AGTR", "CORP", "FOOD", "SPEC"):
            flow.selected_enterprise = ent.upper()

    def _present_q1_environment(self, session: SessionState) -> dict:
        """Q1: Which environment?"""
        session.structured_flow.phase = "q1_env"
        return self._response(
            "**Step 1 of 3** — Which environment is this for?",
            resource_status="q1_env",
            options=[
                {"label": "🔧 Dev", "value": "dev", "description": "Development environment"},
                {"label": "🚀 Prod", "value": "prd", "description": "Production environment"},
            ],
        )

    def _present_q2_resources(self, session: SessionState) -> dict:
        """Q2: Which resource type(s)? — multi-select enabled."""
        flow = session.structured_flow
        flow.phase = "q2_resource"

        env_label = "Dev" if flow.environment == "dev" else "Prod"

        return self._response(
            f"**Step 2 of 3** — Environment: **{env_label}**\n\n"
            f"What type of resource(s) do you need?\n"
            f"*You can select **multiple** resources — e.g. an S3 bucket and a Glue DB together.*",
            resource_status="q2_resource",
            options=self._build_resource_options(),
            options_multi_select=True,
        )

    def _present_q2_enterprise(self, session: SessionState) -> dict:
        """Q2b: Which enterprise?"""
        flow = session.structured_flow
        flow.phase = "q2_enterprise"

        # Show which resources are selected
        if len(flow.selected_resources) > 1:
            labels = [RESOURCE_OPTIONS[k]["label"] for k in flow.selected_resources if k in RESOURCE_OPTIONS]
            resources_text = ", ".join(labels)
            prompt = f"Which enterprise are these resources for?\n\n📋 Selected: **{resources_text}**"
        else:
            config = flow.get_resource_config()
            resource_label = config.get("label", "resource")
            prompt = f"Which enterprise is this **{resource_label}** for?"

        return self._response(
            prompt,
            resource_status="q2_enterprise",
            options=[
                {"label": "AGTR", "value": "AGTR", "description": "Ag Trading"},
                {"label": "CORP", "value": "CORP", "description": "Corporate"},
                {"label": "FOOD", "value": "FOOD", "description": "Food"},
                {"label": "SPEC", "value": "SPEC", "description": "Specialized"},
                {"label": "⬅️ Go Back", "value": "back", "description": "Change resource type"},
            ],
        )

    async def _present_q3(self, session: SessionState) -> dict:
        """Present the next Q3 conditional question, or advance to classification/text collection."""
        flow = session.structured_flow
        flow.phase = "q3_conditionals"

        q = flow.current_q3_question()
        if q is None:
            # All Q3 questions answered — go to classification if Glue DBs, else text collection
            if flow.has_glue_resources():
                return self._present_classification(session)
            return self._present_combined_text_collection(session)

        # Context prefix — show which resource a question applies to
        res_key = flow.q3_resource_context.get(q)
        res_label = RESOURCE_OPTIONS.get(res_key, {}).get("label", "") if res_key else ""
        context_note = f" *(for {res_label})*" if res_label else ""

        if q == "account_placement":
            return self._response(
                f"Where should the resource be placed?{context_note}",
                resource_status="q3_conditionals",
                options=[
                    {"label": "🏠 Lakehouse", "value": "lakehouse",
                     "description": "Shared data lake account"},
                    {"label": "⚡ Compute", "value": "compute",
                     "description": "Enterprise-specific compute account"},
                ],
            )

        if q == "data_construct":
            return self._response(
                f"Is this Internal DB for a **Source** system or a **DataProduct**?{context_note}",
                resource_status="q3_conditionals",
                options=[
                    {"label": "Source", "value": "Source",
                     "description": "Internal DB for a source system (→ Lakehouse)"},
                    {"label": "DataProduct", "value": "DataProduct",
                     "description": "Internal DB for a data product (→ Compute)"},
                ],
            )

        if q == "cdp_flag":
            return self._response(
                f"Raw Source Glue DB — current or CDP data?",
                resource_status="q3_conditionals",
                options=[
                    {"label": "Current", "value": "no",
                     "description": "Current / standard source"},
                    {"label": "CDP", "value": "yes",
                     "description": "Customer Data Platform source"},
                ],
            )

        if q == "serving_purpose":
            return self._response(
                f"Serving purpose for the Serving DB?{context_note}\n\n"
                "This becomes part of the database name (e.g. `_serving_analytics_dev`).",
                resource_status="q3_conditionals",
                options=[
                    {"label": "Analytics", "value": "analytics"},
                    {"label": "Reporting", "value": "reporting"},
                    {"label": "Events", "value": "events"},
                    {"label": "API", "value": "api"},
                    {"label": "Other (type below)", "value": "__custom__"},
                ],
            )

        if q == "subgroup":
            enterprise = flow.selected_enterprise
            subgroups = ENTERPRISE_SUBGROUPS.get(enterprise, [])
            options = [{"label": "None / Skip", "value": "", "description": "No subgroup"}]
            for sg in subgroups:
                options.append({"label": sg, "value": sg})

            return self._response(
                f"Which {enterprise} subgroup?",
                resource_status="q3_conditionals",
                options=options,
            )

        # Unknown question — skip
        flow.advance_q3()
        return await self._present_q3(session)

    # ── Classification phase (asked once for all Glue DBs) ────────────

    def _present_classification(self, session: SessionState) -> dict:
        """Ask data classification once for all Glue databases."""
        flow = session.structured_flow
        flow.phase = "classification"
        flow._classif_step = "classification"

        return self._response(
            "Data classification for the Glue databases?",
            resource_status="classification",
            options=[
                {"label": "Confidential - General Use", "value": "Confidential - General Use",
                 "description": "Default — most common"},
                {"label": "Confidential - Limited", "value": "Confidential - Limited",
                 "description": "Restricted access"},
                {"label": "Confidential - Restricted", "value": "Confidential - Restricted",
                 "description": "Highly restricted"},
                {"label": "Internal", "value": "Internal",
                 "description": "Internal use only"},
            ],
        )

    async def _handle_classification_response(self, session: SessionState, user_message: str) -> dict:
        """Handle classification/privacy responses — asked once globally."""
        flow = session.structured_flow
        step = getattr(flow, '_classif_step', 'classification')

        if step == "classification":
            flow.data_classification = user_message.strip()
            # Now ask privacy — included in combined text collection per example
            # The example shows privacy as part of the "last details" prompt
            # So just move to text collection
            return self._present_combined_text_collection(session)

        # fallback
        return self._present_combined_text_collection(session)

    # ── Combined text collection (single prompt for ALL resources) ──────

    def _present_combined_text_collection(self, session: SessionState) -> dict:
        """Single combined prompt asking all remaining details across ALL resources."""
        flow = session.structured_flow
        flow.phase = "text_collection"

        needed = []

        # Collect unique field needs across all resources
        has_s3 = False
        has_glue_source = False
        has_glue_product = False
        has_glue_serving = False
        has_glue = False

        for res_key in flow.selected_resources:
            config = RESOURCE_OPTIONS.get(res_key, {})
            rtype = config.get("resource_type")
            auto = config.get("auto_fields", {})

            if rtype == "s3":
                has_s3 = True
            elif rtype == "glue_db":
                has_glue = True
                construct = auto.get("data_construct", "")
                layer = auto.get("data_layer", "")
                if construct == "Source" or layer == "raw":
                    has_glue_source = True
                if construct == "DataProduct" or layer in ("curated", "serving"):
                    has_glue_product = True
                if layer == "serving":
                    has_glue_serving = True

        # Source name (for raw/source Glue DBs)
        if has_glue_source:
            needed.append("**Source name** for the Raw Glue DB (e.g. `sap`, `concur`, `workday`)")

        # Data product name (for curated/serving Glue DBs)
        if has_glue_product:
            needed.append("**Data product name** for the Serving/Curated Glue DB (e.g. `c360`, `controls`)")

        # Serving purpose (if serving DB and not already answered in Q3)
        if has_glue_serving and not flow.serving_purpose:
            needed.append("**Serving purpose** (e.g. `analytics`, `reporting`, `consumption`)")

        # Data privacy — asked here as part of final details (per example)
        if has_glue:
            needed.append("**Data privacy**: `PI`, `PCI`, `PHI`, `BCI`, or `NONE`")

        # Ownership fields (for Glue DBs — shared across all)
        if has_glue:
            needed.append("**Data owner email**")
            needed.append("**Data owner GitHub username**")
            needed.append("**Data leader** (e.g. `KatiePorter`, `a123456`)")

        # Intake IDs — grouped for all resources
        total = len(flow.selected_resources)
        resource_labels = [RESOURCE_OPTIONS.get(k, {}).get("label", k) for k in flow.selected_resources]
        resource_list = ", ".join(resource_labels)
        needed.append(f"**Intake IDs** — {total} resource{'s' if total > 1 else ''} total ({resource_list}). "
                       f"How many IDs and how do they map?")

        fields_list = "\n".join(f"  • {f}" for f in needed)

        return self._response(
            f"**Last details:**\n\n{fields_list}",
            resource_status="text_collection",
        )

    async def _handle_text_collection_response(self, session: SessionState,
                                                user_message: str) -> dict:
        """Handle the single combined text collection response — then generate ALL YAMLs."""
        flow = session.structured_flow

        # Store the raw text
        flow._tc_raw_text = user_message

        # Generate all YAMLs
        return await self._finalize_all_resources(session)

    async def _handle_structured_flow(self, session: SessionState, user_message: str) -> dict:
        """Dispatch to the current structured flow phase."""
        flow = session.structured_flow
        msg_lower = user_message.strip().lower()

        # Allow cancel at any point
        if msg_lower in {"cancel", "stop", "quit", "abort", "exit"}:
            session.structured_flow = None
            return self._response("Setup cancelled. Let me know if you'd like to start over.")

        # Allow restart
        if msg_lower in {"restart", "start over", "reset"}:
            session.structured_flow = None
            return self._start_structured_flow(session)

        # Allow go back at any phase
        if msg_lower in {"back", "go back", "previous", "change", "undo"}:
            return await self._handle_go_back(session)

        # Detect rejection / "don't want" patterns — user disagrees with current resource
        reject_patterns = [
            "don't want", "dont want", "not that", "wrong", "no i",
            "change resource", "different resource", "not what i",
            "i said", "that's not", "thats not", "i meant",
        ]
        if any(p in msg_lower for p in reject_patterns):
            return await self._handle_go_back(session)

        if flow.phase == "q1_env":
            return self._handle_q1_response(session, user_message)
        elif flow.phase == "q2_resource":
            return self._handle_q2_resource_response(session, user_message)
        elif flow.phase == "q2_enterprise":
            return await self._handle_q2_enterprise_response(session, user_message)
        elif flow.phase == "q3_conditionals":
            return await self._handle_q3_response(session, user_message)
        elif flow.phase == "classification":
            return await self._handle_classification_response(session, user_message)
        elif flow.phase == "text_collection":
            return await self._handle_text_collection_response(session, user_message)
        else:
            # Unknown phase — restart
            session.structured_flow = None
            return self._start_structured_flow(session)

    async def _handle_go_back(self, session: SessionState) -> dict:
        """Go back to the previous phase in the structured flow."""
        flow = session.structured_flow
        phase_order = ["q1_env", "q2_resource", "q2_enterprise", "q3_conditionals", "classification", "text_collection"]
        current_idx = phase_order.index(flow.phase) if flow.phase in phase_order else 0

        if current_idx <= 0:
            # Already at the start — re-present Q1
            return self._present_q1_environment(session)

        prev_phase = phase_order[current_idx - 1]

        # Reset the current phase's data
        if flow.phase == "q2_resource":
            flow.selected_resource = None
        elif flow.phase == "q2_enterprise":
            flow.selected_resource = None
            flow.selected_enterprise = None
        elif flow.phase == "q3_conditionals":
            flow.selected_enterprise = None
            flow.q3_queue = []
            flow.q3_index = 0
        elif flow.phase == "text_collection":
            flow.q3_queue = []
            flow.q3_index = 0
        elif flow.phase == "classification":
            pass  # Just go back to Q3

        # Navigate to previous phase
        if prev_phase == "q1_env":
            flow.environment = None
            return self._present_q1_environment(session)
        elif prev_phase == "q2_resource":
            flow.selected_resource = None
            return self._present_q2_resources(session)
        elif prev_phase == "q2_enterprise":
            return self._present_q2_enterprise(session)
        elif prev_phase == "q3_conditionals":
            flow.compute_q3_questions()
            return await self._present_q3(session)
        elif prev_phase == "classification":
            return self._present_classification(session)

        return self._present_q1_environment(session)

    def _handle_q1_response(self, session: SessionState, user_message: str) -> dict:
        """Handle Q1 environment response."""
        flow = session.structured_flow
        msg = user_message.strip().lower()

        if "dev" in msg:
            flow.environment = "dev"
        elif "prd" in msg or "prod" in msg:
            flow.environment = "prd"
        else:
            return self._response(
                "Please select an environment:",
                resource_status="q1_env",
                options=[
                    {"label": "🔧 Dev", "value": "dev"},
                    {"label": "🚀 Prod", "value": "prd"},
                ],
            )

        return self._present_q2_resources(session)

    def _handle_q2_resource_response(self, session: SessionState, user_message: str) -> dict:
        """Handle Q2 resource type selection — supports multi-select (comma-separated)."""
        flow = session.structured_flow
        msg = user_message.strip().lower()

        # Multi-select: user may send "s3_source, glue_raw" or "s3_source, s3_dataproduct"
        parts = [p.strip() for p in msg.split(",") if p.strip()]

        resolved_keys = []
        for part in parts:
            key = self._resolve_resource_key(part)
            if key and key not in resolved_keys:
                resolved_keys.append(key)

        if not resolved_keys:
            return self._response(
                "I didn't recognize that resource type. Please select one or more options below:",
                resource_status="q2_resource",
                options=self._build_resource_options(),
                options_multi_select=True,
            )

        # Store all selected resources
        flow.selected_resources = resolved_keys
        flow.current_resource_index = 0
        flow.selected_resource = resolved_keys[0]

        if len(resolved_keys) > 1:
            labels = [RESOURCE_OPTIONS[k]["label"] for k in resolved_keys]
            summary = "\n".join(f"  {i+1}. **{l}**" for i, l in enumerate(labels))
            logger.info(f"Multi-resource selection: {resolved_keys}")

        return self._present_q2_enterprise(session)

    def _resolve_resource_key(self, text: str) -> Optional[str]:
        """Resolve a single resource key from text input."""
        text = text.strip().lower()

        # Exact match
        if text in RESOURCE_OPTIONS:
            return text

        # Fuzzy matching — longest-first
        fuzzy_pairs = [
            ("source bucket", "s3_source"), ("source s3", "s3_source"),
            ("dataproduct bucket", "s3_dataproduct"), ("data product bucket", "s3_dataproduct"),
            ("data product", "s3_dataproduct"), ("dp bucket", "s3_dataproduct"),
            ("dataproduct", "s3_dataproduct"),
            ("scripts bucket", "s3_scripts"), ("script bucket", "s3_scripts"),
            ("engassets bucket", "s3_engassets"), ("engineering assets", "s3_engassets"),
            ("eng assets", "s3_engassets"), ("engassets", "s3_engassets"),
            ("raw source db", "glue_raw"), ("raw source", "glue_raw"),
            ("raw db", "glue_raw"),
            ("curated db", "glue_curated"),
            ("serving db", "glue_serving"),
            ("internal db", "glue_internal"),
            ("scripts", "s3_scripts"), ("script", "s3_scripts"),
            ("curated", "glue_curated"),
            ("serving", "glue_serving"),
            ("internal", "glue_internal"),
        ]
        for phrase, key in fuzzy_pairs:
            if phrase in text:
                return key

        # Ambiguous short words — only if entire input
        short_exact = {"source": "s3_source", "raw": "glue_raw"}
        if text in short_exact:
            return short_exact[text]

        return None

    def _build_resource_options(self) -> list:
        """Build the options list for Q2 resource selection."""
        return [
            {"label": "🪣 Source Bucket (S3)", "value": "s3_source",
             "description": "Data ingestion from source systems → Lakehouse"},
            {"label": "🪣 DataProduct Bucket (S3)", "value": "s3_dataproduct",
             "description": "Transformed data → Compute"},
            {"label": "🪣 Scripts Bucket (S3)", "value": "s3_scripts",
             "description": "ETL scripts and code"},
            {"label": "🪣 EngAssets Bucket (S3)", "value": "s3_engassets",
             "description": "Engineering assets"},
            {"label": "📊 Raw Source DB (Glue)", "value": "glue_raw",
             "description": "Raw data ingestion layer → Lakehouse"},
            {"label": "📊 Curated DB (Glue)", "value": "glue_curated",
             "description": "Processed data → Compute"},
            {"label": "📊 Serving DB (Glue)", "value": "glue_serving",
             "description": "Analytics / serving layer → Compute"},
            {"label": "📊 Internal DB (Glue)", "value": "glue_internal",
             "description": "Internal processing / staging"},
        ]

    async def _handle_q2_enterprise_response(self, session: SessionState, user_message: str) -> dict:
        """Handle Q2b enterprise selection."""
        flow = session.structured_flow
        msg = user_message.strip().upper()

        enterprise = None
        for ent in ("AGTR", "CORP", "FOOD", "SPEC"):
            if ent in msg:
                enterprise = ent
                break

        # Fuzzy matching
        if not enterprise:
            fuzzy_ent = {
                "ag trading": "AGTR", "agriculture": "AGTR",
                "corporate": "CORP",
                "specialized": "SPEC", "specialty": "SPEC",
            }
            msg_lower = user_message.strip().lower()
            for phrase, ent in fuzzy_ent.items():
                if phrase in msg_lower:
                    enterprise = ent
                    break

        if not enterprise:
            config = flow.get_resource_config()
            resource_label = config.get("label", "resource")
            return self._response(
                f"I didn't recognize that enterprise. Please select one for your **{resource_label}**:\n\n"
                f"*You can also type \"back\" to change the resource type.*",
                resource_status="q2_enterprise",
                options=[
                    {"label": "AGTR", "value": "AGTR", "description": "Ag Trading"},
                    {"label": "CORP", "value": "CORP", "description": "Corporate"},
                    {"label": "FOOD", "value": "FOOD", "description": "Food"},
                    {"label": "SPEC", "value": "SPEC", "description": "Specialized"},
                    {"label": "⬅️ Go Back", "value": "back", "description": "Change resource type"},
                ],
            )

        flow.selected_enterprise = enterprise

        # Compute Q3 questions and start asking
        flow.compute_q3_questions()
        return await self._present_q3(session)

    async def _handle_q3_response(self, session: SessionState, user_message: str) -> dict:
        """Handle Q3 conditional question response."""
        flow = session.structured_flow
        q = flow.current_q3_question()
        msg = user_message.strip().lower()

        if q == "account_placement":
            if "lakehouse" in msg or "lh" in msg:
                flow.account_placement = "lakehouse"
            elif "compute" in msg or "cmp" in msg:
                flow.account_placement = "compute"
            else:
                return await self._present_q3(session)

        elif q == "data_construct":
            if "source" in msg:
                flow.data_construct = "Source"
            elif "dataproduct" in msg or "data product" in msg or "product" in msg:
                flow.data_construct = "DataProduct"
            else:
                return await self._present_q3(session)

        elif q == "cdp_flag":
            if "yes" in msg or "cdp" in msg:
                flow.cdp_flag = "yes"
            else:
                flow.cdp_flag = "no"

        elif q == "serving_purpose":
            # Accept the value directly (could be a button or free-form)
            if "__custom__" in msg:
                return self._response(
                    "Please type the serving purpose (e.g. `analytics`, `reporting`, `events`):",
                    resource_status="q3_conditionals",
                )
            purpose = user_message.strip().lower().replace(" ", "_")
            if purpose:
                flow.serving_purpose = purpose
            else:
                return await self._present_q3(session)

        elif q == "subgroup":
            # Accept the value — empty means no subgroup
            value = user_message.strip().upper()
            if value in ("NONE", "SKIP", "NONE / SKIP", ""):
                flow.subgroup = ""
            elif value:
                enterprise = flow.selected_enterprise
                valid_sgs = ENTERPRISE_SUBGROUPS.get(enterprise, [])
                if value in valid_sgs or not valid_sgs:
                    flow.subgroup = value
                else:
                    return self._response(
                        f"**{value}** is not a valid subgroup for {enterprise}.\n\n"
                        f"Valid options: {', '.join(valid_sgs)}",
                        resource_status="q3_conditionals",
                        options=[{"label": sg, "value": sg} for sg in valid_sgs]
                        + [{"label": "None / Skip", "value": ""}],
                    )
            else:
                flow.subgroup = ""

        # Advance to next Q3 question
        flow.advance_q3()
        return await self._present_q3(session)

    async def _finalize_all_resources(self, session: SessionState) -> dict:
        """Process ALL resources at once — derive fields, generate YAMLs, show combined preview."""
        from app.agents.field_deriver import derive_s3_fields, derive_glue_db_fields

        flow = session.structured_flow
        raw_text = getattr(flow, '_tc_raw_text', '')

        # Use LLM to parse the raw text into per-resource fields
        parsed = await self._parse_combined_input(session, flow, raw_text)

        # Process each resource
        for res_key in flow.selected_resources:
            config = RESOURCE_OPTIONS.get(res_key, {})
            resource_type = config.get("resource_type", "s3")

            # Build auto fields for this specific resource
            auto_fields = flow.build_auto_fields_for(res_key)

            # S3 defaults
            if resource_type == "s3":
                auto_fields.setdefault("aws_region", "us-east-1")
                auto_fields.setdefault("versioning_enabled", "true" if res_key == "s3_scripts" else "false")
                auto_fields.setdefault("public_access_blocked", "true")
                auto_fields.setdefault("encryption_enabled", "true")
                auto_fields.setdefault("encryption_type", "SSE-S3")
            else:
                auto_fields.setdefault("region", "us-east-1")
                if flow.data_classification:
                    auto_fields["data_classification"] = flow.data_classification
                else:
                    auto_fields.setdefault("data_classification", "Confidential - General Use")

            # Merge LLM-parsed fields for this resource
            res_parsed = parsed.get(res_key, {})
            for k, v in res_parsed.items():
                if v:
                    auto_fields[k] = v

            # Shared parsed fields (privacy, ownership — apply to all Glue DBs)
            shared = parsed.get("_shared", {})
            if resource_type == "glue_db":
                for k in ("data_privacy", "data_owner_email", "data_owner_github_uname", "data_leader"):
                    if k in shared and shared[k]:
                        auto_fields.setdefault(k, shared[k])
                if not auto_fields.get("data_privacy"):
                    auto_fields["data_privacy"] = "NONE"

            # Create agent for this resource
            agent = session.start_new_resource()
            agent.resource_type = resource_type
            agent.collected_fields = auto_fields
            agent.phase = "collecting"
            agent.initial_listing_shown = True
            agent.optional_fields_offered = True

            # Derive account
            flow.selected_resource = res_key
            self._derive_account_from_flow(flow, agent)

            # Run field deriver
            if resource_type == "s3":
                derived = derive_s3_fields(agent.collected_fields)
                for k, v in derived.items():
                    agent.collected_fields.setdefault(k, v)
                if "bucket_description" not in agent.collected_fields:
                    agent.collected_fields["bucket_description"] = self._generate_bucket_description_for(
                        flow, res_key)
            else:
                derived = derive_glue_db_fields(agent.collected_fields)
                for k, v in derived.items():
                    agent.collected_fields.setdefault(k, v)
                if "database_description" not in agent.collected_fields:
                    agent.collected_fields["database_description"] = self._generate_db_description_for(
                        flow, res_key, agent)

            # Generate YAML
            yaml_result = await self._generate_yaml_silent(session, agent)
            if not yaml_result:
                logger.warning(f"YAML generation failed for {res_key}")
                yaml_result = None

            flow.completed_resource_yamls.append({
                "resource_key": res_key,
                "resource_type": resource_type,
                "label": RESOURCE_OPTIONS.get(res_key, {}).get("label", res_key),
                "fields": agent.collected_fields.copy(),
                "yaml": yaml_result,
            })

        # Show combined preview
        return self._show_multi_yaml_preview(session, flow)

    async def _parse_combined_input(self, session, flow, raw_text: str) -> dict:
        """Use LLM to parse the combined user input into per-resource fields."""
        import json as _json

        # Build a description of what we need for each resource
        resource_descriptions = []
        for res_key in flow.selected_resources:
            config = RESOURCE_OPTIONS.get(res_key, {})
            label = config.get("label", res_key)
            rtype = config.get("resource_type", "s3")
            auto = config.get("auto_fields", {})

            needs = []
            if rtype == "s3":
                needs.append("intake_id")
            else:
                needs.append("intake_id")
                construct = auto.get("data_construct", "")
                layer = auto.get("data_layer", "")
                if construct == "Source" or layer == "raw":
                    needs.append("source_name")
                if construct == "DataProduct" or layer in ("curated", "serving"):
                    needs.append("data_product_name")
                if layer == "serving" and flow.serving_purpose:
                    needs.append(f"serving_purpose (already known: {flow.serving_purpose})")

            resource_descriptions.append(f"- {res_key} ({label}): needs {', '.join(needs)}")

        resources_text = "\n".join(resource_descriptions)

        prompt = f"""Parse the user's message into fields for each resource.

Resources to fill:
{resources_text}

Shared fields needed (for all Glue databases):
- data_privacy: PI, PCI, PHI, BCI, or NONE
- data_owner_email: email address
- data_owner_github_uname: GitHub username
- data_leader: leader ID or name

User message: {raw_text}

Return JSON with resource keys as top-level keys, plus "_shared" for shared fields.
Each resource key maps to a dict of field values.
Example:
{{
  "s3_source": {{"intake_id": "M0000789"}},
  "glue_raw": {{"intake_id": "M0000789", "source_name": "sa3"}},
  "_shared": {{"data_privacy": "PI", "data_owner_email": "john@example.com", "data_owner_github_uname": "johndoe", "data_leader": "KatiePorter"}}
}}

If multiple resources share the same intake_id, use the same ID.
If the user maps specific IDs to specific resources, follow their mapping.
Only return the JSON, nothing else."""

        messages = [{"role": "user", "content": prompt}]
        try:
            result = await llm_client.extract_json(messages, max_tokens=2048)
            logger.info(f"Parsed combined input: {list(result.keys())}")
            return result
        except Exception as e:
            logger.error(f"Failed to parse combined input: {e}")
            # Fallback: extract basic fields with regex
            return self._regex_parse_combined(flow, raw_text)

    def _regex_parse_combined(self, flow, raw_text: str) -> dict:
        """Fallback regex parser for combined input."""
        import re
        result = {}
        text_lower = raw_text.lower()

        # Extract all intake IDs
        intake_ids = re.findall(r'\b[MI]-?\d{4,10}\b', raw_text, re.IGNORECASE)

        # Extract source name
        source_match = re.search(r'source\s+(?:is\s+|name\s+)?[:\-]?\s*(\w+)', text_lower)
        source_name = source_match.group(1) if source_match else None

        # Extract product name
        product_match = re.search(r'(?:product|data\s*product)\s+(?:is\s+|name\s+)?[:\-]?\s*(\w+)', text_lower)
        product_name = product_match.group(1) if product_match else None

        # Extract privacy
        privacy_match = re.search(r'\b(PI|PCI|PHI|BCI|SPI|NONE)\b', raw_text)
        privacy = privacy_match.group(1) if privacy_match else "NONE"

        # Extract email
        email_match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', raw_text)
        email = email_match.group(0) if email_match else None

        # Extract GitHub username
        gh_match = re.search(r'github\s+(?:user(?:name)?\s+)?(\w+)', text_lower)
        gh_user = gh_match.group(1) if gh_match else None

        # Extract leader
        leader_match = re.search(r'leader\s+(?:is\s+)?(\w+)', text_lower)
        leader = leader_match.group(1) if leader_match else None

        # Map intake IDs to resources
        id_idx = 0
        for res_key in flow.selected_resources:
            config = RESOURCE_OPTIONS.get(res_key, {})
            rtype = config.get("resource_type", "s3")
            auto = config.get("auto_fields", {})
            entry = {}

            if id_idx < len(intake_ids):
                entry["intake_id"] = intake_ids[id_idx]
                id_idx += 1

            if rtype == "glue_db":
                construct = auto.get("data_construct", "")
                layer = auto.get("data_layer", "")
                if (construct == "Source" or layer == "raw") and source_name:
                    entry["source_name"] = source_name
                if (construct == "DataProduct" or layer in ("curated", "serving")) and product_name:
                    entry["data_product_name"] = product_name

            result[res_key] = entry

        result["_shared"] = {
            "data_privacy": privacy,
            "data_owner_email": email,
            "data_owner_github_uname": gh_user,
            "data_leader": leader,
        }

        return result

    def _generate_bucket_description_for(self, flow, res_key: str) -> str:
        """Auto-generate a bucket description for a specific resource key."""
        config = RESOURCE_OPTIONS.get(res_key, {})
        usage = config.get("auto_fields", {}).get("usage_type", "data")
        enterprise = flow.selected_enterprise or ""
        subgroup = flow.subgroup or ""

        purpose_map = {
            "Source": "source data",
            "DataProduct": "data product",
            "Scripts": "ETL scripts and code",
            "EngAssets": "engineering assets",
        }
        purpose = purpose_map.get(usage, usage.lower())
        entity = f"{enterprise} {subgroup}".strip() if subgroup else enterprise
        return f"Stores {purpose} for {entity} subgroup"

    def _generate_db_description_for(self, flow, res_key: str, agent) -> str:
        """Auto-generate a database description for a specific resource key."""
        config = RESOURCE_OPTIONS.get(res_key, {})
        auto = config.get("auto_fields", {})
        layer = agent.collected_fields.get("data_layer", auto.get("data_layer", ""))
        enterprise = flow.selected_enterprise or ""
        subgroup = flow.subgroup or ""
        source = agent.collected_fields.get("source_name", "")
        product = agent.collected_fields.get("data_product_name", "")
        purpose = agent.collected_fields.get("purpose", flow.serving_purpose or "")
        entity = f"{enterprise} {subgroup}".strip() if subgroup else enterprise
        data_subject = source or product or "data"

        if purpose:
            return f"Stores {data_subject.capitalize()} {layer.capitalize()} Data Product for {entity} {purpose}"
        return f"Database for {data_subject} to {layer} patterns for {entity}"

    async def _generate_yaml_silent(self, session, agent) -> str | None:
        """Generate YAML without showing it to the user. Returns YAML string or None."""
        import json as _json
        resource_context = schema_registry.get_resource_context(agent.resource_type)

        prompt = YAML_GENERATION_PROMPT.format(
            resource_type=agent.resource_type,
            resource_context=resource_context,
            collected_fields=_json.dumps(agent.collected_fields, indent=2),
        )

        messages = self._build_messages(session, prompt)

        for attempt in range(2):
            try:
                result = await llm_client.extract_json(messages, max_tokens=4096)
                yaml_output = result.get("yaml_output", "")

                # Safety net: reassemble split YAML
                expected_keys = {"yaml_output", "message"}
                extra_keys = set(result.keys()) - expected_keys
                if extra_keys:
                    lines = [yaml_output.rstrip("\n")]
                    for key in result:
                        if key in expected_keys:
                            continue
                        lines.append(key.rstrip("\n"))
                        val = result[key]
                        if isinstance(val, str) and val.strip():
                            lines.append(val.rstrip("\n"))
                    yaml_output = "\n".join(lines) + "\n"

                if yaml_output:
                    agent.generated_yaml = yaml_output
                    agent.phase = "awaiting_confirmation"
                    return yaml_output

                if attempt == 0:
                    messages.append({"role": "assistant", "content": _json.dumps(result)})
                    messages.append({"role": "user", "content": "yaml_output was empty. Please generate the complete YAML."})
                    continue
            except Exception as e:
                logger.error(f"Silent YAML generation failed: {e}")
                if attempt == 0:
                    continue

        return None

    def _show_multi_yaml_preview(self, session: SessionState, flow) -> dict:
        """Show all generated YAMLs for multi-resource confirmation."""
        parts = []
        for i, entry in enumerate(flow.completed_resource_yamls, 1):
            parts.append(
                f"### {i}. {entry['label']} ({entry['resource_type'].upper()})\n\n"
                f"```yaml\n{entry['yaml']}\n```"
            )

        combined = "\n\n---\n\n".join(parts)

        # Set the last resource as the current agent for confirmation flow
        last = flow.completed_resource_yamls[-1]
        agent = session.start_new_resource()
        agent.resource_type = last["resource_type"]
        agent.collected_fields = last["fields"]
        agent.generated_yaml = last["yaml"]
        # Store the full preview set; add to batch only after user confirms.
        agent.multi_preview_entries = list(flow.completed_resource_yamls)
        agent.phase = "awaiting_confirmation"

        # Clear the structured flow
        session.structured_flow = None

        count = len(flow.completed_resource_yamls)
        return self._response(
            f"Here are your **{count} resource configurations**. "
            f"Please review and **confirm**, **edit**, or **cancel**.\n\n{combined}",
            resource_type=last["resource_type"],
            resource_status="awaiting_confirmation",
            generated_yaml=last["yaml"],
            needs_confirmation=True,
        )

    def _check_missing_fields(self, agent) -> list[str]:
        """Return list of missing required fields based on resource type."""
        fields = agent.collected_fields
        missing = []

        if agent.resource_type == "s3":
            for f in ["intake_id", "bucket_name", "bucket_description",
                       "aws_account_id", "usage_type", "enterprise_or_func_name"]:
                if not fields.get(f):
                    missing.append(f)
        elif agent.resource_type in ("glue_db", "glue-db"):
            base_required = ["intake_id", "database_name", "database_s3_location",
                             "aws_account_id", "data_env", "data_layer",
                             "data_construct", "enterprise_or_func_name",
                             "data_owner_email", "data_owner_github_uname", "data_leader"]
            construct = fields.get("data_construct", "").lower()
            if construct == "source":
                base_required.append("source_name")
            elif construct == "dataproduct":
                base_required.append("data_product_name")
            for f in base_required:
                if not fields.get(f):
                    missing.append(f)

        return missing

    def _derive_account_from_flow(self, flow: StructuredFlow, agent: AgentState):
        """Derive aws_account_id based on structured flow decisions."""
        from app.agents.field_deriver import (
            _S3_SOURCE_ACCOUNT, _S3_DATAPRODUCT_ACCOUNT,
            _GLUE_LAKEHOUSE_DEV, _GLUE_LAKEHOUSE_PRD, _GLUE_COMPUTE,
        )

        config = flow.get_resource_config()
        env = flow.environment  # "dev" or "prd"
        enterprise = (flow.selected_enterprise or "").lower()
        resource_type = config.get("resource_type")

        if resource_type == "s3":
            usage_type = config.get("auto_fields", {}).get("usage_type", "")
            if usage_type == "Source":
                acct = _S3_SOURCE_ACCOUNT.get(env)
                if acct:
                    agent.collected_fields["aws_account_id"] = acct
            elif usage_type == "DataProduct":
                ent_map = _S3_DATAPRODUCT_ACCOUNT.get(enterprise)
                if ent_map:
                    acct = ent_map.get(env)
                    if acct:
                        agent.collected_fields["aws_account_id"] = acct
            elif usage_type in ("Scripts", "EngAssets"):
                # User chose lakehouse or compute
                if flow.account_placement == "lakehouse":
                    acct = _S3_SOURCE_ACCOUNT.get(env)
                    if acct:
                        agent.collected_fields["aws_account_id"] = acct
                elif flow.account_placement == "compute":
                    ent_map = _S3_DATAPRODUCT_ACCOUNT.get(enterprise)
                    if ent_map:
                        acct = ent_map.get(env)
                        if acct:
                            agent.collected_fields["aws_account_id"] = acct

        elif resource_type == "glue_db":
            data_layer = config.get("auto_fields", {}).get("data_layer", "")
            if data_layer in ("raw", "raw_serving"):
                acct = _GLUE_LAKEHOUSE_DEV if env == "dev" else _GLUE_LAKEHOUSE_PRD
                agent.collected_fields["aws_account_id"] = acct
            elif data_layer in ("curated", "serving"):
                ent_map = _GLUE_COMPUTE.get(enterprise)
                if ent_map:
                    acct = ent_map.get(env)
                    if acct:
                        agent.collected_fields["aws_account_id"] = acct
            elif data_layer == "internal":
                if flow.account_placement == "lakehouse":
                    acct = _GLUE_LAKEHOUSE_DEV if env == "dev" else _GLUE_LAKEHOUSE_PRD
                    agent.collected_fields["aws_account_id"] = acct
                elif flow.account_placement == "compute":
                    ent_map = _GLUE_COMPUTE.get(enterprise)
                    if ent_map:
                        acct = ent_map.get(env)
                        if acct:
                            agent.collected_fields["aws_account_id"] = acct

    # ─── BATCH HANDLERS ───────────────────────────────────────

    async def _after_review_passed(self, session: SessionState, agent: AgentState,
                                    prefix_message: str = "") -> dict:
        """Called when review passes. Adds resource to batch and decides next step."""
        entry = session.add_to_batch(agent)
        batch_count = len(session.batch)
        rtype = entry["resource_type"].upper()
        name = entry["resource_name"]

        # Clear current agent — resource is now in batch
        session.current_agent = None

        # ── Multi-resource: if structured flow has more resources, advance ──
        flow = session.structured_flow
        if flow and flow.has_more_resources():
            # In the batched flow, all resources should already be processed together
            # This path is legacy — clear the flow and continue normally
            session.structured_flow = None

        # If structured flow exists but no more resources, clear it
        if flow:
            session.structured_flow = None

        # Check if there's a paused PR flow to resume (user added resource mid-PR)
        resume = resume_pr_from_pause(session)
        if resume:
            resume["message"] = (
                f"{prefix_message}"
                f"✅ **{rtype}** `{name}` added to batch ({batch_count} resources).\n\n"
                + resume["message"]
            )
            return resume

        if batch_count == 1:
            # First resource — offer single PR or add more
            msg = (
                f"{prefix_message}"
                f"**{rtype}** `{name}` is ready!\n\n"
                f"Would you like to:\n"
                f"1. **Create PR** — submit this resource now\n"
                f"2. **Add another resource** — build more configs first\n"
            )
        else:
            # 2+ resources — batch mode
            msg = (
                f"{prefix_message}"
                f"**{rtype}** `{name}` added to batch ({batch_count} resources).\n\n"
                f"Add another resource, **\"show batch\"**, or **\"create PR\"** to submit all."
            )

        return self._response(msg, resource_type=entry["resource_type"],
                              resource_status="batch_prompt")

    async def _handle_batch_prompt(self, session: SessionState, user_message: str) -> dict:
        """Route batch-level commands: create PR, show batch, edit N, remove N, or new resource."""
        msg_lower = user_message.strip().lower()

        # ── Create PR ──
        if any(t in msg_lower for t in ["create pr", "submit", "make pr", "proceed"]):
            if not session.batch:
                return self._response("No resources in your batch. Create a resource first.")
            return await self._handle_batch_pr_setup(session)

        # ── Show batch ──
        if any(t in msg_lower for t in ["show batch", "batch summary", "list batch"]):
            summary = session.get_batch_summary()
            return self._response(
                f"{summary}\n\n"
                f"Say **\"create PR\"**, **\"edit N\"**, **\"remove N\"**, or add another resource.",
                resource_status="batch_prompt",
            )

        # ── Remove N ──
        remove_match = re.match(r'remove\s+(\d+)', msg_lower)
        if remove_match:
            idx = int(remove_match.group(1))
            removed = session.remove_from_batch(idx)
            if removed:
                remaining = len(session.batch)
                msg = (
                    f"Removed {removed['resource_type'].upper()} `{removed['resource_name']}`. "
                    f"{remaining} resource{'s' if remaining != 1 else ''} remaining."
                )
                if remaining > 0:
                    msg += f"\n\nSay **\"create PR\"** or add another resource."
                    return self._response(msg, resource_status="batch_prompt")
                else:
                    msg += "\n\nBatch is empty. Start by creating a resource."
                    return self._response(msg)
            return self._response(
                f"Invalid index. Your batch has {len(session.batch)} resource(s). "
                f"Say 'remove 1', 'remove 2', etc.",
                resource_status="batch_prompt",
            )

        # ── Edit N ──
        edit_match = re.match(r'edit\s+(\d+)', msg_lower)
        if edit_match:
            idx = int(edit_match.group(1))
            agent = session.edit_batch_resource(idx)
            if agent:
                resource_name = (
                    agent.collected_fields.get("database_name")
                    or agent.collected_fields.get("bucket_name")
                    or agent.collected_fields.get("role_name")
                    or "resource"
                )
                return self._response(
                    f"Editing {agent.resource_type.upper()} `{resource_name}`.\n\n"
                    f"Current config:\n```yaml\n{agent.generated_yaml}\n```\n\n"
                    f"What would you like to change?",
                    resource_type=agent.resource_type,
                    resource_status="awaiting_confirmation",
                    generated_yaml=agent.generated_yaml,
                )
            return self._response(
                f"Invalid index. Your batch has {len(session.batch)} resource(s).",
                resource_status="batch_prompt",
            )

        # ── Not a batch command → treat as new resource request ──
        session.current_agent = None
        return await self._handle_idle(session, user_message)

    async def _handle_batch_pr_setup(self, session: SessionState) -> dict:
        """Present multi-step PR setup for the entire batch."""
        batch = session.batch
        count = len(batch)

        type_counts = Counter(e["resource_type"].upper() for e in batch)
        type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())

        # Check GitHub token
        github_token = session.github_token
        if not github_token:
            github_token = await self._load_github_token_from_db(session.session_id)
            if github_token:
                session.github_token = github_token

        if not github_token:
            for entry in batch:
                session.completed_resources.append(entry)
            session.clear_batch()
            return self._response(
                f"**{count} resources ready!** ({type_summary})\n\n"
                f"Connect your GitHub account to create a PR.\n"
                f"Your configurations are saved.",
                resource_status="confirmed",
            )

        # Create a batch agent and delegate to present_pr_setup
        agent = session.start_new_resource()
        agent.resource_type = "batch"
        agent.collected_fields = {"batch_count": count, "type_summary": type_summary}
        agent.generated_yaml = "\n---\n".join(e["yaml"] for e in batch)

        return await present_pr_setup(session, agent)

    async def _handle_config_edit_from_pr(
        self, session: SessionState, agent: AgentState,
        extracted_fields: dict, prefix_message: str = ""
    ) -> dict:
        """User wants to edit resource config fields while in PR setup phase.
        
        Flow: update fields → regenerate YAML → auto-confirm → re-review → back to PR setup.
        This creates a seamless round-trip without making the user re-confirm manually.
        """
        if not extracted_fields:
            return self._response(
                "Which field would you like to change, and to what value?\n"
                "For example: *\"change bucket_name to dev-lh1-corp-src\"*",
                resource_type=agent.resource_type,
                resource_status="pr_setup",
                generated_yaml=agent.generated_yaml,
            )

        # Preserve PR settings so we return to the same PR setup state
        saved_pr_branch = agent.pr_branch_name
        saved_pr_title = agent.pr_title
        saved_pr_body = agent.pr_body
        saved_fork_exists = agent.fork_exists
        saved_fork_full_name = agent.fork_full_name
        saved_pr_target_branch = agent.pr_target_branch
        saved_available_branches = agent.available_branches

        # Update collected fields with the new values
        agent.collected_fields.update(extracted_fields)

        # Regenerate YAML with updated fields
        agent.phase = "collecting"  # Temporarily needed for _generate_yaml
        regen_result = await self._generate_yaml(
            session, agent,
            prefix_message=prefix_message or "Configuration updated.",
        )

        # If YAML generation failed, return the error as-is
        if agent.phase != "awaiting_confirmation":
            return regen_result

        # Auto-confirm: skip showing the preview, go straight to review
        agent.phase = "awaiting_confirmation"
        finalize_result = await self._finalize_resource(session, agent)

        # Restore PR settings regardless of review outcome
        agent.pr_branch_name = saved_pr_branch
        agent.pr_title = saved_pr_title
        agent.pr_body = saved_pr_body
        agent.fork_exists = saved_fork_exists
        agent.fork_full_name = saved_fork_full_name
        agent.pr_target_branch = saved_pr_target_branch
        agent.available_branches = saved_available_branches

        return finalize_result

    async def _proceed_to_pr_setup(self, session: SessionState, agent: AgentState,
                                    prefix_message: str = "") -> dict:
        """Move from review to PR setup. Checks GitHub token first."""
        github_token = session.github_token
        if not github_token:
            github_token = await self._load_github_token_from_db(session.session_id)
            if github_token:
                session.github_token = github_token

        if not github_token:
            agent.phase = "done"
            rtype = (agent.resource_type or "unknown").upper()
            session.complete_current_resource()
            msg = prefix_message + (
                f"**{rtype} configuration confirmed!**\n\n"
                f"Connect your GitHub account to enable automatic PR creation.\n\n"
                f"Would you like to create another resource, or are we done?"
            )
            return self._response(
                msg,
                resource_type=agent.resource_type,
                resource_status="confirmed",
                generated_yaml=agent.generated_yaml,
            )

        agent.phase = "pr_setup"
        pr_response = await present_pr_setup(session, agent)

        # Prepend any prefix message (e.g. review pass message)
        if prefix_message:
            pr_response["message"] = prefix_message + pr_response["message"]

        return pr_response

    async def _try_post_completion(self, session: SessionState, user_message: str) -> dict | None:
        """Check if user is referencing a completed resource. Returns None if not.
        
        Called when current_agent is None but completed_resources exist.
        Only handles clear references (show yaml, create PR, edit config).
        Returns None for anything else so _handle_idle processes it.
        """
        msg_lower = user_message.strip().lower()
        last_resource = session.completed_resources[-1] if session.completed_resources else None
        if not last_resource:
            return None

        yaml_content = last_resource.get("yaml", "")
        fields = last_resource.get("fields", {})
        rtype = last_resource.get("resource_type", "unknown")
        pr_url = last_resource.get("pr_url")

        # ── Show YAML ──
        show_yaml_triggers = ["show yaml", "show the yaml", "show my yaml",
                              "show config", "show my config", "show the config",
                              "see the yaml", "view yaml", "view config"]
        if any(trigger in msg_lower for trigger in show_yaml_triggers):
            return self._response(
                f"Here is your last {rtype.upper()} configuration:\n\n"
                f"```yaml\n{yaml_content}\n```\n\n"
                f"Would you like to create another resource, edit this one, or are we done?",
                resource_type=rtype,
                resource_status="confirmed",
                generated_yaml=yaml_content,
            )

        # ── Create PR (if no PR was created yet) ──
        if not pr_url:
            pr_triggers = ["create pr", "make pr", "create a pr",
                           "make a pr", "submit pr"]
            if any(trigger in msg_lower for trigger in pr_triggers):
                agent = session.start_new_resource()
                agent.resource_type = rtype
                agent.collected_fields = fields.copy()
                agent.generated_yaml = yaml_content
                agent.phase = "pr_setup"
                session.completed_resources.pop()
                return await self._proceed_to_pr_setup(session, agent)

        # Not a reference to the completed resource
        return None

    async def _handle_post_completion(self, session: SessionState, user_message: str) -> dict:
        """After resource confirmed, check if user still wants to interact with it.
        
        Handles: show yaml, create PR, edit config, or start a new resource.
        """
        msg_lower = user_message.strip().lower()

        # Check if the user is referencing the last completed resource
        last_resource = session.completed_resources[-1] if session.completed_resources else None

        if last_resource:
            yaml_content = last_resource.get("yaml", "")
            fields = last_resource.get("fields", {})
            rtype = last_resource.get("resource_type", "unknown")
            pr_url = last_resource.get("pr_url")

            # ── Show YAML ──
            show_yaml_triggers = ["show yaml", "show the yaml", "show my yaml",
                                  "show config", "show my config", "show the config",
                                  "yaml", "see the yaml", "view yaml", "view config"]
            if any(trigger in msg_lower for trigger in show_yaml_triggers):
                return self._response(
                    f"Here is your last {rtype.upper()} configuration:\n\n"
                    f"```yaml\n{yaml_content}\n```\n\n"
                    f"Would you like to create another resource, or are we done?",
                    resource_type=rtype,
                    resource_status="confirmed",
                    generated_yaml=yaml_content,
                )

            # ── Create PR / proceed with PR (if no PR was created yet) ──
            if not pr_url:
                pr_triggers = ["create pr", "make pr", "proceed", "create a pr",
                               "make a pr", "go ahead", "pr"]
                if any(trigger in msg_lower for trigger in pr_triggers):
                    # Restore agent state so we can re-enter PR setup
                    agent = session.start_new_resource()
                    agent.resource_type = rtype
                    agent.collected_fields = fields.copy()
                    agent.generated_yaml = yaml_content
                    agent.phase = "pr_setup"
                    # Remove last from completed_resources since we're re-activating it
                    session.completed_resources.pop()
                    return await self._proceed_to_pr_setup(session, agent)

            # ── Edit config (user wants to change something in the last resource) ──
            edit_triggers = ["edit", "change", "update", "fix", "modify"]
            if any(trigger in msg_lower for trigger in edit_triggers):
                # Re-activate the resource for editing
                agent = session.start_new_resource()
                agent.resource_type = rtype
                agent.collected_fields = fields.copy()
                agent.generated_yaml = yaml_content
                agent.phase = "awaiting_confirmation"
                agent.initial_listing_shown = True
                agent.optional_fields_offered = True
                # Remove from completed since we're re-activating
                session.completed_resources.pop()
                return await self._handle_confirmation(session, user_message)

        # Default: start fresh — route through idle for new resource or general chat
        session.current_agent = None
        return await self._handle_idle(session, user_message)

    async def _handle_session_end(self, session: SessionState) -> dict:
        """Show summary and say goodbye."""
        session.current_agent = None

        # Merge batch resources into completed for summary
        all_resources = session.completed_resources + session.batch
        session.clear_batch()

        if not all_resources:
            return self._response(
                "Goodbye! No resources were created this session. Come back anytime."
            )

        parts = ["**Session Complete!** Here's what we created:\n"]
        for i, res in enumerate(all_resources, 1):
            rtype = res.get("resource_type", "unknown").upper()
            fields = res.get("fields", {})
            name = (
                fields.get("bucket_name")
                or fields.get("database_name")
                or fields.get("role_name")
                or res.get("resource_name")
                or "unnamed"
            )
            parts.append(f"**{i}. {rtype}** — `{name}`")
            pr_url = res.get("pr_url")
            if pr_url:
                parts.append(f"   PR: {pr_url}")

        parts.append(f"\n**{len(all_resources)} resource(s)** configured. Goodbye!")
        return self._response("\n".join(parts))

    async def _handle_pr_status(self, session: SessionState) -> dict:
        """Show the user their PRs created via the chatbot, with live status from GitHub."""
        from app.models.database import async_session_factory
        from app.models.schemas import PRRecord
        from app.services.scm_adapter import get_pr_live_status
        from sqlalchemy import select

        username = session.github_username
        if not username:
            return self._response(
                "Connect your GitHub account first to see your PRs."
            )

        try:
            async with async_session_factory() as db:
                stmt = (
                    select(PRRecord)
                    .where(PRRecord.github_username == username)
                    .order_by(PRRecord.created_at.desc())
                    .limit(10)
                )
                result = await db.execute(stmt)
                records = result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to fetch PR records: {e}")
            return self._response("Sorry, I couldn't fetch your PR records right now.")

        if not records:
            return self._response(
                "No PRs found for your account. Create a resource and raise a PR first!"
            )

        # Fetch live status for each PR
        parts = ["📋 **Your PRs:**\n"]
        parts.append("| # | Title | Status | Resources | Link |")
        parts.append("|---|-------|--------|-----------|------|")

        status_icons = {
            "open": "🟢 Open",
            "closed": "🔴 Closed",
            "merged": "🟣 Merged",
            "unknown": "⚪ Unknown",
        }

        for i, rec in enumerate(records, 1):
            # Try to get live status
            if session.github_token:
                try:
                    live = await get_pr_live_status(session.github_token, rec.pr_url)
                    state = live.get("state", "unknown")
                except Exception:
                    state = "unknown"
            else:
                state = "unknown"

            icon = status_icons.get(state, f"⚪ {state}")
            title = rec.title or "Untitled"
            count = rec.resource_count or 1
            types = ", ".join(t.upper() for t in (rec.resource_types or []))
            resource_info = f"{count} ({types})" if types else str(count)
            pr_link = f"[PR #{rec.pr_number}]({rec.pr_url})" if rec.pr_number else f"[Link]({rec.pr_url})"

            parts.append(f"| {i} | {title} | {icon} | {resource_info} | {pr_link} |")

        parts.append(f"\n_Showing up to 10 most recent PRs._")
        return self._response("\n".join(parts))

    # ─── HELPERS ───────────────────────────────────────────────

    def _match_fix_option(self, msg_lower: str, agent: AgentState) -> dict | None:
        """Check if user is selecting a numbered fix option (e.g. 'option 1', '1', 'fix 1').
        
        Returns the changes dict if matched, None otherwise.
        Only considers concrete values — skips descriptive suggestions like
        'Use your Lakehouse account ID'.
        """
        match = re.match(r'(?:option|fix|go with|choose|pick|select)?\s*(\d+)', msg_lower)
        if not match:
            return None

        option_num = int(match.group(1))
        if not agent.review_result:
            return None

        # Collect all fix options across all violations
        all_options = []
        for v in agent.review_result.violations:
            for opt in v.fix_options:
                all_options.append(opt)

        if option_num < 1 or option_num > len(all_options):
            return None

        selected = all_options[option_num - 1]
        changes = selected.get("changes", {})
        if not changes:
            return None

        # Filter out descriptive/non-concrete suggestions
        concrete = {}
        for k, v in changes.items():
            v_str = str(v).lower()
            # Skip vague suggestions like "Use your Lakehouse account ID"
            if v_str.startswith("use ") or v_str.startswith("modify ") or "e.g." in v_str:
                continue
            concrete[k] = v

        return concrete if concrete else None

    def _cancel_current_resource(self, session: SessionState) -> dict:
        """Cancel the current resource and return a batch-aware response."""
        session.current_agent = None

        # Check if there's a paused PR flow to resume
        resume = resume_pr_from_pause(session)
        if resume:
            return resume

        batch_count = len(session.batch)
        if batch_count > 0:
            summary = session.get_batch_summary()
            return self._response(
                f"Current resource cancelled.\n\n"
                f"Your batch still has {batch_count} resource{'s' if batch_count != 1 else ''}:\n\n"
                f"{summary}\n\n"
                f"Say **\"create PR\"** to submit, **\"add another\"** to continue, or **\"show batch\"** for details.",
                resource_status="batch_prompt",
            )
        return self._response("Configuration cancelled. Let me know if you'd like to start over.")

    def _build_messages(self, session: SessionState, user_prompt: str) -> list[dict]:
        """Build the messages array for an LLM call."""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *_history_provider.get_messages(session)[:-1],  # History minus current message
            {"role": "user", "content": user_prompt},
        ]

    async def _load_github_token_from_db(self, session_id: str) -> Optional[str]:
        """Fallback: load GitHub token from DB if in-memory state lost (e.g., server restart)."""
        try:
            from app.models.database import async_session_factory
            from app.models.schemas import ChatSession
            from sqlalchemy import select

            async with async_session_factory() as db:
                result = await db.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
                db_session = result.scalar_one_or_none()
                if db_session and db_session.github_token:
                    logger.info(f"Loaded GitHub token from DB for session {session_id}")
                    return db_session.github_token
        except Exception as e:
            logger.warning(f"Failed to load GitHub token from DB: {e}")
        return None

    async def _try_resume_from_db(self, session: SessionState):
        """
        Attempt to rebuild agent state from the database after a server restart.
        Loads: conversation_summary, recent messages (last 20), github_token,
        and latest active resource state.

        What IS restored: resource_type, collected_fields, current_field,
        generated_yaml, phase, conversation_history (last 20), conversation_summary,
        github_token, github_username.

        What is NOT restored: field_retries (reset to 0 — acceptable tradeoff).
        """
        try:
            from app.models.database import async_session_factory
            from app.models.schemas import ResourceState, ChatMessage, ChatSession, ResourceStatus
            from sqlalchemy import select

            async with async_session_factory() as db:
                # 1. Load session data (summary, token)
                db_session_result = await db.execute(
                    select(ChatSession).where(ChatSession.id == session.session_id)
                )
                chat_session = db_session_result.scalar_one_or_none()
                if not chat_session:
                    return

                session.conversation_summary = chat_session.conversation_summary
                session.github_token = chat_session.github_token
                session.github_username = chat_session.github_username

                # 2. Load recent messages into in-memory history (last 20)
                msgs_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session.session_id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(20)
                )
                for msg in reversed(msgs_result.scalars().all()):
                    session.conversation_history.append({
                        "role": msg.role.value.lower(),
                        "content": msg.content,
                    })

                # 3. Load latest active resource state (if any)
                res_result = await db.execute(
                    select(ResourceState)
                    .where(
                        ResourceState.session_id == session.session_id,
                        ResourceState.status.in_([
                            ResourceStatus.COLLECTING,
                            ResourceStatus.AWAITING_CONFIRMATION,
                        ]),
                    )
                    .order_by(ResourceState.updated_at.desc())
                    .limit(1)
                )
                resource_state = res_result.scalar_one_or_none()

                if resource_state:
                    agent = session.start_new_resource()
                    agent.resource_type = resource_state.resource_type
                    agent.collected_fields = resource_state.collected_fields or {}
                    agent.current_field = resource_state.current_field
                    agent.generated_yaml = resource_state.generated_yaml

                    if resource_state.status == ResourceStatus.COLLECTING:
                        agent.phase = "collecting"
                    elif resource_state.status == ResourceStatus.AWAITING_CONFIRMATION:
                        agent.phase = "awaiting_confirmation"

                if session.conversation_history:
                    logger.info(
                        f"Resumed session {session.session_id} from DB: "
                        f"{len(session.conversation_history)} messages, "
                        f"resource={'yes' if resource_state else 'no'}"
                    )

        except Exception as e:
            logger.warning(f"Session resume from DB failed: {e}", exc_info=True)
            # Graceful degradation — agent starts fresh

    def _response(
        self,
        message: str,
        resource_type: str = None,
        resource_status: str = None,
        generated_yaml: str = None,
        needs_confirmation: bool = False,
        pr_url: str = None,
        review_result: dict = None,
        options: list = None,
        options_multi_select: bool = False,
    ) -> dict:
        return {
            "message": message,
            "resource_type": resource_type,
            "resource_status": resource_status,
            "generated_yaml": generated_yaml,
            "needs_confirmation": needs_confirmation,
            "pr_url": pr_url,
            "review_result": review_result,
            "options": options,
            "options_multi_select": options_multi_select,
        }


# ── Singleton — delegates to the new Orchestrator ─────────────
# This keeps backward compatibility with routes.py and other imports.

from app.agents.orchestrator import orchestrator as _orchestrator


class _GeneratorShim:
    """Backward-compatible shim: delegates process_message to the Orchestrator."""

    async def process_message(self, session_id: str, user_message: str) -> dict:
        return await _orchestrator.process_message(session_id, user_message)


generator_agent = _GeneratorShim()
