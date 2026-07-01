"""Context builder — assembles the system prompt with dynamic context."""
from __future__ import annotations

from pathlib import Path

from models.state import Session, Preference

_CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"


def build_system_prompt(session: Session, preferences: list[Preference]) -> str:
    """
    Build the full system prompt by combining:
    1. Base system prompt (agent.md)
    2. User preferences (if any)
    3. Supported resource types hint
    """
    # 1. Base system prompt
    system_md = (_CONTEXT_DIR / "system.md").read_text(encoding="utf-8")

    # 2. User preferences
    pref_section = ""
    if preferences:
        pref_lines = [f"- {p.key}: {p.value}" for p in preferences]
        pref_section = (
            "\n\n# User Preferences (always respect these)\n"
            + "\n".join(pref_lines)
        )

    # 3. Supported resources
    resources_dir = _CONTEXT_DIR / "resources"
    available = [f.stem for f in resources_dir.glob("*.md")] if resources_dir.exists() else []
    resource_hint = (
        f"\n\n# Available Resource Types\n"
        f"You can provision: {', '.join(available)}. "
        f"Call `get_resource_info` with the type to learn its fields."
    )

    return system_md + pref_section + resource_hint


def build_conversation_messages(session: Session) -> list[dict]:
    """
    Convert session messages to OpenAI format.
    Only include user/assistant messages (not internal tool messages).
    """
    messages = []
    for msg in session.messages:
        if msg.role in ("user", "assistant"):
            entry = {"role": msg.role, "content": msg.content}
            if msg.role == "assistant" and msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            messages.append(entry)
    return messages
