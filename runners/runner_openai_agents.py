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

    except Exception as e:
        error_msg = str(e)
        if "max turns" in error_msg.lower() or "exceeded" in error_msg.lower():
            stopped_by = "budget"
            llm_calls = budget_value
        else:
            return RunResult(
                framework="openai_agents",
                scenario=scenario["name"],
                budget_param="max_turns",
                budget_value=budget_value,
                actual_llm_calls=llm_calls,
                actual_tool_calls=tool_calls_observed,
                stopped_by="error",
                error=error_msg,
            )

    return RunResult(
        framework="openai_agents",
        scenario=scenario["name"],
        budget_param="max_turns",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
