"""
Google ADK budget enforcement runner.

Budget primitive: max_iterations on Runner or Agent config
What it counts: Each full agent loop iteration (LLM call + optional tool execution)
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through Google ADK with max_iterations budget."""
    try:
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types
    except ImportError as e:
        return RunResult(
            framework="adk",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    def get_weather(city: str) -> dict:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return json.loads(default_tool_handler("get_weather", json.dumps({"city": city})))

    def calculate(expression: str) -> dict:
        """Perform arithmetic."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return json.loads(default_tool_handler("calculate", json.dumps({"expression": expression})))

    tools = []
    for td in scenario.get("tool_definitions", []):
        if td["name"] == "get_weather":
            tools.append(get_weather)
        elif td["name"] == "calculate":
            tools.append(calculate)

    agent = Agent(
        name="budget_test_agent",
        model="mock-budget-llm",
        instruction="You are a helpful assistant. Use tools as needed.",
        tools=tools,
    )

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="budget_test",
        session_service=session_service,
    )

    llm_calls = 0
    stopped_by = "natural"

    try:
        session = await session_service.create_session(
            app_name="budget_test",
            user_id="test_user",
        )

        user_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text="Check the weather in various cities.")]
        )

        async for event in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=user_message,
            max_iterations=budget_value,
        ):
            if hasattr(event, 'content') and event.content:
                if event.content.role == "model":
                    llm_calls += 1

        if llm_calls >= budget_value:
            stopped_by = "budget"

    except Exception as e:
        error_msg = str(e)
        if "max_iterations" in error_msg.lower() or "iteration" in error_msg.lower():
            stopped_by = "budget"
        else:
            return RunResult(
                framework="adk",
                scenario=scenario["name"],
                budget_param="max_iterations",
                budget_value=budget_value,
                actual_llm_calls=llm_calls,
                actual_tool_calls=tool_calls_observed,
                stopped_by="error",
                error=error_msg,
            )

    return RunResult(
        framework="adk",
        scenario=scenario["name"],
        budget_param="max_iterations",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
