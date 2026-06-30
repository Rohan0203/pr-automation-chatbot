"""
LLM client with provider switch.
Supports:
- TrueFoundry OpenAI-compatible endpoint
- AWS Bedrock Converse API
"""
import os
import json
import httpx
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

# Provider config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()

# TrueFoundry config
TFY_API_KEY = os.getenv("TRUEFOUNDRY_OPENAI_API_KEY", "")
# TFY_MODEL = os.getenv("TRUEFOUNDRY_OPENAI_MODEL", "openai/gpt-4o-mini")
TFY_MODEL = os.getenv("TRUEFOUNDRY_OPENAI_MODEL", "openai/gpt-4o-mini")
TFY_BASE_URL = os.getenv("TRUEFOUNDRY_OPENAI_BASE_URL", "https://tfy-dev.aiops.cloudapps.cargill.com")
CA_BUNDLE_PATH = os.getenv("CUSTOM_CA_BUNDLE_PATH", None)

# Bedrock config
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))

_client: AsyncOpenAI | None = None


def _resolve_provider() -> str:
    if LLM_PROVIDER in {"truefoundry", "bedrock"}:
        return LLM_PROVIDER
    if TFY_API_KEY:
        return "truefoundry"
    return "bedrock"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # TrueFoundry is internal — clear proxy env vars so httpx connects directly
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(key, None)

        http_client = None
        if CA_BUNDLE_PATH:
            http_client = httpx.AsyncClient(verify=CA_BUNDLE_PATH)

        _client = AsyncOpenAI(
            api_key=TFY_API_KEY,
            base_url=TFY_BASE_URL,
            http_client=http_client,
        )
    return _client


async def chat(system_prompt: str, user_message: str) -> str:
    """Simple chat completion — returns text response."""
    provider = _resolve_provider()
    if provider == "bedrock":
        return await _chat_bedrock(system_prompt, user_message)

    client = _get_client()
    response = await client.chat.completions.create(
        model=TFY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content


async def chat_json(system_prompt: str, user_message: str) -> dict:
    """Chat completion expecting JSON response. Parses and returns dict."""
    provider = _resolve_provider()
    if provider == "bedrock":
        # Converse API does not support JSON mode directly, so enforce it in prompt.
        text = await _chat_bedrock(
            system_prompt + "\n\nReturn strictly valid JSON. No markdown, no extra text.",
            user_message,
        )
        return _safe_json_loads(text)

    client = _get_client()
    response = await client.chat.completions.create(
        model=TFY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content
    return json.loads(text)


def _safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _extract_bedrock_text(response: dict) -> str:
    output = response.get("output", {})
    message = output.get("message", {})
    contents = message.get("content", [])
    parts: list[str] = []
    for item in contents:
        if isinstance(item, dict) and "text" in item:
            parts.append(item["text"])
    return "".join(parts).strip()


def _chat_bedrock_sync(system_prompt: str, user_message: str) -> str:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for Bedrock. Install with: pip install boto3"
        ) from exc

    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[
            {
                "role": "user",
                "content": [{"text": user_message}],
            }
        ],
        inferenceConfig={"temperature": 0.1},
    )
    return _extract_bedrock_text(response)


async def _chat_bedrock(system_prompt: str, user_message: str) -> str:
    return await asyncio.to_thread(_chat_bedrock_sync, system_prompt, user_message)
