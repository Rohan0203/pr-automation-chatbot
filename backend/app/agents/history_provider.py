"""
History Providers — abstractions for how conversation history is sent to the LLM.

FullHistoryProvider: Sends last N messages verbatim (Phase 1 default).
SummaryHistoryProvider: Hybrid — sends DB summary + last 20 in-memory messages (Phase 2).
"""
import logging
from typing import Optional, Protocol, TYPE_CHECKING

from app.services.llm_client import llm_client

if TYPE_CHECKING:
    from app.agents.session_state import SessionState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PROTOCOL
# ═══════════════════════════════════════════════════════════════

class HistoryProvider(Protocol):
    """Protocol for providing conversation history to the LLM."""

    def get_messages(self, session: "SessionState") -> list[dict]:
        """Return the list of messages to include in LLM context."""
        ...

    def add_message(self, session: "SessionState", role: str, content: str) -> None:
        """Record a message."""
        ...


# ═══════════════════════════════════════════════════════════════
# FULL HISTORY PROVIDER (kept for reference / fallback)
# ═══════════════════════════════════════════════════════════════

class FullHistoryProvider:
    """
    Sends the full conversation history to the LLM.
    Simple and accurate. Truncates to last MAX_MESSAGES to avoid token overflow.
    """

    MAX_MESSAGES = 30

    def get_messages(self, session: "SessionState") -> list[dict]:
        """Return full history (truncated to last N messages)."""
        return session.conversation_history[-self.MAX_MESSAGES:]

    def add_message(self, session: "SessionState", role: str, content: str) -> None:
        """Append message to history."""
        session.conversation_history.append({"role": role, "content": content})


# ═══════════════════════════════════════════════════════════════
# SUMMARY HISTORY PROVIDER (Phase 2 — hybrid approach)
# ═══════════════════════════════════════════════════════════════

SUMMARIZATION_THRESHOLD = 20
RECENT_MESSAGES_TO_KEEP = 20

SUMMARY_SYSTEM_PROMPT = """You are a conversation summarizer for an infrastructure chatbot.
Given a sequence of messages between a user and an AI assistant about 
AWS infrastructure configuration, produce a concise factual summary.

The summary must include:
- What resource types were discussed
- What was successfully configured (include key field values like intake_id, resource names)
- What PRs were created (include PR URLs if mentioned)
- Any incomplete or cancelled resource creation attempts
- Current state of any ongoing resource configuration

Keep the summary under 200 words. Be factual and specific. No opinions."""


class SummaryHistoryProvider:
    """
    Hybrid history provider for Phase 2.

    - Uses in-memory SessionState.conversation_history for recent messages
    - Uses SessionState.conversation_summary (loaded from DB) for older context

    When total in-memory messages > 20:
        Context = [system msg with summary] + [last 20 in-memory messages]
    When total in-memory messages <= 20:
        Context = [all in-memory messages] (same as FullHistoryProvider)

    No DB access needed in get_messages() or add_message().
    Summary is loaded into SessionState on session resume.
    """

    def get_messages(self, session: "SessionState") -> list[dict]:
        """Return message list for LLM context. Uses in-memory history."""
        history = session.conversation_history

        if len(history) <= RECENT_MESSAGES_TO_KEEP:
            return list(history[-RECENT_MESSAGES_TO_KEEP:])

        # More than 20 messages — use summary + recent 20
        messages = []
        if session.conversation_summary:
            messages.append({
                "role": "system",
                "content": f"CONVERSATION SUMMARY (earlier messages):\n{session.conversation_summary}",
            })
        messages.extend(history[-RECENT_MESSAGES_TO_KEEP:])
        return messages

    def add_message(self, session: "SessionState", role: str, content: str) -> None:
        """Append message to in-memory history."""
        session.conversation_history.append({"role": role, "content": content})


# ═══════════════════════════════════════════════════════════════
# BACKGROUND SUMMARIZATION
# ═══════════════════════════════════════════════════════════════

async def maybe_update_summary(session_id: str) -> None:
    """
    Background task: check if summarization is needed, and generate/save summary.

    Trigger conditions (ANY of these):
    1. total_messages > 20 AND total_messages % 20 == 0  (regular interval)
    2. total_messages > 20 AND conversation_summary IS NULL  (missed/failed trigger)

    Creates its own DB session — safe to run after request completes.
    Must NOT raise exceptions — wraps in try/except.
    """
    try:
        from app.models.database import async_session_factory
        from app.models.schemas import ChatSession, ChatMessage
        from sqlalchemy import select, func

        async with async_session_factory() as db:
            # Count total messages
            count_result = await db.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == session_id
                )
            )
            total = count_result.scalar() or 0

            if total <= SUMMARIZATION_THRESHOLD:
                return

            # Get current summary
            session_result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            chat_session = session_result.scalar_one_or_none()
            if not chat_session:
                return

            existing_summary = chat_session.conversation_summary

            should_summarize = (
                total % SUMMARIZATION_THRESHOLD == 0
                or existing_summary is None
            )

            if not should_summarize:
                return

            logger.info(
                f"Summarizing session {session_id}: {total} messages, "
                f"existing_summary={'yes' if existing_summary else 'no'}"
            )

            # Fetch older messages (everything except last 20)
            older_msgs_result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
                .limit(total - RECENT_MESSAGES_TO_KEEP)
            )
            older_msgs = older_msgs_result.scalars().all()

            if not older_msgs:
                return

            # Build messages for summarization
            conversation_text = "\n".join(
                f"{m.role.value}: {m.content}" for m in older_msgs
            )

            summary_messages = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Summarize this conversation:\n\n{conversation_text}"},
            ]

            # Generate summary via LLM
            summary = await llm_client.chat(summary_messages, temperature=0.0)

            # Save to DB
            chat_session.conversation_summary = summary.strip()
            await db.commit()

            # Also update in-memory SessionState
            try:
                from app.agents.session_state import get_session
                mem_session = get_session(session_id)
                mem_session.conversation_summary = summary.strip()
            except Exception:
                pass  # In-memory session may not exist

            logger.info(f"Summary updated for session {session_id} ({len(summary)} chars)")

    except Exception as e:
        logger.error(f"Summarization failed for session {session_id}: {e}", exc_info=True)
        # Do NOT re-raise — chat continues working without summary
