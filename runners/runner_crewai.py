"""
CrewAI budget enforcement runner.

Budget primitive: max_iter on Agent
What it counts: Each tool-use loop iteration. CrewAI counts each time the agent
  decides to use a tool and gets a result back as one iteration.
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through CrewAI with max_iter budget."""
    try:
        from crewai import Agent, Task, Crew
        from crewai.tools import tool as crewai_tool
        from crewai import LLM
    except ImportError as e:
        return RunResult(
            framework="crewai",
            scenario=scenario["name"],
            budget_param="max_iter",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    @crewai_tool
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    @crewai_tool
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

    llm = LLM(
        model="openai/mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    agent = Agent(
        role="Weather Checker",
        goal="Check weather in cities as requested",
        backstory="You are a helpful weather assistant.",
        tools=tools,
        llm=llm,
        max_iter=budget_value,
        verbose=False,
    )

    task = Task(
        description="Check the weather in various cities.",
        expected_output="Weather information",
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=False,
    )

    import httpx
    httpx.post(f"{mock_url}/reset")

    stopped_by = "natural"

    try:
        result = await asyncio.to_thread(crew.kickoff)

        if hasattr(result, 'raw') and "max iterations" in str(result.raw).lower():
            stopped_by = "budget"

    except Exception as e:
        error_msg = str(e)
        if "max_iter" in error_msg.lower() or "iteration" in error_msg.lower():
            stopped_by = "budget"
        else:
            ledger = httpx.get(f"{mock_url}/ledger").json()
            ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger
            return RunResult(
                framework="crewai",
                scenario=scenario["name"],
                budget_param="max_iter",
                budget_value=budget_value,
                actual_llm_calls=len(ledger_entries),
                actual_tool_calls=tool_calls_observed,
                stopped_by="error",
                error=error_msg,
            )

    ledger = httpx.get(f"{mock_url}/ledger").json()
    ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

    return RunResult(
        framework="crewai",
        scenario=scenario["name"],
        budget_param="max_iter",
        budget_value=budget_value,
        actual_llm_calls=len(ledger_entries),
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
