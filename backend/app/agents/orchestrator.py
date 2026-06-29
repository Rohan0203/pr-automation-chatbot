"""
Orchestrator — thin state machine router for the resource configuration agent.

Receives user messages, determines the current phase, delegates to the appropriate
handler, and passes responses through the response decorator.

State machine:
  IDLE → COLLECTING → AWAITING_CONFIRMATION → REVIEWING → REVIEW_FAILED
       → BATCH_PROMPT → PR_SETUP → DONE

Also handles:
  - Structured flow (Q1→Q2→Q3→text_collection) for guided resource creation
  - Session resume from DB after server restart
  - Post-completion interactions (show yaml, create PR, edit)

Replaces the monolithic GeneratorAgent.process_message() method.
"""
import re
import json
import logging
from typing import Optional

from app.agents.session_state import (
    AgentState,
    SessionState,
    get_session,
    delete_session,
)
from app.agents.response_decorator import build_response, decorate_response
from app.agents.history_provider import SummaryHistoryProvider
from app.agents.prompts import SYSTEM_PROMPT, ROUTING_PROMPT
from app.agents.collector_agent import CollectorAgent
from app.agents.confirmation_handler import (
    handle_confirmation,
    finalize_resource,
    handle_review_failed,
)
from app.agents.batch_handler import (
    after_review_passed,
    handle_batch_prompt,
    handle_batch_pr_setup,
)
from app.agents.structured_flow_handler import (
    start_structured_flow,
    handle_structured_flow,
)
from app.agents.pr_handler import (
    present_pr_setup,
    handle_pr_setup,
    resume_pr_from_pause,
)
from app.agents.yaml_utils import generate_yaml
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry
from app.config import settings

logger = logging.getLogger(__name__)

_history_provider = SummaryHistoryProvider()
_collector = CollectorAgent()


class Orchestrator:
    """
    Thin state machine that routes messages to the appropriate handler.
    All domain logic lives in the handler modules — the orchestrator just decides
    who gets the message based on the current session phase.
    """

    async def process_message(self, session_id: str, user_message: str) -> dict:
        """Process a user message and return the agent's response."""
        if not user_message or not user_message.strip():
            return build_response(
                "It looks like you sent an empty message. How can I help you?"
            )

        session = get_session(session_id)

        # Resume from DB if needed (e.g. after server restart)
        if not session.current_agent and not session.conversation_history:
            await self._try_resume_from_db(session)

        _history_provider.add_message(session, "user", user_message)

        agent = session.current_agent

        # ── STATE LOG: incoming message context ──
        agent_phase = agent.phase if agent else "no_agent"
        agent_rtype = agent.resource_type if agent else None
        agent_fields_count = len(agent.collected_fields) if agent else 0
        flow_phase = session.structured_flow.phase if session.structured_flow else None
        logger.info(
            "[ORCHESTRATOR] ━━━ INCOMING MESSAGE ━━━\n"
            "  session_id   : %s\n"
            "  user_message : %.120s\n"
            "  agent_phase  : %s\n"
            "  resource_type: %s\n"
            "  fields_count : %d\n"
            "  flow_phase   : %s\n"
            "  batch_size   : %d\n"
            "  completed    : %d\n"
            "  has_yaml     : %s",
            session_id,
            user_message.replace('\n', ' '),
            agent_phase,
            agent_rtype,
            agent_fields_count,
            flow_phase,
            len(session.batch),
            len(session.completed_resources),
            bool(agent and agent.generated_yaml),
        )

        try:
            result = await self._route_message(session, agent, user_message)
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            result = build_response(
                f"I encountered an error: {str(e)}. Please try again.",
                resource_type=agent.resource_type if agent else None,
            )

        # Decorate response for consistent formatting
        phase = agent.phase if agent else None
        result = decorate_response(result, phase)

        # ── STATE LOG: outgoing response ──
        new_phase = session.current_agent.phase if session.current_agent else "no_agent"
        logger.info(
            "[ORCHESTRATOR] ━━━ RESPONSE ━━━\n"
            "  new_phase     : %s\n"
            "  resource_status: %s\n"
            "  resource_type : %s\n"
            "  has_yaml      : %s\n"
            "  has_options   : %s\n"
            "  needs_confirm : %s\n"
            "  message_len   : %d\n"
            "  message_start : %.150s",
            new_phase,
            result.get('resource_status'),
            result.get('resource_type'),
            bool(result.get('generated_yaml')),
            bool(result.get('options')),
            result.get('needs_confirmation', False),
            len(result.get('message', '')),
            result.get('message', '')[:150].replace('\n', ' '),
        )

        _history_provider.add_message(session, "assistant", result["message"])
        return result

    async def _route_message(
        self, session: SessionState, agent: Optional[AgentState], user_message: str
    ) -> dict:
        """Route to the correct handler based on session phase."""

        # Structured flow intercept
        if session.structured_flow and agent is None:
            logger.info("[ROUTE] → structured_flow_handler (phase=%s)", session.structured_flow.phase)
            return await handle_structured_flow(
                session, user_message, self._build_messages
            )

        # Batch command intercept
        if agent is None and session.batch:
            batch_keywords = [
                "create pr", "show batch", "remove ", "edit ",
                "submit", "make pr", "batch", "proceed",
            ]
            if any(kw in user_message.strip().lower() for kw in batch_keywords):
                logger.info("[ROUTE] → batch_handler (batch_size=%d)", len(session.batch))
                return await handle_batch_prompt(
                    session, user_message, self._handle_idle
                )

        if agent is None or agent.phase == "idle":
            if agent is None and session.completed_resources:
                post_result = await self._try_post_completion(session, user_message)
                if post_result:
                    logger.info("[ROUTE] → post_completion (completed=%d)", len(session.completed_resources))
                    return post_result
            logger.info("[ROUTE] → handle_idle")
            return await self._handle_idle(session, user_message)

        elif agent.phase == "detecting":
            logger.info("[ROUTE] → handle_idle (was detecting, resetting)")
            session.current_agent = None
            return await self._handle_idle(session, user_message)

        elif agent.phase == "collecting":
            logger.info("[ROUTE] → collector_agent.handle_collecting (resource=%s, fields=%d)",
                        agent.resource_type, len(agent.collected_fields))
            return await _collector.handle_collecting(
                session, user_message, self._build_messages
            )

        elif agent.phase == "awaiting_confirmation":
            logger.info("[ROUTE] → confirmation_handler (resource=%s)", agent.resource_type)
            return await handle_confirmation(
                session, user_message,
                build_messages_fn=self._build_messages,
                cancel_fn=self._cancel_current_resource,
                after_review_fn=after_review_passed,
            )

        elif agent.phase == "reviewing":
            logger.info("[ROUTE] → reviewing (waiting, resource=%s)", agent.resource_type)
            return build_response(
                "⏳ Your configuration is being reviewed. Please wait...",
                resource_type=agent.resource_type,
                resource_status="reviewing",
            )

        elif agent.phase == "review_failed":
            logger.info("[ROUTE] → review_failed_handler (resource=%s, attempt=%d)",
                        agent.resource_type, agent.review_attempts)
            return await handle_review_failed(
                session, user_message,
                build_messages_fn=self._build_messages,
                cancel_fn=self._cancel_current_resource,
                after_review_fn=after_review_passed,
                match_fix_option_fn=self._match_fix_option,
            )

        elif agent.phase == "batch_prompt":
            logger.info("[ROUTE] → batch_handler (batch_size=%d)", len(session.batch))
            return await handle_batch_prompt(
                session, user_message, self._handle_idle
            )

        elif agent.phase == "pr_setup":
            logger.info("[ROUTE] → pr_handler (sub_phase=%s)", getattr(agent, 'pr_sub_phase', 'unknown'))
            result = await handle_pr_setup(session, user_message)
            if result.get("resource_status") == "edit_config_requested":
                extracted = result.pop("_extracted_fields", {})
                logger.info("[ROUTE] → config_edit_from_pr (fields=%s)", list(extracted.keys()))
                return await self._handle_config_edit_from_pr(
                    session, agent, extracted, result.get("message", "")
                )
            return result

        elif agent.phase == "done":
            logger.info("[ROUTE] → post_completion (phase=done)")
            return await self._handle_post_completion(session, user_message)

        else:
            logger.info("[ROUTE] → handle_idle (unknown phase=%s)", agent.phase)
            return await self._handle_idle(session, user_message)

    # ─── IDLE / ROUTING ────────────────────────────────────────

    async def _handle_idle(self, session: SessionState, user_message: str) -> dict:
        msg_lower = user_message.strip().lower()

        # Session end
        end_keywords = {
            "done", "bye", "exit", "goodbye", "finished",
            "no more", "nothing else", "all done", "i'm done",
            "im done", "that's all", "that is all", "end",
        }
        if msg_lower in end_keywords or any(
            kw in msg_lower for kw in ["that's all", "that is all", "no more", "all done", "i'm done"]
        ):
            logger.info("[IDLE] → session_end")
            return await self._handle_session_end(session)

        # PR status
        pr_status_triggers = {
            "show my prs", "my prs", "pr status", "show prs",
            "list prs", "check pr", "pr list", "my pull requests",
        }
        if msg_lower in pr_status_triggers or any(
            t in msg_lower for t in ["show my pr", "pr status", "my pull request", "check my pr"]
        ):
            return await self._handle_pr_status(session)

        # Resource creation intent → structured flow
        create_triggers = [
            "create", "set up", "setup", "configure", "provision", "make", "build",
            "need", "want", "new", "add", "get started", "start", "help me create",
            "s3", "glue", "iam", "bucket", "database", "role",
            "source", "dataproduct", "scripts", "engassets", "curated", "serving",
            "raw", "internal", "resource", "infrastructure", "yaml", "config",
        ]
        if any(t in msg_lower for t in create_triggers):
            logger.info("[IDLE] → start_structured_flow (resource intent detected)")
            return start_structured_flow(session)

        # General conversation — LLM routing
        logger.info("[IDLE] → LLM routing (no keyword match)")
        messages = self._build_messages(
            session,
            ROUTING_PROMPT.format(
                resource_triggers=schema_registry.get_triggers_summary(),
                user_message=user_message,
            ),
        )

        try:
            result = await llm_client.extract_json(messages)
        except Exception as e:
            logger.error(f"Routing LLM call failed: {e}")
            return start_structured_flow(session)

        intent = result.get("intent", "general")
        detected_type = result.get("detected_resource_type")
        confidence = result.get("confidence", 0)
        extracted = result.get("extracted_fields", {})
        general_response = result.get("general_response")

        logger.info("[IDLE] LLM routing result: intent=%s, detected_type=%s, confidence=%.2f, extracted_keys=%s",
                    intent, detected_type, confidence, list(extracted.keys()) if extracted else [])

        if intent == "resource" and detected_type and confidence >= 0.6:
            return start_structured_flow(session, detected_type, extracted)

        # Resource question (not creation)
        if detected_type and schema_registry.get_resource_context(detected_type):
            resource_context = schema_registry.get_resource_context(detected_type)
            help_prompt = (
                f"The user asked a question about **{detected_type}** resource configuration.\n\n"
                f"RESOURCE GUIDE:\n{resource_context}\n\n"
                f"User question: \"{user_message}\"\n\n"
                f"Answer using the resource guide. After answering, ask if they'd like to "
                f"create a {detected_type} configuration.\n\nRespond in plain text (not JSON)."
            )
            try:
                help_response = await llm_client.chat(
                    [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": help_prompt}],
                    temperature=0.1,
                )
                return build_response(help_response)
            except Exception:
                pass

        if general_response:
            return build_response(general_response)

        return build_response(
            "Hi! I help create infrastructure YAML configurations and raise PRs.\n\n"
            "I support **S3 buckets** and **Glue databases**.\n\n"
            "Ready to get started?",
            options=[
                {"label": "🚀 Get Started", "value": "get started"},
                {"label": "❓ What can you do?", "value": "what can you do"},
            ],
        )

    # ─── POST-COMPLETION ───────────────────────────────────────

    async def _try_post_completion(self, session: SessionState, user_message: str) -> Optional[dict]:
        msg_lower = user_message.strip().lower()
        last_resource = session.completed_resources[-1] if session.completed_resources else None
        if not last_resource:
            return None

        yaml_content = last_resource.get("yaml", "")
        fields = last_resource.get("fields", {})
        rtype = last_resource.get("resource_type", "unknown")
        pr_url = last_resource.get("pr_url")

        show_yaml_triggers = [
            "show yaml", "show the yaml", "show my yaml",
            "show config", "show my config", "show the config",
            "see the yaml", "view yaml", "view config",
        ]
        if any(trigger in msg_lower for trigger in show_yaml_triggers):
            return build_response(
                f"Here is your last {rtype.upper()} configuration:\n\n"
                f"```yaml\n{yaml_content}\n```\n\n"
                f"Would you like to create another resource, edit this one, or are we done?",
                resource_type=rtype,
                resource_status="confirmed",
                generated_yaml=yaml_content,
            )

        if not pr_url:
            pr_triggers = ["create pr", "make pr", "create a pr", "make a pr", "submit pr"]
            if any(trigger in msg_lower for trigger in pr_triggers):
                agent = session.start_new_resource()
                agent.resource_type = rtype
                agent.collected_fields = fields.copy()
                agent.generated_yaml = yaml_content
                agent.phase = "pr_setup"
                session.completed_resources.pop()
                return await self._proceed_to_pr_setup(session, agent)

        return None

    async def _handle_post_completion(self, session: SessionState, user_message: str) -> dict:
        msg_lower = user_message.strip().lower()
        last_resource = session.completed_resources[-1] if session.completed_resources else None

        if last_resource:
            yaml_content = last_resource.get("yaml", "")
            fields = last_resource.get("fields", {})
            rtype = last_resource.get("resource_type", "unknown")
            pr_url = last_resource.get("pr_url")

            show_yaml_triggers = [
                "show yaml", "show the yaml", "show my yaml",
                "show config", "show my config", "show the config",
                "yaml", "see the yaml", "view yaml", "view config",
            ]
            if any(trigger in msg_lower for trigger in show_yaml_triggers):
                return build_response(
                    f"Here is your last {rtype.upper()} configuration:\n\n"
                    f"```yaml\n{yaml_content}\n```\n\n"
                    f"Would you like to create another resource, or are we done?",
                    resource_type=rtype,
                    resource_status="confirmed",
                    generated_yaml=yaml_content,
                )

            if not pr_url:
                pr_triggers = [
                    "create pr", "make pr", "proceed", "create a pr",
                    "make a pr", "go ahead", "pr",
                ]
                if any(trigger in msg_lower for trigger in pr_triggers):
                    agent = session.start_new_resource()
                    agent.resource_type = rtype
                    agent.collected_fields = fields.copy()
                    agent.generated_yaml = yaml_content
                    agent.phase = "pr_setup"
                    session.completed_resources.pop()
                    return await self._proceed_to_pr_setup(session, agent)

            edit_triggers = ["edit", "change", "update", "fix", "modify"]
            if any(trigger in msg_lower for trigger in edit_triggers):
                agent = session.start_new_resource()
                agent.resource_type = rtype
                agent.collected_fields = fields.copy()
                agent.generated_yaml = yaml_content
                agent.phase = "awaiting_confirmation"
                agent.initial_listing_shown = True
                agent.optional_fields_offered = True
                session.completed_resources.pop()
                return await handle_confirmation(
                    session, user_message,
                    build_messages_fn=self._build_messages,
                    cancel_fn=self._cancel_current_resource,
                    after_review_fn=after_review_passed,
                )

        session.current_agent = None
        return await self._handle_idle(session, user_message)

    async def _handle_session_end(self, session: SessionState) -> dict:
        session.current_agent = None
        all_resources = session.completed_resources + session.batch
        session.clear_batch()

        if not all_resources:
            return build_response(
                "Goodbye! No resources were created this session. Come back anytime."
            )

        parts = ["**Session Complete!** Here's what we created:\n"]
        for i, res in enumerate(all_resources, 1):
            rtype = res.get("resource_type", "unknown").upper()
            fields = res.get("fields", {})
            name = (
                fields.get("bucket_name")
                or fields.get("database_name")
                or fields.get("role_name")
                or res.get("resource_name")
                or "unnamed"
            )
            parts.append(f"**{i}. {rtype}** — `{name}`")
            pr_url = res.get("pr_url")
            if pr_url:
                parts.append(f"   PR: {pr_url}")

        parts.append(f"\n**{len(all_resources)} resource(s)** configured. Goodbye!")
        return build_response("\n".join(parts))

    async def _handle_pr_status(self, session: SessionState) -> dict:
        from app.models.database import async_session_factory
        from app.models.schemas import PRRecord
        from app.services.scm_adapter import get_pr_live_status
        from sqlalchemy import select

        username = session.github_username
        if not username:
            return build_response("Connect your GitHub account first to see your PRs.")

        try:
            async with async_session_factory() as db:
                stmt = (
                    select(PRRecord)
                    .where(PRRecord.github_username == username)
                    .order_by(PRRecord.created_at.desc())
                    .limit(10)
                )
                result = await db.execute(stmt)
                records = result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to fetch PR records: {e}")
            return build_response("Sorry, I couldn't fetch your PR records right now.")

        if not records:
            return build_response(
                "No PRs found for your account. Create a resource and raise a PR first!"
            )

        parts = ["📋 **Your PRs:**\n"]
        parts.append("| # | Title | Status | Resources | Link |")
        parts.append("|---|-------|--------|-----------|------|")

        status_icons = {
            "open": "🟢 Open", "closed": "🔴 Closed",
            "merged": "🟣 Merged", "unknown": "⚪ Unknown",
        }

        for i, rec in enumerate(records, 1):
            if session.github_token:
                try:
                    live = await get_pr_live_status(session.github_token, rec.pr_url)
                    state = live.get("state", "unknown")
                except Exception:
                    state = "unknown"
            else:
                state = "unknown"

            icon = status_icons.get(state, f"⚪ {state}")
            title = rec.title or "Untitled"
            count = rec.resource_count or 1
            types = ", ".join(t.upper() for t in (rec.resource_types or []))
            resource_info = f"{count} ({types})" if types else str(count)
            pr_link = (
                f"[PR #{rec.pr_number}]({rec.pr_url})"
                if rec.pr_number
                else f"[Link]({rec.pr_url})"
            )
            parts.append(f"| {i} | {title} | {icon} | {resource_info} | {pr_link} |")

        parts.append("\n_Showing up to 10 most recent PRs._")
        return build_response("\n".join(parts))

    # ─── PR SETUP HELPERS ──────────────────────────────────────

    async def _proceed_to_pr_setup(
        self, session: SessionState, agent: AgentState, prefix_message: str = ""
    ) -> dict:
        github_token = session.github_token
        if not github_token:
            github_token = await self._load_github_token_from_db(session.session_id)
            if github_token:
                session.github_token = github_token

        if not github_token:
            agent.phase = "done"
            rtype = (agent.resource_type or "unknown").upper()
            session.complete_current_resource()
            msg = prefix_message + (
                f"**{rtype} configuration confirmed!**\n\n"
                f"Connect your GitHub account to enable automatic PR creation.\n\n"
                f"Would you like to create another resource, or are we done?"
            )
            return build_response(
                msg,
                resource_type=agent.resource_type,
                resource_status="confirmed",
                generated_yaml=agent.generated_yaml,
            )

        agent.phase = "pr_setup"
        pr_response = await present_pr_setup(session, agent)
        if prefix_message:
            pr_response["message"] = prefix_message + pr_response["message"]
        return pr_response

    async def _handle_config_edit_from_pr(
        self, session: SessionState, agent: AgentState,
        extracted_fields: dict, prefix_message: str = "",
    ) -> dict:
        if not extracted_fields:
            return build_response(
                "Which field would you like to change, and to what value?\n"
                "For example: *\"change bucket_name to dev-lh1-corp-src\"*",
                resource_type=agent.resource_type,
                resource_status="pr_setup",
                generated_yaml=agent.generated_yaml,
            )

        saved_pr = {
            "pr_branch_name": agent.pr_branch_name,
            "pr_title": agent.pr_title,
            "pr_body": agent.pr_body,
            "fork_exists": agent.fork_exists,
            "fork_full_name": agent.fork_full_name,
            "pr_target_branch": agent.pr_target_branch,
            "available_branches": agent.available_branches,
        }

        agent.collected_fields.update(extracted_fields)
        agent.phase = "collecting"
        regen_result = await generate_yaml(
            session, agent, self._build_messages,
            prefix_message=prefix_message or "Configuration updated.",
        )

        if agent.phase != "awaiting_confirmation":
            return regen_result

        agent.phase = "awaiting_confirmation"
        finalize_result = await finalize_resource(session, agent, after_review_passed)

        # Restore PR settings
        for k, v in saved_pr.items():
            setattr(agent, k, v)

        return finalize_result

    # ─── SHARED HELPERS ────────────────────────────────────────

    def _cancel_current_resource(self, session: SessionState) -> dict:
        session.current_agent = None

        resume = resume_pr_from_pause(session)
        if resume:
            return resume

        batch_count = len(session.batch)
        if batch_count > 0:
            summary = session.get_batch_summary()
            return build_response(
                f"Current resource cancelled.\n\n"
                f"Your batch still has {batch_count} resource{'s' if batch_count != 1 else ''}:\n\n"
                f"{summary}\n\n"
                f"Say **\"create PR\"** to submit, **\"add another\"** to continue, or **\"show batch\"** for details.",
                resource_status="batch_prompt",
            )
        return build_response("Configuration cancelled. Let me know if you'd like to start over.")

    def _build_messages(self, session: SessionState, user_prompt: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *_history_provider.get_messages(session)[:-1],
            {"role": "user", "content": user_prompt},
        ]

    def _match_fix_option(self, msg_lower: str, agent: AgentState) -> Optional[dict]:
        match = re.match(
            r"(?:option|fix|go with|choose|pick|select)?\s*(\d+)", msg_lower
        )
        if not match:
            return None

        option_num = int(match.group(1))
        if not agent.review_result:
            return None

        all_options = []
        for v in agent.review_result.violations:
            for opt in v.fix_options:
                all_options.append(opt)

        if option_num < 1 or option_num > len(all_options):
            return None

        selected = all_options[option_num - 1]
        changes = selected.get("changes", {})
        if not changes:
            return None

        concrete = {}
        for k, v in changes.items():
            v_str = str(v).lower()
            if v_str.startswith("use ") or v_str.startswith("modify ") or "e.g." in v_str:
                continue
            concrete[k] = v

        return concrete if concrete else None

    async def _load_github_token_from_db(self, session_id: str) -> Optional[str]:
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

    async def _try_resume_from_db(self, session: SessionState):
        try:
            from app.models.database import async_session_factory
            from app.models.schemas import ResourceState, ChatMessage, ChatSession, ResourceStatus
            from sqlalchemy import select

            async with async_session_factory() as db:
                db_session_result = await db.execute(
                    select(ChatSession).where(ChatSession.id == session.session_id)
                )
                chat_session = db_session_result.scalar_one_or_none()
                if not chat_session:
                    return

                session.conversation_summary = chat_session.conversation_summary
                session.github_token = chat_session.github_token
                session.github_username = chat_session.github_username

                msgs_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session.session_id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(20)
                )
                for msg in reversed(msgs_result.scalars().all()):
                    session.conversation_history.append({
                        "role": msg.role.value.lower(),
                        "content": msg.content,
                    })

                res_result = await db.execute(
                    select(ResourceState)
                    .where(
                        ResourceState.session_id == session.session_id,
                        ResourceState.status.in_([
                            ResourceStatus.COLLECTING,
                            ResourceStatus.AWAITING_CONFIRMATION,
                        ]),
                    )
                    .order_by(ResourceState.updated_at.desc())
                    .limit(1)
                )
                resource_state = res_result.scalar_one_or_none()

                if resource_state:
                    agent = session.start_new_resource()
                    agent.resource_type = resource_state.resource_type
                    agent.collected_fields = resource_state.collected_fields or {}
                    agent.current_field = resource_state.current_field
                    agent.generated_yaml = resource_state.generated_yaml

                    if resource_state.status == ResourceStatus.COLLECTING:
                        agent.phase = "collecting"
                    elif resource_state.status == ResourceStatus.AWAITING_CONFIRMATION:
                        agent.phase = "awaiting_confirmation"

                if session.conversation_history:
                    logger.info(
                        f"Resumed session {session.session_id} from DB: "
                        f"{len(session.conversation_history)} messages, "
                        f"resource={'yes' if resource_state else 'no'}"
                    )

        except Exception as e:
            logger.warning(f"Session resume from DB failed: {e}", exc_info=True)


# ── Singleton ─────────────────────────────────────────────────

orchestrator = Orchestrator()
