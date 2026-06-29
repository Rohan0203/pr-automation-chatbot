"""
LLM Client - Switchable between Groq, OpenAI, and Azure OpenAI (EPAM DIAL)

All providers use the OpenAI-compatible API format via the `openai` SDK.
"""
import json
import logging
import os
from typing import Optional

import httpx
from openai import AsyncOpenAI, AsyncAzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified async LLM client that supports Groq, OpenAI, TrueFoundry OpenAI, and Azure OpenAI.
    Switch provider via LLM_PROVIDER env variable.
    """

    def __init__(self):
        self.provider = settings.llm_provider.lower()
        self._client = None
        self._model: str = ""
        self._http_client: Optional[httpx.AsyncClient] = None
        self._initialize()

    def _get_http_client(self) -> Optional[httpx.AsyncClient]:
        ca_bundle_path = settings.custom_ca_bundle_path
        if not ca_bundle_path:
            return None

        self._http_client = httpx.AsyncClient(verify=ca_bundle_path)
        logger.info("LLM HTTP client using custom CA bundle: %s", ca_bundle_path)
        return self._http_client

    def _initialize(self):
        """Initialize the appropriate client based on provider setting."""
        http_client = self._get_http_client()

        if self.provider == "groq":
            self._client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                http_client=http_client,
            )
            self._model = settings.groq_model
            logger.info(f"LLM initialized with Groq provider, model: {self._model}")
        elif self.provider == "openai":
            openai_kwargs = {
                "api_key": settings.openai_api_key,
                "http_client": http_client,
            }
            if settings.openai_base_url:
                openai_kwargs["base_url"] = settings.openai_base_url
            self._client = AsyncOpenAI(**openai_kwargs)
            self._model = settings.openai_model
            logger.info(
                f"LLM initialized with OpenAI provider, model: {self._model}"
                + (f", base_url: {settings.openai_base_url}" if settings.openai_base_url else "")
            )
        elif self.provider == "truefoundry_openai":
            # TrueFoundry is an internal Cargill service — corporate proxy
            # cannot resolve it. Clear proxy env vars so httpx connects directly.
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                os.environ.pop(key, None)

            # Recreate http client AFTER clearing proxy vars
            ca_bundle_path = settings.custom_ca_bundle_path
            if ca_bundle_path:
                if self._http_client:
                    # Close the old client that may have captured proxy
                    pass
                self._http_client = httpx.AsyncClient(verify=ca_bundle_path)
                http_client = self._http_client

            self._client = AsyncOpenAI(
                api_key=settings.truefoundry_openai_api_key,
                base_url=settings.truefoundry_openai_base_url,
                http_client=http_client,
            )
            self._model = settings.truefoundry_openai_model
            logger.info(
                "LLM initialized with TrueFoundry OpenAI provider (proxy bypassed), "
                f"model: {self._model}, base_url: {settings.truefoundry_openai_base_url}"
            )
        elif self.provider == "azure":
            self._client = AsyncAzureOpenAI(
                api_key=settings.azure_openai_api_key,
                azure_endpoint=settings.azure_openai_endpoint,
                api_version=settings.azure_openai_api_version,
                http_client=http_client,
            )
            self._model = settings.azure_openai_deployment
            logger.info(f"LLM initialized with Azure/DIAL provider, deployment: {self._model}")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Send a chat completion request and return the response text.

        Args:
            messages: List of {"role": ..., "content": ...} messages
            temperature: Low temperature for deterministic extraction
            max_tokens: Max response tokens
            response_format: Optional, e.g., {"type": "json_object"} for JSON mode

        Returns:
            The assistant's response text
        """
        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            logger.debug(f"LLM response ({self.provider}): {content[:200]}...")
            logger.info(f"LLM response length: {len(content)} chars, finish_reason: {response.choices[0].finish_reason}")
            if response.usage:
                logger.info(f"LLM token usage: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, total={response.usage.total_tokens}")
            return content
        except Exception as e:
            logger.error(f"LLM request failed ({self.provider}): {e}")
            raise

    async def extract_json(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Send a chat request expecting a JSON response.
        Parses and returns the JSON dict.
        """
        response_text = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        logger.info(f"extract_json raw response ({len(response_text)} chars): {response_text[:500]}")

        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {response_text[:300]}")
            # Try to extract JSON from the response
            json_match = _extract_json_from_text(response_text)
            if json_match:
                return json.loads(json_match)
            raise ValueError(f"LLM did not return valid JSON: {response_text[:300]}")


def _extract_json_from_text(text: str) -> Optional[str]:
    """Try to extract a JSON object from text that may contain markdown or extra text."""
    # Look for JSON block in markdown
    import re
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1) if match.lastindex else match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return None


# ── Singleton ─────────────────────────────────────────────────

llm_client = LLMClient()
