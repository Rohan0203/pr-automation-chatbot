"""
PR Chatbot - Configuration Module
Loads settings from .env file with support for switching LLM providers.
"""
import os
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Provider
    llm_provider: str = Field(
        default="groq",
        description=(
            "LLM provider: 'groq', 'openai', 'truefoundry_openai', or 'azure'"
        ),
    )

    # Groq
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    openai_base_url: Optional[str] = Field(default=None, description="Optional custom base URL for OpenAI-compatible endpoints (e.g. TrueFoundry gateway)")

    # TrueFoundry OpenAI Gateway (OpenAI-compatible)
    truefoundry_openai_api_key: str = Field(default="", description="TrueFoundry virtual account token")
    truefoundry_openai_model: str = Field(default="openai/gpt-4o-mini", description="TrueFoundry gateway model ID")
    truefoundry_openai_base_url: str = Field(
        default="https://tfy-dev.aiops.cloudapps.cargill.com",
        description="TrueFoundry OpenAI-compatible base URL",
    )

    # Azure OpenAI / EPAM DIAL Proxy
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI / DIAL API key")
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI endpoint URL")
    azure_openai_deployment: str = Field(default="gpt-4o-mini-2024-07-18", description="Azure OpenAI deployment name")
    azure_openai_api_version: str = Field(default="2024-02-01", description="Azure OpenAI API version")

    # Optional custom CA bundle for TLS interception/corporate proxy networks
    custom_ca_bundle_path: Optional[str] = Field(
        default=None,
        description="Optional path to PEM CA bundle used by outbound HTTPS clients",
    )

    # Database
    database_url: str = Field(default="sqlite:///./pr_chatbot.db", description="Database connection URL")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=True)

    # Logging
    log_level: str = Field(default="INFO")

    # CORS — comma-separated origins or ["*"] for dev
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:8000"],
        description="Allowed CORS origins. Set to ['*'] for development.",
    )

    # GitHub OAuth
    github_client_id: Optional[str] = Field(default=None, description="GitHub OAuth App Client ID")
    github_client_secret: Optional[str] = Field(default=None, description="GitHub OAuth App Client Secret")
    frontend_url: str = Field(default="http://localhost:5173", description="Frontend URL for OAuth redirects")

    # Enterprise GitHub (leave blank to use github.com)
    github_enterprise_url: str = Field(
        default="https://git.cglcloud.com",
        description="Enterprise GitHub base URL, e.g. https://git.cglcloud.com",
    )

    # Upstream repo (target for PRs — fork-based workflow)
    github_upstream_owner: str = Field(default="abinashlingank", description="Upstream repo owner")
    github_upstream_repo: str = Field(default="object-provisioning", description="Upstream repo name")
    github_upstream_branch: str = Field(default="main", description="Upstream default branch")

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
