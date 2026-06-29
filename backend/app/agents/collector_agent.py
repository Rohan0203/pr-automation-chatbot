"""
Collector Agent — handles the field collection phase via LLM.

This is the slimmed-down version of the old GeneratorAgent, containing
only the collection logic:
  - Extract fields from user messages via LLM + resource context
  - Handle field validation and retries
  - Trigger YAML generation when all fields are collected

All orchestration, routing, confirmation, batch, and PR logic has been
moved to their respective handler modules.
"""
import json
import logging

from app.agents.prompts import SYSTEM_PROMPT, RESOURCE_ACTION_PROMPT
from app.agents.session_state import AgentState, SessionState
from app.agents.response_decorator import build_response
from app.agents.yaml_utils import generate_yaml
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry

logger = logging.getLogger(__name__)


class CollectorAgent:
    """
    Handles the COLLECTING phase — extracts fields from user messages,
    validates them against the resource guide, and triggers YAML generation
    when all fields are ready.
    """

    async def handle_collecting(
        self,
        session: SessionState,
        user_message: str,
        build_messages_fn,
    ) -> dict:
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

        messages = build_messages_fn(session, prompt)

        try:
            result = await llm_client.extract_json(messages, max_tokens=4096)
        except Exception as e:
            logger.error(f"Collection LLM call failed: {e}")
            return build_response(
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

        logger.info(
            "[COLLECTOR] LLM response:\n"
            "  resource_type : %s\n"
            "  next_action   : %s\n"
            "  next_field    : %s\n"
            "  extracted     : %s\n"
            "  invalid       : %s\n"
            "  retries       : %s\n"
            "  fields_total  : %d\n"
            "  message_start : %.120s",
            agent.resource_type,
            next_action,
            next_field,
            list(extracted.keys()) if extracted else [],
            list(invalid.keys()) if invalid else [],
            retries,
            len(agent.collected_fields) + len(extracted if isinstance(extracted, dict) else {}),
            message[:120].replace('\n', ' ') if message else '(empty)',
        )

        # Update state
        if extracted and isinstance(extracted, dict):
            agent.collected_fields.update(extracted)
        if retries and isinstance(retries, dict):
            agent.field_retries.update(retries)
        if next_field:
            agent.current_field = next_field

        # Route based on next_action
        if next_action == "cancel":
            logger.info("[COLLECTOR] → cancel")
            session.current_agent = None
            return build_response("Configuration cancelled. Let me know if you'd like to start over.")

        if next_action == "abort":
            logger.info("[COLLECTOR] → abort (too many retries)")
            session.current_agent = None
            return build_response(
                message or "Session aborted due to too many invalid attempts. Please restart."
            )

        if next_action == "confirm":
            # Check if we should auto-apply optional fields first
            resource_context_text = schema_registry.get_resource_context(agent.resource_type) or ""
            has_optional_fields = "No optional fields" not in resource_context_text
            uses_field_classification = "Field Classification" in resource_context_text
            if (
                not agent.optional_fields_offered
                and has_optional_fields
                and not uses_field_classification
            ):
                agent.optional_fields_offered = True
                logger.info(
                    "[COLLECTOR] → forcing optional fields prompt before confirm"
                )
                return await self.handle_collecting(
                    session,
                    "[System: All mandatory fields collected. Present optional fields with defaults per the guide.]",
                    build_messages_fn,
                )
            # All fields collected — generate YAML
            logger.info("[COLLECTOR] → confirm → generate_yaml (fields=%d)", len(agent.collected_fields))
            agent.optional_fields_offered = True
            return await generate_yaml(
                session, agent, build_messages_fn, prefix_message=message
            )

        if next_action == "ask_optional":
            agent.optional_fields_offered = True
            return build_response(
                message,
                resource_type=agent.resource_type,
                resource_status="collecting",
            )

        if next_action == "generate_yaml" and yaml_output:
            agent.generated_yaml = yaml_output
            agent.phase = "awaiting_confirmation"
            preview = f"```yaml\n{agent.generated_yaml}\n```\n\n**Confirm**, **edit**, or **cancel**?"
            return build_response(
                preview,
                resource_type=agent.resource_type,
                resource_status="awaiting_confirmation",
                generated_yaml=agent.generated_yaml,
                needs_confirmation=True,
            )

        # Default: ask_field or answer_question
        return build_response(
            message,
            resource_type=agent.resource_type,
            resource_status="collecting",
        )
