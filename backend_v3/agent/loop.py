"""Agent loop — ReAct-style tool-calling loop."""
from __future__ import annotations

import json
import logging
from typing import Any

from models.state import Session, Message
from agent.context_builder import build_system_prompt, build_conversation_messages
from services.llm import chat_with_tools
from tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS
from db.repository import load_preferences, save_message

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


async def run_agent_turn(session: Session, user_message: str) -> str:
    """
    Process one user message through the agent loop.

    1. Add user message to session
    2. Build context (system prompt + conversation history)
    3. Loop: call LLM → if tool_calls, execute them and feed results back → repeat
    4. When LLM responds with content (no tool_calls), return that as the response
    """
    # Record user message
    session.add_message("user", user_message)
    await save_message(session.session_id, session.messages[-1])

    # Load user preferences for context
    preferences = await load_preferences(session.user_id)

    # Build system prompt
    system_prompt = build_system_prompt(session, preferences)

    # Build message history for LLM
    # We maintain a running list for this turn (includes tool call/result messages)
    llm_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(build_conversation_messages(session))

    # Agent loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Call LLM
        response = await chat_with_tools(llm_messages, tools=TOOL_SCHEMAS)

        # If no tool calls — we have the final response
        if not response.get("tool_calls"):
            content = response.get("content", "")
            session.add_message("assistant", content)
            await save_message(session.session_id, session.messages[-1])
            return content

        # Has tool calls — execute them
        # First, add assistant message with tool_calls to the LLM messages
        llm_messages.append(response)

        for tool_call in response["tool_calls"]:
            func_name = tool_call["function"]["name"]
            try:
                args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            # Execute tool
            tool_fn = TOOL_FUNCTIONS.get(func_name)
            if tool_fn is None:
                result = json.dumps({"error": f"Unknown tool: {func_name}"})
            else:
                try:
                    result = await tool_fn(**args)
                except Exception as e:
                    logger.exception(f"Tool {func_name} failed")
                    result = json.dumps({"error": str(e)})

            # Add tool result to LLM messages
            llm_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            })

            logger.debug(f"Tool: {func_name}({args}) → {result[:200]}")

    # Exceeded max iterations — force a response
    session.add_message("assistant", "I'm having trouble processing this. Could you rephrase?")
    await save_message(session.session_id, session.messages[-1])
    return session.messages[-1].content
