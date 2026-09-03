"""
Agno streaming runner — exercises Agent.arun(..., stream=True).

Pairs with runner_agno.py (non-streaming) to cover the D13 / D14 streaming
dimensions in DIMENSIONS.md. Same scenario, same deterministic mock, same
tool_call_limit — but the request goes through the streaming code path in
the model backend so we observe how the budget guard behaves under SSE
event iteration rather than a single unary response.

Motivating case: agno-agi/agno#8324 splits the tool_call_limit guard across
four response loops in libs/agno/agno/models/base.py — response(),
aresponse(), response_stream(), aresponse_stream(). The non-streaming
runner exercises the first two; this one exercises the last two.
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through Agno Agent with stream=True."""
    try:
        from agno.agent import Agent
        from agno.models.openai import OpenAIChat
        from agno.tools import tool
    except ImportError as e:
        return RunResult(
            framework="agno_stream",
            scenario=scenario["name"],
            budget_param="tool_call_limit",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    @tool
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    @tool
    def calculate(expression: str) -> str:
        """Perform arithmetic."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("calculate", json.dumps({"expression": expression}))

    tools_list: list[Any] = []
    for td in scenario.get("tool_definitions", []) or scenario.get("tools", []):
        if td["name"] == "get_weather":
            tools_list.append(get_weather)
        elif td["name"] == "calculate":
            tools_list.append(calculate)

    model = OpenAIChat(
        id="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    agent = Agent(
        model=model,
        tools=tools_list,
        tool_call_limit=budget_value,
    )

    events_seen = 0
    stream_chunks_observed = 0
    task_prompt = scenario.get("task", "Perform the requested task.")

    try:
        async for event in agent.arun(task_prompt, stream=True):
            events_seen += 1
            event_type = type(event).__name__
            if "Content" in event_type or "Chunk" in event_type:
                stream_chunks_observed += 1
            if events_seen > 500:
                break

        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        stopped_by = "completed"
        if events_seen > 500:
            stopped_by = "runaway"

        return RunResult(
            framework="agno_stream",
            scenario=scenario["name"],
            budget_param="tool_call_limit",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by=stopped_by,
            metadata={
                "note": (
                    "Streaming variant of runner_agno. Exercises the "
                    "response_stream / aresponse_stream code paths in "
                    "libs/agno/agno/models/base.py. Iterates events from "
                    "agent.arun(prompt, stream=True) rather than awaiting a "
                    "single RunOutput."
                ),
                "events_seen": events_seen,
                "stream_chunks_observed": stream_chunks_observed,
                "streaming": True,
            },
        )

    except Exception as e:
        return RunResult(
            framework="agno_stream",
            scenario=scenario["name"],
            budget_param="tool_call_limit",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
