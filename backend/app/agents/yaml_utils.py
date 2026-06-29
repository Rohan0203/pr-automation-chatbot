"""
YAML Generation Utilities — shared helpers for YAML generation and reassembly.

Consolidates the duplicate YAML generation logic that was in generator_agent.py.
Used by both the collector agent (interactive YAML gen) and the structured flow
handler (silent multi-resource YAML gen).
"""
import json
import logging
from typing import Optional

from app.agents.prompts import YAML_GENERATION_PROMPT, SYSTEM_PROMPT
from app.agents.yaml_validator import validate_yaml
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry

logger = logging.getLogger(__name__)


def reassemble_split_yaml(result: dict) -> str:
    """
    Fix LLM responses where YAML is split across JSON keys.

    When the LLM returns extra keys beyond 'yaml_output' and 'message',
    it means the YAML was incorrectly split. This function reassembles it.
    """
    yaml_output = result.get("yaml_output", "")
    expected_keys = {"yaml_output", "message"}
    extra_keys = set(result.keys()) - expected_keys

    if not extra_keys:
        return yaml_output

    logger.warning(
        f"LLM split YAML across JSON keys! Reassembling from {len(extra_keys)} extra keys"
    )
    lines = [yaml_output.rstrip("\n")] if yaml_output else []
    for key in result:
        if key in expected_keys:
            continue
        lines.append(key.rstrip("\n"))
        val = result[key]
        if isinstance(val, str) and val.strip():
            lines.append(val.rstrip("\n"))
    reassembled = "\n".join(lines) + "\n"
    logger.info(f"Reassembled YAML ({len(reassembled)} chars): {reassembled[:300]}")
    return reassembled


def build_yaml_prompt(resource_type: str, collected_fields: dict) -> str:
    """Build the YAML generation prompt for a given resource type and fields."""
    resource_context = schema_registry.get_resource_context(resource_type)
    return YAML_GENERATION_PROMPT.format(
        resource_type=resource_type,
        resource_context=resource_context,
        collected_fields=json.dumps(collected_fields, indent=2),
    )


async def generate_yaml(
    session,
    agent,
    build_messages_fn,
    prefix_message: str = "",
    silent: bool = False,
) -> dict | str | None:
    """
    Unified YAML generation with retry and validation.

    Args:
        session: SessionState
        agent: AgentState with resource_type and collected_fields
        build_messages_fn: callable(session, prompt) -> list[dict]
        prefix_message: optional message to prepend to the preview
        silent: if True, returns yaml string (or None) instead of a response dict

    Returns:
        - If silent=True: YAML string or None
        - If silent=False: response dict with yaml preview or error
    """
    prompt = build_yaml_prompt(agent.resource_type, agent.collected_fields)
    messages = build_messages_fn(session, prompt)

    if not silent:
        logger.info(
            f"YAML generation prompt length: {len(prompt)} chars, "
            f"messages count: {len(messages)}"
        )

    for attempt in range(2):
        try:
            result = await llm_client.extract_json(messages, max_tokens=4096)
            yaml_output = result.get("yaml_output", "")

            if not silent:
                logger.info(
                    f"YAML generation attempt {attempt}: "
                    f"yaml_output length={len(yaml_output)}, "
                    f"content='{yaml_output[:200]}'"
                )
                logger.info(f"YAML generation full result keys: {list(result.keys())}")

            # Reassemble if LLM split YAML across JSON keys
            yaml_output = reassemble_split_yaml(result)

            if not yaml_output:
                if attempt == 0:
                    messages.append({"role": "assistant", "content": json.dumps(result)})
                    messages.append({
                        "role": "user",
                        "content": "yaml_output was empty. Please generate the complete YAML.",
                    })
                    continue

                if silent:
                    return None
                return _error_response(agent, "Failed to generate YAML. Please try again.")

            if silent:
                # Silent mode: just return the YAML string
                agent.generated_yaml = yaml_output
                agent.phase = "awaiting_confirmation"
                return yaml_output

            # Interactive mode: validate before showing
            validation = validate_yaml(yaml_output, agent.resource_type, agent.collected_fields)

            if validation.valid:
                agent.generated_yaml = yaml_output
                agent.phase = "awaiting_confirmation"
                warning_text = ""
                if validation.warnings:
                    warning_text = "⚠️ " + "; ".join(validation.warnings) + "\n\n"
                combined_prefix = (
                    (prefix_message + "\n\n" + warning_text).strip()
                    if warning_text
                    else prefix_message
                )
                return _preview_response(agent, combined_prefix)

            # Invalid — retry once with error feedback
            if attempt == 0:
                logger.warning(
                    f"YAML validation failed (attempt 1), retrying: {validation.error_summary}"
                )
                messages.append({"role": "assistant", "content": json.dumps(result)})
                messages.append({
                    "role": "user",
                    "content": (
                        f"The generated YAML has errors: {validation.error_summary}. "
                        f"Please fix these issues and regenerate the complete YAML."
                    ),
                })
                continue

            # Second attempt also failed — show with warning
            logger.warning(
                f"YAML validation failed after retry: {validation.error_summary}"
            )
            agent.generated_yaml = yaml_output
            agent.phase = "awaiting_confirmation"
            warning = f"⚠️ Note: {validation.error_summary}"
            combined = f"{prefix_message}\n\n{warning}" if prefix_message else warning
            return _preview_response(agent, combined.strip())

        except Exception as e:
            logger.error(f"YAML generation failed: {e}")
            if attempt == 0:
                continue
            if silent:
                return None
            return _error_response(agent, f"Failed to generate YAML: {e}. Please try again.")

    # Safety net
    if silent:
        return None
    return _error_response(agent, "Failed to generate YAML after multiple attempts. Please try again.")


def _preview_response(agent, prefix: str = "") -> dict:
    """Build the YAML preview response dict."""
    preview = f"```yaml\n{agent.generated_yaml}\n```\n\n"
    preview += "**Confirm**, **edit**, or **cancel**?"
    full_message = f"{prefix}\n\n{preview}" if prefix else preview

    return {
        "message": full_message.strip(),
        "resource_type": agent.resource_type,
        "resource_status": "awaiting_confirmation",
        "generated_yaml": agent.generated_yaml,
        "needs_confirmation": True,
        "pr_url": None,
        "review_result": None,
        "options": None,
        "options_multi_select": False,
    }


def _error_response(agent, message: str) -> dict:
    """Build an error response dict during YAML generation."""
    return {
        "message": message,
        "resource_type": agent.resource_type,
        "resource_status": "collecting",
        "generated_yaml": None,
        "needs_confirmation": False,
        "pr_url": None,
        "review_result": None,
        "options": None,
        "options_multi_select": False,
    }
