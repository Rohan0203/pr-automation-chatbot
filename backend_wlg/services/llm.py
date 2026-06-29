"""LLM factory — single place to create LLM clients for all providers."""
from __future__ import annotations

import os

import httpx
from langchain_openai import ChatOpenAI


def get_llm(**overrides) -> ChatOpenAI:
    """Build a ChatOpenAI instance based on LLM_PROVIDER env var.

    Accepts optional overrides (temperature, model, etc.) that take
    precedence over the env-driven defaults.
    """
    ca_bundle = os.environ.get("CUSTOM_CA_BUNDLE_PATH")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    verify = ca_bundle if ca_bundle else True

    http_async = httpx.AsyncClient(verify=verify)
    http_sync = httpx.Client(verify=verify)

    common = {
        "http_async_client": http_async,
        "http_client": http_sync,
        "http_socket_options": (),
    }

    if provider == "truefoundry_openai":
        defaults = {
            "model": os.environ.get("TRUEFOUNDRY_OPENAI_MODEL", "openai/gpt-4o-mini"),
            "api_key": os.environ["TRUEFOUNDRY_OPENAI_API_KEY"],
            "base_url": os.environ.get(
                "TRUEFOUNDRY_OPENAI_BASE_URL",
                "https://tfy-dev.aiops.cloudapps.cargill.com",
            ),
            "temperature": 0,
        }
    elif provider == "azure":
        defaults = {
            "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            "api_key": os.environ["AZURE_OPENAI_API_KEY"],
            "base_url": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "temperature": 0,
        }
    else:
        defaults = {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": os.environ["OPENAI_API_KEY"],
            "temperature": 0,
        }

    merged = {**defaults, **common, **overrides}
    return ChatOpenAI(**merged)
