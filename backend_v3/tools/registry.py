"""
Tool registry — maps tool names to implementations and OpenAI function schemas.
Central place to register all tools the agent can use.
"""
from __future__ import annotations

from typing import Callable, Any

from tools.session_tools import get_session_state, create_resources, drop_resource
from tools.field_tools import set_fields, get_resource_info
from tools.derive_tools import derive_fields
from tools.generate_tools import generate_yaml
from tools.preference_tools import save_preference

# ─── Tool function map ────────────────────────────────────────────────────────

TOOL_FUNCTIONS: dict[str, Callable] = {
    "get_session_state": get_session_state,
    "create_resources": create_resources,
    "drop_resource": drop_resource,
    "set_fields": set_fields,
    "get_resource_info": get_resource_info,
    "derive_fields": derive_fields,
    "generate_yaml": generate_yaml,
    "save_preference": save_preference,
}

# ─── OpenAI tool schemas ─────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_session_state",
            "description": "Get the current session state including all resources and their statuses/fields. Call this at the start of every turn.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_resources",
            "description": "Create one or more new resources to begin collecting fields. Call when user requests new infrastructure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "resource_type": {
                                    "type": "string",
                                    "description": "Type of resource (e.g. 's3', 'glue_db')",
                                },
                            },
                            "required": ["resource_type"],
                        },
                        "description": "List of resources to create",
                    },
                },
                "required": ["resources"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drop_resource",
            "description": "Drop/abandon a resource. Use when user wants to cancel a specific resource.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "ID of the resource to drop (e.g. 's3_0')",
                    },
                },
                "required": ["resource_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_fields",
            "description": "Set collected field values on a resource after extracting from user message. Handles normalization internally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "ID of the resource (e.g. 's3_0')",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Key-value pairs of field names and their values",
                    },
                },
                "required": ["resource_id", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_resource_info",
            "description": "Get the field specification and context for a resource type. Returns what fields to collect, what to derive, and behavioral instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "description": "Type of resource (e.g. 's3')",
                    },
                },
                "required": ["resource_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "derive_fields",
            "description": "Derive computable fields (bucket_name, account_id, etc.) from collected values. Call after all user-provided fields are set.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "ID of the resource to derive fields for",
                    },
                },
                "required": ["resource_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_yaml",
            "description": "Generate the final YAML output for a confirmed resource. Only call after user explicitly confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "ID of the resource to generate YAML for",
                    },
                },
                "required": ["resource_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_preference",
            "description": "Save a user preference for future sessions (e.g. response style, fields per turn). Call when user expresses a lasting preference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Preference key (e.g. 'fields_per_turn', 'tone', 'verbosity')",
                    },
                    "value": {
                        "type": "string",
                        "description": "Preference value (e.g. '2', 'concise', 'detailed')",
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
]
