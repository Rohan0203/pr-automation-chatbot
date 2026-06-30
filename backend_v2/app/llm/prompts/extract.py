"""Prompt for field extraction during collection."""

EXTRACT_PROMPT = """\
You are extracting field values from a user's message for AWS resource configuration.
The user may be configuring MULTIPLE resources at once. Some fields are shared across resources.

CONTEXT:
{context}

PREVIOUS BOT MESSAGE:
{previous_bot_message}

USER MESSAGE:
{user_message}

Extract any field values the user provided. For each field, validate against the rules/options given.

Respond in JSON:
{{
  "extracted": {{
    "field_name": {{
      "value": "extracted_value",
      "valid": true,
      "applies_to": "all"
    }},
    "another_field": {{
      "value": "bad_value",
      "valid": false,
      "issue": "brief reason why it's invalid",
      "applies_to": "s3"
    }}
  }},
  "intent": "answer"
}}

For "applies_to":
- Use "all" if the user says it's the same for all resources
- Use the specific resource type (e.g. "s3", "glue_db") if it only applies to one
- If the user gives different values for the same field per resource, create separate entries like "intake_id_s3" and "intake_id_glue_db"

Intent options:
- "answer": user is providing field values
- "question": user is asking a question (extract nothing)
- "edit": user wants to change a previously given value
- "drop": user wants to abandon a resource
- "skip": user wants to skip the current field(s)

Only extract fields listed in the context. Do not invent fields.
If the user message contains no field values, return empty "extracted" with appropriate intent.
"""
