"""
GitHub OAuth — handles authorization flow, token exchange, and user info.
State parameter is purely for CSRF protection (no session_id encoding).
"""
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Temporary in-memory store for OAuth state tokens (CSRF protection)
OAUTH_STATES: dict[str, dict] = {}

# Compute base URLs for enterprise GitHub (or fall back to github.com)
_ENTERPRISE = (settings.github_enterprise_url or "").rstrip("/")
GITHUB_WEB = _ENTERPRISE if _ENTERPRISE else "https://github.com"
GITHUB_API = f"{_ENTERPRISE}/api/v3" if _ENTERPRISE else "https://api.github.com"


def get_github_auth_url() -> str:
    """Generate a GitHub OAuth authorization URL with a random CSRF state token."""
    state = secrets.token_urlsafe(32)
    OAUTH_STATES[state] = {"created_at": datetime.now(timezone.utc)}

    params = urlencode({
        "client_id": settings.github_client_id,
        "scope": "repo user:email",
        "state": state,
    })

    return f"{GITHUB_WEB}/login/oauth/authorize?{params}"


async def exchange_code_for_token(code: str, state: Optional[str] = None) -> str:
    """
    Exchange an OAuth authorization code for an access token.
    """
    if state is not None:
        if state not in OAUTH_STATES:
            raise ValueError("Invalid OAuth state")
        del OAUTH_STATES[state]

    try:
        async with httpx.AsyncClient(verify=settings.custom_ca_bundle_path or True, timeout=30) as client:
            response = await client.post(
                f"{GITHUB_WEB}/login/oauth/access_token",
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

        data = response.json()
        if "error" in data:
            raise ValueError(data.get("error_description", data["error"]))

        token = data.get("access_token")
        if not token:
            raise ValueError("GitHub OAuth token missing in response")
        return token
    except httpx.HTTPStatusError as e:
        logger.error("GitHub token exchange failed with status %s: %s", e.response.status_code, e.response.text)
        raise ValueError("GitHub token exchange failed")
    except httpx.HTTPError as e:
        logger.error("GitHub token exchange network error: %s", e)
        raise ValueError("GitHub token exchange network error")
    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected GitHub token exchange error: %s", e)
        raise ValueError("Unexpected GitHub token exchange error")


async def get_github_username(token: str) -> str:
    """Fetch the GitHub username for the given access token."""
    try:
        async with httpx.AsyncClient(verify=settings.custom_ca_bundle_path or True, timeout=30) as client:
            response = await client.get(
                f"{GITHUB_API}/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()

        data = response.json()
        username = data.get("login")
        if not username:
            raise ValueError("GitHub username missing in response")
        return username
    except httpx.HTTPStatusError as e:
        logger.error("GitHub user lookup failed with status %s: %s", e.response.status_code, e.response.text)
        raise ValueError("Failed to fetch GitHub username")
    except httpx.HTTPError as e:
        logger.error("GitHub user lookup network error: %s", e)
        raise ValueError("GitHub user lookup network error")
    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected GitHub user lookup error: %s", e)
        raise ValueError("Unexpected GitHub user lookup error")
