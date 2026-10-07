"""
OpenAI Agents SDK budget enforcement runner.

Budget primitive: max_turns on Runner.run()
What it counts: Each "turn" is one full LLM call (including tool use resolution)
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through OpenAI Agents SDK with max_turns budget."""
    try:
        from agents import Agent, Runner, function_tool, ModelSettings
        from agents.exceptions import MaxTurnsExceeded
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI
    except ImportError as e:
        return RunResult(
            framework="openai_agents",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    @function_tool
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    @function_tool
    def calculate(expression: str) -> str:
        """Perform arithmetic."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("calculate", json.dumps({"expression": expression}))

    tools = []
    for td in scenario.get("tool_definitions", []):
        if td["name"] == "get_weather":
            tools.append(get_weather)
        elif td["name"] == "calculate":
            tools.append(calculate)

    client = AsyncOpenAI(base_url=mock_url + "/v1", api_key="mock-key")
    model = OpenAIChatCompletionsModel(
        model="mock-budget-llm",
        openai_client=client,
    )

    agent = Agent(
        name="budget_test_agent",
        instructions="You are a helpful assistant. Use tools as needed.",
        tools=tools,
        model=model,
    )

    llm_calls = 0
    stopped_by = "natural"
    error_msg = None

    def ledger_llm_calls():
        """Request count observed by the mock, as the other runners read it.

        This runner previously set `llm_calls = budget_value` on the
        budget-stop path, which made `actual_llm_calls` a restatement of the
        declared limit rather than a measurement. That is why
        `field_provenance.framework_reported_llm_calls_by_framework` records
        this runner as `declared` where agno, crewai and semantic_kernel are
        `ledger`.
        """
        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger
        return len(entries)

    try:
        result = await Runner.run(
            agent,
            "Check the weather in various cities.",
            max_turns=budget_value,
        )

        for item in result.raw_responses:
            llm_calls += 1

        if hasattr(result, 'last_turn') and result.last_turn >= budget_value:
            stopped_by = "budget"

    except MaxTurnsExceeded as e:
        # Match the SDK's own exception type, not a substring of its message.
        # The previous test was `"max turns" in msg or "exceeded" in msg`, which
        # also matches a rate-limit ("quota exceeded") or a context-length
        # ("maximum context length exceeded") failure, and would have recorded
        # either as a clean budget stop.
        stopped_by = "budget"
        error_msg = str(e)
        llm_calls = ledger_llm_calls()

    except Exception as e:
        return RunResult(
            framework="openai_agents",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=ledger_llm_calls(),
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=str(e),
        )

    return RunResult(
        framework="openai_agents",
        scenario=scenario["name"],
        budget_param="max_turns",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
        error=error_msg,
    )
