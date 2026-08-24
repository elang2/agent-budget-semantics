"""
OpenAI Swarm budget enforcement runner.

Budget primitive: max_turns in run() loop
What it counts: ALL messages in history since invocation (user + assistant + tool results)
Unique: Swarm counts history length, not "iterations". Adding a tool result message AND
the assistant response both increment the count. So budget=6 with one tool call = 3 turns
consumed (assistant tool_call + tool_result + assistant response).

This is the most permissive counting in practice but also the most confusing to reason about.
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through OpenAI Swarm with max_turns budget."""
    try:
        from swarm import Swarm, Agent
        from openai import OpenAI
    except ImportError as e:
        return RunResult(
            framework="swarm",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    def get_weather(city: str) -> str:
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    def calculate(expression: str) -> str:
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("calculate", json.dumps({"expression": expression}))

    tools = []
    for td in scenario.get("tool_definitions", []):
        if td["name"] == "get_weather":
            tools.append(get_weather)
        elif td["name"] == "calculate":
            tools.append(calculate)

    agent = Agent(
        name="BudgetTestAgent",
        instructions="You are a helpful assistant. Use tools when needed.",
        functions=tools,
    )

    client = OpenAI(base_url=mock_url + "/v1", api_key="mock-key")
    swarm_client = Swarm(client=client)

    messages = [{"role": "user", "content": "Perform the requested task."}]

    try:
        response = swarm_client.run(
            agent=agent,
            messages=messages,
            max_turns=budget_value,
        )

        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        return RunResult(
            framework="swarm",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by="completed" if response.messages else "empty",
            metadata={
                "messages_in_response": len(response.messages) if response.messages else 0,
                "note": "Swarm counts len(history) - init_len as 'turns'. "
                       "Each assistant message AND each tool result message counts. "
                       "So one tool call = 2 turns consumed (call + result).",
            },
        )

    except Exception as e:
        return RunResult(
            framework="swarm",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
