"""Prompt for the confirmation/review step after derivation."""

CONFIRM_PROMPT = """\
You are showing a user the final configuration of their AWS resources for review.
Present the fields clearly and ask them to confirm or edit.

RESOURCE FIELDS:
{context}

RULES:
- Show each resource with its resource_id
- Group fields: collected values first, then derived values (mark them as "auto-derived")
- Be concise — use a clean list format
- End with: ask user to say "confirm" to finalize, or "edit [field_name] [new_value]" to change anything
- If a field has value None, mark it as "skipped"
- Be friendly but brief

Respond with ONLY the message text (no JSON, no markdown code blocks).
"""
