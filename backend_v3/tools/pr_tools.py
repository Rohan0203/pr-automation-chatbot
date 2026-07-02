"""PR creation tool — fork-based workflow for GitHub Enterprise."""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import asyncio
import httpx
import yaml as pyyaml
from dotenv import load_dotenv

from models.state import Session, Resource, ResourceStatus
from tools.session_tools import _get_session
from db.repository import load_github_token, save_resource

load_dotenv()

logger = logging.getLogger(__name__)

# Config from env
GITHUB_ENTERPRISE_URL = (os.getenv("GITHUB_ENTERPRISE_URL") or "").rstrip("/")
GITHUB_API = f"{GITHUB_ENTERPRISE_URL}/api/v3" if GITHUB_ENTERPRISE_URL else "https://api.github.com"
GITHUB_UPSTREAM_OWNER = os.getenv("GITHUB_UPSTREAM_OWNER", "")
GITHUB_UPSTREAM_REPO = os.getenv("GITHUB_UPSTREAM_REPO", "")
GITHUB_UPSTREAM_BRANCH = os.getenv("GITHUB_UPSTREAM_BRANCH", "main")
CA_BUNDLE = os.getenv("CUSTOM_CA_BUNDLE_PATH") or True

# Account → folder mapping
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_account_map: dict | None = None


def _load_account_map() -> dict:
    """Load account_directory_map.yaml."""
    global _account_map
    if _account_map is not None:
        return _account_map
    path = _CONFIG_DIR / "account_directory_map.yaml"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            _account_map = pyyaml.safe_load(f) or {}
    else:
        _account_map = {}
    return _account_map


def _resolve_file_path(resource_type: str, fields: dict) -> str:
    """Resolve the repo file path for a resource (e.g. aws_lakehouse/lakehouse-001/s3/bucket-name.yaml)."""
    mapping = _load_account_map()
    accounts = mapping.get("accounts", {})
    resource_folders = mapping.get("resource_folders", {})
    name_fields = mapping.get("resource_name_fields", {})

    account_id = str(fields.get("aws_account_id", "")).strip("'\"")
    account_info = accounts.get(account_id)

    if not account_info:
        # Fallback
        return f"configs/{resource_type}/{fields.get('intake_id', 'unknown')}.yaml"

    account_folder = account_info["folder"]
    subfolder = resource_folders.get(resource_type, resource_type)
    name_field = name_fields.get(resource_type, "")
    resource_name = fields.get(name_field, "") if name_field else ""

    if not resource_name:
        resource_name = (
            fields.get("bucket_name")
            or fields.get("database_name")
            or fields.get("role_name")
            or fields.get("intake_id", "unknown")
        )

    return f"{account_folder}/{subfolder}/{resource_name}.yaml"


def _create_pr_sync(
    token: str,
    username: str,
    resources: list[dict],
) -> dict:
    """
    Synchronous PR creation flow using GitHub REST API (httpx).
    Steps: fork → sync → branch → commit files → PR.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, verify=CA_BUNDLE, timeout=30) as client:
        # 1. Get or create fork
        fork_full = f"{username}/{GITHUB_UPSTREAM_REPO}"
        resp = client.get(f"{GITHUB_API}/repos/{fork_full}")
        if resp.status_code == 404:
            # Create fork
            resp = client.post(
                f"{GITHUB_API}/repos/{GITHUB_UPSTREAM_OWNER}/{GITHUB_UPSTREAM_REPO}/forks",
                json={},
            )
            if resp.status_code not in (200, 201, 202):
                return {"success": False, "error": f"Fork creation failed: {resp.text}"}
            # Wait for fork to be ready
            for _ in range(10):
                time.sleep(2)
                check = client.get(f"{GITHUB_API}/repos/{fork_full}")
                if check.status_code == 200:
                    break
            else:
                return {"success": False, "error": "Fork creation timed out"}

        # 2. Sync fork with upstream
        client.post(
            f"{GITHUB_API}/repos/{fork_full}/merge-upstream",
            json={"branch": GITHUB_UPSTREAM_BRANCH},
        )

        # 3. Get base branch SHA
        resp = client.get(
            f"{GITHUB_API}/repos/{fork_full}/git/ref/heads/{GITHUB_UPSTREAM_BRANCH}"
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"Cannot get base branch: {resp.text}"}
        base_sha = resp.json()["object"]["sha"]

        # 4. Create feature branch
        timestamp = int(time.time())
        intake_ids = list({r["intake_id"] for r in resources if r.get("intake_id")})
        branch_name = f"config/{'-'.join(intake_ids)}-{timestamp}" if intake_ids else f"config/batch-{timestamp}"

        resp = client.post(
            f"{GITHUB_API}/repos/{fork_full}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        if resp.status_code not in (200, 201):
            # Branch might exist, append extra suffix
            branch_name = f"{branch_name}-{int(time.time()) % 1000}"
            resp = client.post(
                f"{GITHUB_API}/repos/{fork_full}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"Branch creation failed: {resp.text}"}

        # 5. Commit files (one commit with tree API for batch)
        # Get base tree
        resp = client.get(f"{GITHUB_API}/repos/{fork_full}/git/commits/{base_sha}")
        base_tree_sha = resp.json()["tree"]["sha"]

        tree_entries = []
        file_paths = []
        for r in resources:
            path = r["file_path"]
            file_paths.append(path)
            # Create blob
            blob_resp = client.post(
                f"{GITHUB_API}/repos/{fork_full}/git/blobs",
                json={"content": r["yaml_content"], "encoding": "utf-8"},
            )
            if blob_resp.status_code not in (200, 201):
                return {"success": False, "error": f"Blob creation failed for {path}: {blob_resp.text}"}
            tree_entries.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.json()["sha"],
            })

        # Create tree
        tree_resp = client.post(
            f"{GITHUB_API}/repos/{fork_full}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        if tree_resp.status_code not in (200, 201):
            return {"success": False, "error": f"Tree creation failed: {tree_resp.text}"}
        new_tree_sha = tree_resp.json()["sha"]

        # Create commit
        commit_msg = f"feat: add {len(resources)} resource config{'s' if len(resources) != 1 else ''}"
        commit_resp = client.post(
            f"{GITHUB_API}/repos/{fork_full}/git/commits",
            json={
                "message": commit_msg,
                "tree": new_tree_sha,
                "parents": [base_sha],
            },
        )
        if commit_resp.status_code not in (200, 201):
            return {"success": False, "error": f"Commit failed: {commit_resp.text}"}
        new_commit_sha = commit_resp.json()["sha"]

        # Update branch ref
        client.patch(
            f"{GITHUB_API}/repos/{fork_full}/git/refs/heads/{branch_name}",
            json={"sha": new_commit_sha},
        )

        # 6. Create PR
        pr_title = f"[CONFIG] {', '.join(r.get('resource_type', '').upper() for r in resources)} — {', '.join(intake_ids)}"
        pr_body_parts = ["## Infrastructure Configuration\n"]
        for r in resources:
            pr_body_parts.append(f"### {r.get('resource_type', '').upper()} — {r.get('resource_name', '')}")
            pr_body_parts.append(f"- **Intake ID:** {r.get('intake_id', 'N/A')}")
            pr_body_parts.append(f"- **File:** `{r['file_path']}`")
            pr_body_parts.append(f"\n```yaml\n{r['yaml_content']}\n```\n")
        pr_body_parts.append("---\n_This PR was automatically generated by MiNi._")

        pr_resp = client.post(
            f"{GITHUB_API}/repos/{GITHUB_UPSTREAM_OWNER}/{GITHUB_UPSTREAM_REPO}/pulls",
            json={
                "title": pr_title,
                "body": "\n".join(pr_body_parts),
                "head": f"{username}:{branch_name}",
                "base": GITHUB_UPSTREAM_BRANCH,
            },
        )
        if pr_resp.status_code not in (200, 201):
            return {"success": False, "error": f"PR creation failed: {pr_resp.text}"}

        pr_data = pr_resp.json()
        return {
            "success": True,
            "pr_url": pr_data.get("html_url"),
            "pr_number": pr_data.get("number"),
            "branch_name": branch_name,
            "files_committed": file_paths,
            "title": pr_title,
        }


async def create_pr(**kwargs) -> str:
    """
    Create a PR with all DONE resources in the current session.
    Uses the authenticated user's GitHub token from the DB.
    """
    session = _get_session()

    # Find all DONE resources with YAML
    done_resources = [
        r for r in session.resources
        if r.status == ResourceStatus.DONE and r.yaml_output
    ]

    if not done_resources:
        return json.dumps({"error": "No completed resources to submit. Generate YAML first."})

    # Get user's GitHub token
    token = await load_github_token(session.user_id)
    if not token:
        return json.dumps({
            "error": "GitHub token not found. Please re-authenticate via GitHub OAuth.",
            "action_needed": "re_auth",
        })

    # Build resource entries for the PR
    pr_resources = []
    for r in done_resources:
        fields = r.all_fields
        file_path = _resolve_file_path(r.resource_type, fields)
        resource_name = (
            fields.get("bucket_name")
            or fields.get("database_name")
            or fields.get("role_name")
            or r.resource_id
        )
        pr_resources.append({
            "resource_type": r.resource_type,
            "resource_name": resource_name,
            "intake_id": fields.get("intake_id", ""),
            "file_path": file_path,
            "yaml_content": r.yaml_output,
        })

    # Run the sync GitHub operations in a thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            _create_pr_sync,
            token,
            session.user_id,
            pr_resources,
        )

    return json.dumps(result)
