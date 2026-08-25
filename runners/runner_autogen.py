"""
AutoGen (v0.4+) budget enforcement runner.

Budget primitive: MaxMessageTermination(max_messages=N) on RoundRobinGroupChat
What it counts: TextMessage + ToolCallSummaryMessage (NOT individual events)

Observed behavior (v0.4.7):
  max_messages=N counts composite "messages": the initial user TextMessage (1)
  plus each ToolCallSummaryMessage (1 per agent turn, regardless of how many
  tools that turn executed). So budget=N allows N-1 agent turns.
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

    def get_weather(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

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

    model_client = OpenAIChatCompletionClient(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": False,
        },
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
    framework_message_count = 0

    try:
        result = await team.run(task="Check the weather in various cities.")

        for msg in result.messages:
            msg_type = type(msg).__name__
            if msg_type == "ToolCallRequestEvent":
                llm_calls += 1
            elif msg_type == "TextMessage":
                source = getattr(msg, "source", "")
                if source != "user":
                    llm_calls += 1

        text_msgs = sum(1 for m in result.messages if type(m).__name__ == "TextMessage")
        summary_msgs = sum(1 for m in result.messages if type(m).__name__ == "ToolCallSummaryMessage")
        framework_message_count = text_msgs + summary_msgs

        if hasattr(result, 'stop_reason') and result.stop_reason:
            if "maximum" in str(result.stop_reason).lower():
                stopped_by = "budget"

    except Exception as e:
        return RunResult(
            framework="autogen",
            scenario=scenario["name"],
            budget_param="max_messages",
            budget_value=budget_value,
            actual_llm_calls=llm_calls,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=str(e),
        )
    finally:
        if hasattr(model_client, 'close'):
            await model_client.close()

    return RunResult(
        framework="autogen",
        scenario=scenario["name"],
        budget_param="max_messages",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
        framework_iteration_count=framework_message_count,
    )
