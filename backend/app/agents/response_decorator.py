"""
Response Decorator — formats and standardizes all agent responses
before they are sent to the frontend.

Uses template-based formatting for common states (fast, no LLM cost).
Ensures consistent markdown structure, progress indicators, and
action options across all conversation states.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# RESPONSE BUILDER — canonical response dict constructor
# ═══════════════════════════════════════════════════════════════

def build_response(
    message: str,
    resource_type: str = None,
    resource_status: str = None,
    generated_yaml: str = None,
    needs_confirmation: bool = False,
    pr_url: str = None,
    review_result: dict = None,
    options: list = None,
    options_multi_select: bool = False,
    _extracted_fields: dict = None,
) -> dict:
    """Build a canonical response dict for the API layer."""
    resp = {
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
    if _extracted_fields is not None:
        resp["_extracted_fields"] = _extracted_fields
    return resp


# ═══════════════════════════════════════════════════════════════
# STATE LABELS — human-readable labels for each agent phase
# ═══════════════════════════════════════════════════════════════

_STATE_LABELS = {
    "idle": None,
    "q1_env": "Step 1 of 3 — Environment",
    "q2_resource": "Step 2 of 3 — Resource Type",
    "q2_enterprise": "Step 2 of 3 — Enterprise",
    "q3_conditionals": "Step 3 of 3 — Configuration",
    "classification": "Final Details — Classification",
    "text_collection": "Final Details",
    "collecting": "Collecting Fields",
    "awaiting_confirmation": "Review Configuration",
    "reviewing": "Organizational Review",
    "review_failed": "Review — Issues Found",
    "batch_prompt": "Batch Management",
    "pr_setup": "PR Setup",
    "confirmed": "Complete",
}


def decorate_response(response: dict, phase: str = None) -> dict:
    """
    Apply formatting and decoration to an agent response.

    This is the main entry point called by the orchestrator after every
    agent handler returns a response. It adds:
    - Progress indicators for structured flow phases
    - Consistent formatting for YAML previews
    - Standardized action option presentation

    The original response dict is modified in-place and returned.
    """
    if not response or not response.get("message"):
        return response

    message = response["message"]
    resource_status = response.get("resource_status") or phase

    # Add phase context label if applicable
    label = _STATE_LABELS.get(resource_status)
    if label and not _already_has_step_indicator(message):
        # Don't double-add if the handler already included a step indicator
        pass  # Handlers already include step labels — avoid duplication

    # Ensure YAML previews are consistently formatted
    if response.get("needs_confirmation") and response.get("generated_yaml"):
        message = _ensure_yaml_block(message, response["generated_yaml"])
        response["message"] = message

    # Format review results consistently
    if response.get("review_result") and resource_status == "review_failed":
        # Review formatting is already handled by the review handler
        pass

    return response


def format_field_summary(collected_fields: dict, resource_type: str = None) -> str:
    """Format collected fields as a clean markdown table."""
    if not collected_fields:
        return "_No fields collected yet._"

    lines = ["| Field | Value |", "|-------|-------|"]
    for key, value in collected_fields.items():
        display_val = str(value)
        if len(display_val) > 60:
            display_val = display_val[:57] + "..."
        lines.append(f"| `{key}` | {display_val} |")
    return "\n".join(lines)


def format_batch_summary(batch: list) -> str:
    """Format a batch of resources as a summary table."""
    if not batch:
        return "_No resources in batch._"

    count = len(batch)
    lines = [
        f"📦 **Batch** ({count} resource{'s' if count != 1 else ''}):\n",
        "| # | Type | Name | Intake ID |",
        "|---|------|------|-----------|",
    ]
    for i, entry in enumerate(batch, 1):
        rtype = entry.get("resource_type", "unknown").upper()
        name = entry.get("resource_name", "unknown")
        iid = entry.get("intake_id", "—")
        lines.append(f"| {i} | {rtype} | `{name}` | {iid} |")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _already_has_step_indicator(message: str) -> bool:
    """Check if the message already contains a step/progress indicator."""
    return "**Step " in message or "step " in message.lower()[:30]


def _ensure_yaml_block(message: str, yaml_content: str) -> str:
    """Ensure the YAML content is in a properly formatted code block."""
    if "```yaml" in message:
        return message  # Already formatted
    if yaml_content and yaml_content not in message:
        # YAML is missing from the message — add it
        return f"{message}\n\n```yaml\n{yaml_content}\n```"
    return message
