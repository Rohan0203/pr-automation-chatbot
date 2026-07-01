"""LLM service — OpenAI-compatible client with tool-calling support."""
from __future__ import annotations

import os
import json
import httpx
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load .env from backend_v3 root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Configuration from env
_MODEL = os.getenv("TRUEFOUNDRY_OPENAI_MODEL", "openai/gpt-4o-mini")
_API_KEY = os.getenv("TRUEFOUNDRY_OPENAI_API_KEY", "")
_BASE_URL = os.getenv("TRUEFOUNDRY_OPENAI_BASE_URL", "https://tfy-dev.aiops.cloudapps.cargill.com")
_CA_BUNDLE = os.getenv("CUSTOM_CA_BUNDLE_PATH", None)
_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Lazy-init the OpenAI client."""
    global _client
    if _client is None:
        # Strip proxy env vars that interfere with corporate networks
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(key, None)

        http_client = None
        if _CA_BUNDLE:
            http_client = httpx.AsyncClient(verify=_CA_BUNDLE)

        _client = AsyncOpenAI(
            api_key=_API_KEY,
            base_url=_BASE_URL,
            http_client=http_client,
        )
    return _client


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """
    Send a chat completion request with optional tool definitions.

    Args:
        messages: OpenAI-format messages list
        tools: OpenAI-format tool definitions (function calling)

    Returns:
        The assistant message dict (with content and/or tool_calls)
    """
    client = _get_client()

    kwargs = {
        "model": _MODEL,
        "messages": messages,
        "temperature": _TEMPERATURE,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = await client.chat.completions.create(**kwargs)
    choice = response.choices[0]

    result = {
        "role": "assistant",
        "content": choice.message.content,
    }

    if choice.message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]

    return result
