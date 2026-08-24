"""
AutoGen (v0.4+) budget enforcement runner.

Budget primitive: max_turns on AgentChat.run() / run_stream()
What it counts: Each LLM response OR tool result message counts as one "turn"
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through AutoGen with max_turns budget."""
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.teams import RoundRobinGroupChat
        from autogen_agentchat.conditions import MaxMessageTermination
        from autogen_ext.models.openai import OpenAIChatCompletionClient
    except ImportError as e:
        return RunResult(
            framework="autogen",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    def weather_tool(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    def calculate_tool(expression: str) -> str:
        """Perform arithmetic."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("calculate", json.dumps({"expression": expression}))

    tools = []
    for td in scenario.get("tool_definitions", []):
        if td["name"] == "get_weather":
            tools.append(weather_tool)
        elif td["name"] == "calculate":
            tools.append(calculate_tool)

    model_client = OpenAIChatCompletionClient(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    agent = AssistantAgent(
        name="budget_test_agent",
        model_client=model_client,
        tools=tools,
        system_message="You are a helpful assistant. Use tools as needed.",
    )

    termination = MaxMessageTermination(max_messages=budget_value)
    team = RoundRobinGroupChat(
        participants=[agent],
        termination_condition=termination,
    )

    llm_calls = 0
    stopped_by = "natural"

    try:
        result = await team.run(task="Check the weather in various cities.")

        for msg in result.messages:
            msg_type = type(msg).__name__
            if msg_type in ("AssistantMessage", "ModelClientStreamingChunkEvent"):
                llm_calls += 1

        if hasattr(result, 'stop_reason') and result.stop_reason:
            if "maximum" in str(result.stop_reason).lower():
                stopped_by = "budget"

    except Exception as e:
        return RunResult(
            framework="autogen",
            scenario=scenario["name"],
            budget_param="max_turns",
            budget_value=budget_value,
            actual_llm_calls=llm_calls,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=str(e),
        )
    finally:
        await model_client.close()

    return RunResult(
        framework="autogen",
        scenario=scenario["name"],
        budget_param="max_turns",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
