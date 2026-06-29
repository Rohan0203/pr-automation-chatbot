"""
SCM Adapter — Fork-based PR workflow for infrastructure config PRs.

Flow:
  1. Check if user has a fork of the upstream repo
  2. If no fork exists → create it (and wait for it to be ready)
  3. Sync the fork's default branch with upstream (to avoid conflicts)
  4. Create a feature branch in the user's fork
  5. Commit the YAML file to that branch
  6. Open a cross-fork PR: user_fork:feature_branch → upstream:main

Target upstream repo is read from config (settings.github_upstream_*).
"""
import logging
import time
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import httpx
from github import Github, GithubException, InputGitTreeElement
from github.Repository import Repository

from app.config import settings

logger = logging.getLogger(__name__)


def _get_github_api_base() -> str:
    """Return GitHub API base URL (enterprise-aware)."""
    enterprise = (settings.github_enterprise_url or "").strip().rstrip("/")
    if enterprise:
        return f"{enterprise}/api/v3"
    return "https://api.github.com"


# ═══════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════

class SCMError(Exception):
    """
    Raised by SCMAdapter when a GitHub SCM operation fails.

    Attributes:
        message: Human-readable error description
        operation: Which operation failed (e.g., "fork_creation", "branch_creation")
        recoverable: Whether the user can retry (True) or it's a permanent failure (False)
    """

    def __init__(self, message: str, operation: str, recoverable: bool = True):
        self.message = message
        self.operation = operation
        self.recoverable = recoverable
        super().__init__(message)


# ═══════════════════════════════════════════════════════════════
# SCM ADAPTER (Synchronous — runs in thread pool)
# ═══════════════════════════════════════════════════════════════

class SCMAdapter:
    """
    Handles all GitHub SCM operations for the fork-based PR workflow.
    All methods are synchronous (PyGithub is sync).
    Call from async code using asyncio.get_event_loop().run_in_executor().
    """

    def __init__(self, github_token: str):
        """Initialize with an authenticated user's GitHub token."""
        self.token = github_token
        self.api_base = _get_github_api_base()
        self.github = Github(base_url=self.api_base, login_or_token=github_token)

    def check_fork_exists(self, upstream_owner: str, upstream_repo: str) -> dict:
        """
        Check if the authenticated user already has a fork of upstream_owner/upstream_repo.

        Returns:
            {"exists": True, "fork_full_name": "user/repo"} or {"exists": False, "username": "..."}
        """
        try:
            user = self.github.get_user()
            fork_full_name = f"{user.login}/{upstream_repo}"
            try:
                fork = self.github.get_repo(fork_full_name)
                if fork.fork:
                    return {"exists": True, "fork_full_name": fork_full_name, "username": user.login}
            except GithubException:
                pass
            return {"exists": False, "username": user.login}
        except GithubException as e:
            raise SCMError(
                f"Cannot check fork status: {e.data.get('message', str(e))}",
                operation="check_fork",
                recoverable=True,
            )

    def get_or_create_fork(self, upstream_owner: str, upstream_repo: str) -> Repository:
        """
        Check if the authenticated user already has a fork of upstream_owner/upstream_repo.
        If fork exists, return it. If not, create it and poll until ready.

        Returns:
            The user's fork Repository object.

        Raises:
            SCMError: if fork creation fails or times out.
        """
        try:
            upstream = self.github.get_repo(f"{upstream_owner}/{upstream_repo}")
        except GithubException as e:
            raise SCMError(
                f"Cannot access upstream repo {upstream_owner}/{upstream_repo}: {e.data.get('message', str(e))}",
                operation="access_upstream",
                recoverable=False,
            )

        user = self.github.get_user()
        fork_full_name = f"{user.login}/{upstream_repo}"

        # Check if fork already exists
        try:
            fork = self.github.get_repo(fork_full_name)
            if fork.fork:
                logger.info(f"Fork already exists: {fork_full_name}")
                return fork
        except GithubException:
            pass  # Fork doesn't exist yet

        # Create fork
        logger.info(f"Creating fork of {upstream_owner}/{upstream_repo}...")
        try:
            fork = user.create_fork(upstream)
        except GithubException as e:
            raise SCMError(
                f"Failed to create fork: {e.data.get('message', str(e))}",
                operation="fork_creation",
                recoverable=True,
            )

        # Poll until fork is ready (max 30 seconds, check every 2s)
        for _ in range(15):
            time.sleep(2)
            try:
                fork = self.github.get_repo(fork_full_name)
                if fork.size > 0 or fork.get_branches().totalCount > 0:
                    logger.info(f"Fork ready: {fork_full_name}")
                    return fork
            except GithubException:
                continue

        # Return anyway — fork might be ready but empty
        try:
            return self.github.get_repo(fork_full_name)
        except GithubException:
            raise SCMError(
                "Fork creation timed out. Please try again in a few seconds.",
                operation="fork_creation",
                recoverable=True,
            )

    def sync_fork_with_upstream(self, fork: Repository, upstream_branch: str = "main"):
        """
        Sync the fork's default branch with the upstream repo.

        Uses httpx to call GitHub's merge-upstream REST API directly
        (PyGithub doesn't support this endpoint natively).

        Safe to call even if fork is already up-to-date.
        """
        try:
            response = httpx.post(
                f"{self.api_base}/repos/{fork.full_name}/merge-upstream",
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"branch": upstream_branch},
                timeout=30,
                verify=settings.custom_ca_bundle_path or True,
            )

            if response.status_code in (200, 409):
                # 200 = merged, 409 = already up-to-date
                logger.info(f"Fork sync result for {fork.full_name}: {response.status_code}")
                return
            elif response.status_code == 422:
                # Upstream branch might not exist or fork has no upstream
                logger.warning(f"Fork sync skipped (422): {response.json()}")
                return

            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            logger.warning(f"Fork sync failed (non-critical): {e}")
            # Non-fatal — continue with PR creation
        except Exception as e:
            logger.warning(f"Fork sync error (non-critical): {e}")

    def create_feature_branch(
        self,
        fork: Repository,
        branch_name: str,
        base_branch: str = "main",
    ) -> str:
        """
        Create a new branch in the fork from base_branch.

        If branch_name already exists, appends a timestamp suffix.

        Returns:
            The final branch name used.

        Raises:
            SCMError: if branch creation fails.
        """
        try:
            base_ref = fork.get_branch(base_branch)
            base_sha = base_ref.commit.sha
        except GithubException as e:
            raise SCMError(
                f"Base branch '{base_branch}' not found in fork: {e.data.get('message', str(e))}",
                operation="branch_creation",
                recoverable=False,
            )

        # Check if branch already exists, append timestamp if so
        final_name = branch_name
        try:
            fork.get_branch(final_name)
            # Branch exists — append timestamp
            final_name = f"{branch_name}-{int(time.time())}"
        except GithubException:
            pass  # Branch doesn't exist — use original name

        try:
            fork.create_git_ref(ref=f"refs/heads/{final_name}", sha=base_sha)
            logger.info(f"Created branch: {final_name}")
            return final_name
        except GithubException as e:
            raise SCMError(
                f"Failed to create branch '{final_name}': {e.data.get('message', str(e))}",
                operation="branch_creation",
                recoverable=True,
            )

    def commit_yaml_file(
        self,
        fork: Repository,
        branch: str,
        resource_type: str,
        intake_id: str,
        resource_name: str,
        yaml_content: str,
        resolved_path: str = None,
    ) -> str:
        """
        Commit a YAML file to the specified branch in the fork.

        File path: Uses resolved_path if provided, else falls back to
        configs/{resource_type}/{intake_id}-{resource_name}.yaml

        Returns:
            The full file path that was committed.

        Raises:
            SCMError: if commit fails.
        """
        file_path = resolved_path or f"configs/{resource_type}/{intake_id}-{resource_name}.yaml"
        commit_message = f"feat: add {resource_type} config for {intake_id}"

        try:
            # Check if file already exists (update vs create)
            try:
                existing = fork.get_contents(file_path, ref=branch)
                fork.update_file(
                    path=file_path,
                    message=commit_message,
                    content=yaml_content,
                    sha=existing.sha,
                    branch=branch,
                )
                logger.info(f"Updated file: {file_path} on branch {branch}")
            except GithubException:
                # File doesn't exist — create it
                fork.create_file(
                    path=file_path,
                    message=commit_message,
                    content=yaml_content,
                    branch=branch,
                )
                logger.info(f"Created file: {file_path} on branch {branch}")

            return file_path

        except GithubException as e:
            raise SCMError(
                f"Failed to commit YAML file: {e.data.get('message', str(e))}",
                operation="commit",
                recoverable=True,
            )

    def commit_batch_files(
        self,
        fork: Repository,
        branch: str,
        resources: list[dict],
    ) -> list[str]:
        """
        Commit multiple YAML files to the specified branch in a single atomic commit
        using the Git Tree API.

        Each resource dict: {resource_type, intake_id, resource_name, yaml_content}
        Optionally includes 'resolved_path' for correct folder placement.

        Returns:
            List of committed file paths.

        Raises:
            SCMError: if commit fails.
        """
        try:
            # Get the base commit and tree
            base_ref = fork.get_branch(branch)
            base_sha = base_ref.commit.sha
            base_tree_sha = base_ref.commit.commit.tree.sha

            # Build tree entries — one blob per file
            tree_entries = []
            file_paths = []
            for r in resources:
                path = r.get("resolved_path") or f"configs/{r['resource_type']}/{r['intake_id']}-{r['resource_name']}.yaml"
                file_paths.append(path)
                blob = fork.create_git_blob(r["yaml_content"], "utf-8")
                tree_entries.append(InputGitTreeElement(
                    path=path,
                    mode="100644",
                    type="blob",
                    sha=blob.sha,
                ))

            # Create a new tree with all files
            base_tree = fork.get_git_tree(base_tree_sha)
            new_tree = fork.create_git_tree(tree_entries, base_tree=base_tree)

            # Create a single commit
            commit_message = f"feat: add {len(resources)} resource config{'s' if len(resources) != 1 else ''}"
            parent = fork.get_git_commit(base_sha)
            new_commit = fork.create_git_commit(
                message=commit_message,
                tree=new_tree,
                parents=[parent],
            )

            # Update branch ref to point to new commit
            ref = fork.get_git_ref(f"heads/{branch}")
            ref.edit(sha=new_commit.sha)

            logger.info(f"Batch committed {len(file_paths)} files to branch {branch}")
            return file_paths

        except GithubException as e:
            raise SCMError(
                f"Failed to commit batch files: {e.data.get('message', str(e))}",
                operation="batch_commit",
                recoverable=True,
            )

    def create_pull_request(
        self,
        fork_owner: str,
        fork_repo_name: str,
        feature_branch: str,
        upstream_owner: str,
        upstream_repo: str,
        upstream_branch: str,
        title: str,
        body: str,
    ) -> str:
        """
        Open a cross-fork pull request.
        head = fork_owner:feature_branch
        base = upstream_branch (on the upstream repo)

        The PR is created on the UPSTREAM repo.

        Returns:
            PR HTML URL.

        Raises:
            SCMError: if PR creation fails.
        """
        try:
            upstream = self.github.get_repo(f"{upstream_owner}/{upstream_repo}")
            pr = upstream.create_pull(
                title=title,
                body=body,
                head=f"{fork_owner}:{feature_branch}",
                base=upstream_branch,
            )
            logger.info(f"PR created: {pr.html_url}")
            return pr.html_url

        except GithubException as e:
            error_msg = e.data.get("message", str(e)) if hasattr(e, "data") else str(e)
            # Check for token revocation
            if e.status == 401:
                raise SCMError(
                    "GitHub token expired or revoked. Please reconnect your GitHub account.",
                    operation="auth",
                    recoverable=True,
                )
            raise SCMError(
                f"Failed to create pull request: {error_msg}",
                operation="pr_creation",
                recoverable=True,
            )

    def list_upstream_branches(self, upstream_owner: str, upstream_repo: str) -> list[str]:
        """
        List all branches in the upstream repo.

        Returns:
            List of branch names, e.g. ["main", "dev", "test"]
        """
        try:
            repo = self.github.get_repo(f"{upstream_owner}/{upstream_repo}")
            return [b.name for b in repo.get_branches()]
        except GithubException as e:
            raise SCMError(
                f"Cannot list branches: {e.data.get('message', str(e))}",
                operation="list_branches",
                recoverable=True,
            )


# ═══════════════════════════════════════════════════════════════
# TOP-LEVEL ASYNC FUNCTIONS (called from routes/agent)
# ═══════════════════════════════════════════════════════════════

async def check_fork_status(github_token: str) -> dict:
    """
    Check if the authenticated user already has a fork of the upstream repo.
    Runs in a thread pool since PyGithub is sync.

    Returns:
        {"exists": True, "fork_full_name": "user/repo", "username": "..."} or
        {"exists": False, "username": "...", "error": None}
    """
    def _run():
        adapter = SCMAdapter(github_token)
        return adapter.check_fork_exists(
            settings.github_upstream_owner,
            settings.github_upstream_repo,
        )

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run)
    except SCMError as e:
        return {"exists": False, "username": "unknown", "error": e.message}
    except Exception as e:
        return {"exists": False, "username": "unknown", "error": str(e)}


async def get_upstream_branches(github_token: str) -> list[str]:
    """Fetch branch names from the upstream repo. Runs in thread pool."""
    def _run():
        adapter = SCMAdapter(github_token)
        return adapter.list_upstream_branches(
            settings.github_upstream_owner,
            settings.github_upstream_repo,
        )

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run)
    except SCMError:
        return [settings.github_upstream_branch]
    except Exception:
        return [settings.github_upstream_branch]


async def create_pr_for_resource(
    github_token: str,
    github_username: str,
    resource_type: str,
    intake_id: str,
    resource_name: str,
    yaml_content: str,
    branch_name: str = None,
    pr_title: str = None,
    pr_body: str = None,
    collected_fields: dict = None,
    upstream_owner: str = None,
    upstream_repo: str = None,
    upstream_branch: str = None,
) -> dict:
    """
    Full end-to-end PR creation flow.
    Runs SCMAdapter in a thread pool executor (since PyGithub is sync).

    Args:
        branch_name: Optional custom branch name. If None, auto-generates one.

    Returns on success:
        { "success": True, "pr_url": "...", "branch_name": "...", "file_path": "..." }

    Returns on failure:
        { "success": False, "error": "Human-readable message", "recoverable": True/False }
    """
    upstream_owner = upstream_owner or settings.github_upstream_owner
    upstream_repo = upstream_repo or settings.github_upstream_repo
    upstream_branch = upstream_branch or settings.github_upstream_branch

    if not branch_name:
        timestamp = int(time.time())
        branch_name = f"config/{resource_type}-{intake_id}-{timestamp}"

    def _run():
        adapter = SCMAdapter(github_token)

        # Resolve file path
        resolved = None
        if collected_fields:
            try:
                from app.services.path_resolver import resolve_file_path
                resolved = resolve_file_path(resource_type, collected_fields)
            except Exception:
                pass

        # 1. Get or create fork
        fork = adapter.get_or_create_fork(upstream_owner, upstream_repo)

        # 2. Sync fork with upstream
        adapter.sync_fork_with_upstream(fork, upstream_branch)

        # 3. Create feature branch
        final_branch = adapter.create_feature_branch(fork, branch_name, upstream_branch)

        # 4. Commit YAML file
        file_path = adapter.commit_yaml_file(
            fork, final_branch, resource_type, intake_id, resource_name, yaml_content,
            resolved_path=resolved,
        )

        # 5. Create cross-fork PR
        title = pr_title or f"[CONFIG] {resource_type.upper()} - {intake_id} - {resource_name}"
        body = pr_body or (
            f"## Infrastructure Configuration\n\n"
            f"**Resource Type:** {resource_type}\n"
            f"**Intake ID:** {intake_id}\n"
            f"**Resource Name:** {resource_name}\n\n"
            f"```yaml\n{yaml_content}\n```\n\n"
            f"---\n"
            f"_This PR was automatically generated by PR Chatbot._"
        )

        pr_url = adapter.create_pull_request(
            fork_owner=fork.owner.login,
            fork_repo_name=fork.name,
            feature_branch=final_branch,
            upstream_owner=upstream_owner,
            upstream_repo=upstream_repo,
            upstream_branch=upstream_branch,
            title=title,
            body=body,
        )

        return {
            "success": True,
            "pr_url": pr_url,
            "branch_name": final_branch,
            "file_path": file_path,
            "title": title,
        }

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _run)
        return result

    except SCMError as e:
        logger.error(f"SCM error ({e.operation}): {e.message}")
        return {
            "success": False,
            "error": e.message,
            "recoverable": e.recoverable,
        }
    except Exception as e:
        logger.error(f"Unexpected SCM error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"An unexpected error occurred: {str(e)}",
            "recoverable": True,
        }


# ═══════════════════════════════════════════════════════════════
# PR STATUS TRACKING
# ═══════════════════════════════════════════════════════════════

async def get_pr_live_status(github_token: str, pr_url: str) -> dict:
    """
    Fetch current PR state from GitHub API.

    Returns:
        {"state": "open|closed|merged", "title": ..., "number": ..., ...}
    """
    import re as _re

    match = _re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
    if not match:
        return {"state": "unknown", "error": "Could not parse PR URL"}

    owner, repo, number = match.group(1), match.group(2), int(match.group(3))

    def _run():
        adapter = SCMAdapter(github_token)
        gh_repo = adapter.github.get_repo(f"{owner}/{repo}")
        pr = gh_repo.get_pull(number)
        return {
            "state": "merged" if pr.merged else pr.state,
            "title": pr.title,
            "number": pr.number,
            "mergeable": pr.mergeable,
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
            "html_url": pr.html_url,
        }

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run)
    except Exception as e:
        return {"state": "unknown", "error": str(e)}

async def create_pr_for_batch(
    github_token: str,
    github_username: str,
    resources: list[dict],
    branch_name: str,
    pr_title: str = None,
    pr_body: str = None,
    upstream_owner: str = None,
    upstream_repo: str = None,
    upstream_branch: str = None,
) -> dict:
    """
    Full end-to-end PR creation flow for multiple resources in a single commit.
    Uses the Git Tree API for atomic multi-file commits.

    Args:
        resources: List of dicts with {resource_type, intake_id, resource_name, yaml_content}
        branch_name: Custom branch name for the batch PR.

    Returns on success:
        { "success": True, "pr_url": "...", "branch_name": "...", "file_paths": [...] }

    Returns on failure:
        { "success": False, "error": "Human-readable message", "recoverable": True/False }
    """
    upstream_owner = upstream_owner or settings.github_upstream_owner
    upstream_repo = upstream_repo or settings.github_upstream_repo
    upstream_branch = upstream_branch or settings.github_upstream_branch

    if not branch_name:
        timestamp = int(time.time())
        first_intake = resources[0]["intake_id"] if resources else "batch"
        branch_name = f"config/batch-{first_intake}-{timestamp}"

    title = pr_title or f"[CONFIG] Batch — {len(resources)} resources"
    body = pr_body or f"Batch PR with {len(resources)} resource configurations."

    def _run():
        adapter = SCMAdapter(github_token)

        # 1. Get or create fork
        fork = adapter.get_or_create_fork(upstream_owner, upstream_repo)

        # 2. Sync fork with upstream
        adapter.sync_fork_with_upstream(fork, upstream_branch)

        # 3. Create feature branch
        final_branch = adapter.create_feature_branch(fork, branch_name, upstream_branch)

        # 4. Commit all files in one atomic commit
        file_paths = adapter.commit_batch_files(fork, final_branch, resources)

        # 5. Create cross-fork PR
        pr_url = adapter.create_pull_request(
            fork_owner=fork.owner.login,
            fork_repo_name=fork.name,
            feature_branch=final_branch,
            upstream_owner=upstream_owner,
            upstream_repo=upstream_repo,
            upstream_branch=upstream_branch,
            title=title,
            body=body,
        )

        return {
            "success": True,
            "pr_url": pr_url,
            "branch_name": final_branch,
            "file_paths": file_paths,
            "title": title,
        }

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _run)
        return result

    except SCMError as e:
        logger.error(f"SCM error ({e.operation}): {e.message}")
        return {
            "success": False,
            "error": e.message,
            "recoverable": e.recoverable,
        }
    except Exception as e:
        logger.error(f"Unexpected SCM error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"An unexpected error occurred: {str(e)}",
            "recoverable": True,
        }