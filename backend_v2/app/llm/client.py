"""
LLM client — thin wrapper around TrueFoundry OpenAI-compatible API.
Configure via .env file.
"""
import os
import json
import httpx
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

# TrueFoundry config
TFY_API_KEY = os.getenv("TRUEFOUNDRY_OPENAI_API_KEY", "")
TFY_MODEL = os.getenv("TRUEFOUNDRY_OPENAI_MODEL", "openai/gpt-4o-mini")
TFY_BASE_URL = os.getenv("TRUEFOUNDRY_OPENAI_BASE_URL", "https://tfy-dev.aiops.cloudapps.cargill.com")
CA_BUNDLE_PATH = os.getenv("CUSTOM_CA_BUNDLE_PATH", None)

_client: AsyncOpenAI | None = None


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
