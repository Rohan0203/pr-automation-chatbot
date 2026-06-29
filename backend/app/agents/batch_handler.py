"""
Batch Handler — manages batch-level commands: show, remove, edit, create PR.

Extracted from the monolithic GeneratorAgent.
"""
import re
import logging
from typing import Optional
from collections import Counter

from app.agents.session_state import AgentState, SessionState
from app.agents.response_decorator import build_response
from app.agents.pr_handler import present_pr_setup, resume_pr_from_pause
from app.config import settings

logger = logging.getLogger(__name__)


async def after_review_passed(
    session: SessionState,
    agent: AgentState,
    prefix_message: str = "",
) -> dict:
    """Called when review passes. Adds resource to batch and decides next step."""
    entry = session.add_to_batch(agent)
    batch_count = len(session.batch)
    rtype = entry["resource_type"].upper()
    name = entry["resource_name"]

    logger.info("[BATCH] after_review_passed: resource=%s, name=%s, batch_count=%d",
                rtype, name, batch_count)

    # Clear current agent — resource is now in batch
    session.current_agent = None

    # Clear structured flow if present
    if session.structured_flow:
        session.structured_flow = None

    # Check if there's a paused PR flow to resume
    resume = resume_pr_from_pause(session)
    if resume:
        resume["message"] = (
            f"{prefix_message}"
            f"✅ **{rtype}** `{name}` added to batch ({batch_count} resources).\n\n"
            + resume["message"]
        )
        return resume

    if batch_count == 1:
        msg = (
            f"{prefix_message}"
            f"**{rtype}** `{name}` is ready!\n\n"
            f"Would you like to:\n"
            f"1. **Create PR** — submit this resource now\n"
            f"2. **Add another resource** — build more configs first\n"
        )
    else:
        msg = (
            f"{prefix_message}"
            f"**{rtype}** `{name}` added to batch ({batch_count} resources).\n\n"
            f"Add another resource, **\"show batch\"**, or **\"create PR\"** to submit all."
        )

    return build_response(
        msg,
        resource_type=entry["resource_type"],
        resource_status="batch_prompt",
    )


async def handle_batch_prompt(
    session: SessionState,
    user_message: str,
    handle_idle_fn,
) -> dict:
    """Route batch-level commands: create PR, show batch, edit N, remove N, or new resource."""
    msg_lower = user_message.strip().lower()

    # Create PR
    if any(t in msg_lower for t in ["create pr", "submit", "make pr", "proceed"]):
        if not session.batch:
            return build_response("No resources in your batch. Create a resource first.")
        return await handle_batch_pr_setup(session)

    # Show batch
    if any(t in msg_lower for t in ["show batch", "batch summary", "list batch"]):
        summary = session.get_batch_summary()
        return build_response(
            f"{summary}\n\n"
            f"Say **\"create PR\"**, **\"edit N\"**, **\"remove N\"**, or add another resource.",
            resource_status="batch_prompt",
        )

    # Remove N
    remove_match = re.match(r"remove\s+(\d+)", msg_lower)
    if remove_match:
        idx = int(remove_match.group(1))
        removed = session.remove_from_batch(idx)
        if removed:
            remaining = len(session.batch)
            msg = (
                f"Removed {removed['resource_type'].upper()} `{removed['resource_name']}`. "
                f"{remaining} resource{'s' if remaining != 1 else ''} remaining."
            )
            if remaining > 0:
                msg += "\n\nSay **\"create PR\"** or add another resource."
                return build_response(msg, resource_status="batch_prompt")
            else:
                msg += "\n\nBatch is empty. Start by creating a resource."
                return build_response(msg)
        return build_response(
            f"Invalid index. Your batch has {len(session.batch)} resource(s). "
            f"Say 'remove 1', 'remove 2', etc.",
            resource_status="batch_prompt",
        )

    # Edit N
    edit_match = re.match(r"edit\s+(\d+)", msg_lower)
    if edit_match:
        idx = int(edit_match.group(1))
        agent = session.edit_batch_resource(idx)
        if agent:
            resource_name = (
                agent.collected_fields.get("database_name")
                or agent.collected_fields.get("bucket_name")
                or agent.collected_fields.get("role_name")
                or "resource"
            )
            return build_response(
                f"Editing {agent.resource_type.upper()} `{resource_name}`.\n\n"
                f"Current config:\n```yaml\n{agent.generated_yaml}\n```\n\n"
                f"What would you like to change?",
                resource_type=agent.resource_type,
                resource_status="awaiting_confirmation",
                generated_yaml=agent.generated_yaml,
            )
        return build_response(
            f"Invalid index. Your batch has {len(session.batch)} resource(s).",
            resource_status="batch_prompt",
        )

    # Not a batch command → treat as new resource request
    session.current_agent = None
    return await handle_idle_fn(session, user_message)


async def handle_batch_pr_setup(session: SessionState) -> dict:
    """Present multi-step PR setup for the entire batch."""
    batch = session.batch
    count = len(batch)

    type_counts = Counter(e["resource_type"].upper() for e in batch)
    type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())

    # Check GitHub token
    github_token = session.github_token
    if not github_token:
        github_token = await _load_github_token_from_db(session.session_id)
        if github_token:
            session.github_token = github_token

    if not github_token:
        for entry in batch:
            session.completed_resources.append(entry)
        session.clear_batch()
        return build_response(
            f"**{count} resources ready!** ({type_summary})\n\n"
            f"Connect your GitHub account to create a PR.\n"
            f"Your configurations are saved.",
            resource_status="confirmed",
        )

    # Create a batch agent and delegate to present_pr_setup
    agent = session.start_new_resource()
    agent.resource_type = "batch"
    agent.collected_fields = {"batch_count": count, "type_summary": type_summary}
    agent.generated_yaml = "\n---\n".join(e["yaml"] for e in batch)

    return await present_pr_setup(session, agent)


async def _load_github_token_from_db(session_id: str) -> Optional[str]:
    """Fallback: load GitHub token from DB if in-memory state lost."""
    try:
        from app.models.database import async_session_factory
        from app.models.schemas import ChatSession
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            db_session = result.scalar_one_or_none()
            if db_session and db_session.github_token:
                logger.info(f"Loaded GitHub token from DB for session {session_id}")
                return db_session.github_token
    except Exception as e:
        logger.warning(f"Failed to load GitHub token from DB: {e}")
    return None
