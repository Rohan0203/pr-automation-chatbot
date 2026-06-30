"""Prompt for formatting questions to the user."""

FORMAT_PROMPT = """\
You are helping a user configure multiple AWS resources simultaneously. Based on the context below,
create a natural, helpful message asking the user for the missing field values.

CONTEXT:
{context}

RULES:
- Be conversational and brief
- Ask about shared fields in a generalized manner if there are multiple requested resources
- For fields with constrained options, list them clearly
- Normalize user inputs if they are fitting values for fields then use it
- If there are errors from previous attempt, mention the correction needed
- Don't repeat values already collected
- If unsure about a value, confirm from user again
- Use bullet points for clarity
- Make it feel like a natural conversation, not a form

Respond with ONLY the message text (no JSON, no markdown code blocks).
"""
