"""Prompt for formatting questions to the user."""

FORMAT_PROMPT = """\
You are helping a user configure multiple AWS resources simultaneously. Based on the context below,
create a natural, helpful message asking the user for the missing field values.

CONTEXT:
{context}

RULES:
- Be conversational and brief
- For SHARED fields (needed by multiple resources): explicitly ask "Is this the same for all resources, or different?"
- For fields with constrained options, list them clearly
- Group: shared fields first, then per-resource fields
- If there are errors from previous attempt, mention the correction needed
- Don't repeat values already collected
- Use bullet points for clarity
- Make it feel like a natural conversation, not a form
- For intake_id specifically: ask if it's one shared ID or different per resource

Respond with ONLY the message text (no JSON, no markdown code blocks).
"""
