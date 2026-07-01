"""Agent loop — ReAct-style tool-calling loop with guardrails."""
from __future__ import annotations

import json
import logging
from typing import Any

from models.state import Session, Message
from agent.context_builder import build_system_prompt, build_conversation_messages
from services.llm import chat_with_tools
from tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS
from db.repository import load_user_profile, save_message

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


async def _auto_inject_state(llm_messages: list[dict]) -> None:
    """Guardrail: pre-call get_session_state so LLM always starts with fresh truth."""
    state_fn = TOOL_FUNCTIONS["get_session_state"]
    state_json = await state_fn()
    llm_messages.append({
        "role": "system",
        "content": f"[Auto-injected current state]\n{state_json}",
    })


async def _auto_derive_if_complete(
    tool_name: str, tool_result: str, llm_messages: list[dict], tool_call_id: str
) -> str:
    """Guardrail: if set_fields returns collection_complete, auto-trigger derive_fields.
    Returns the enriched tool result (with derive results appended), or original if no derive needed."""
    if tool_name != "set_fields":
        return tool_result

    try:
        result_data = json.loads(tool_result)
    except json.JSONDecodeError:
        return tool_result

    if not result_data.get("collection_complete"):
        return tool_result

    resource_id = result_data.get("resource_id")
    if not resource_id:
        return tool_result

    derive_fn = TOOL_FUNCTIONS.get("derive_fields")
    if not derive_fn:
        return tool_result

    logger.info(f"Guardrail: auto-deriving fields for {resource_id}")
    derive_result = await derive_fn(resource_id=resource_id)

    # Merge derive result into the set_fields result so LLM sees one coherent tool response
    try:
        derive_data = json.loads(derive_result)
        result_data["auto_derived"] = derive_data
    except json.JSONDecodeError:
        result_data["auto_derived"] = derive_result

    return json.dumps(result_data)


async def run_agent_turn(session: Session, user_message: str) -> str:
    """
    Process one user message through the agent loop.

    Guardrails (code-enforced, not prompt-dependent):
    1. Auto-inject current session state before first LLM call
    2. Auto-trigger derive_fields when set_fields returns collection_complete
    """
    # Record user message
    session.add_message("user", user_message)
    await save_message(session.session_id, session.messages[-1])

    # Load user profile for context
    profile = await load_user_profile(session.user_id)

    # Build system prompt
    system_prompt = build_system_prompt(session, profile)

    # Build message history for LLM
    llm_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(build_conversation_messages(session))

    # Guardrail 1: auto-inject fresh state
    await _auto_inject_state(llm_messages)

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
            # Guardrail 2: auto-derive if collection just completed (enriches the result)
            result = await _auto_derive_if_complete(func_name, result, llm_messages, tool_call["id"])

            llm_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            })

            logger.debug(f"Tool: {func_name}({args}) → {result[:200]}")

    # Exceeded max iterations
    session.add_message("assistant", "I'm having trouble processing this. Could you rephrase?")
    await save_message(session.session_id, session.messages[-1])
    return session.messages[-1].content
