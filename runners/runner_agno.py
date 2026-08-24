"""
Agno (formerly Phidata) budget enforcement runner.

Budget primitive: max_iterations on Agent, Team-level budget across agents
What it counts: Each tool-use cycle as one iteration (similar to CrewAI)
Unique: Has TEAM-level budget that's shared across multiple agents.
When Agent A uses 2 iterations and Agent B uses 1, the team has consumed 3.
This is the only framework with a true shared budget pool across agents.

Also supports max_tokens as a cumulative output token budget.
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through Agno Agent with max_iterations."""
    try:
        from agno.agent import Agent
        from agno.models.openai import OpenAIChat
        from agno.tools import tool
    except ImportError as e:
        return RunResult(
            framework="agno",
            scenario=scenario["name"],
            budget_param="max_iterations",
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

    tools_list = []
    for td in scenario.get("tool_definitions", []):
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
        max_iterations=budget_value,
        show_tool_calls=False,
    )

    try:
        response = await agent.arun("Perform the requested task.")

        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        return RunResult(
            framework="agno",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by="completed" if response else "empty",
            metadata={
                "note": "Agno counts tool-use cycles as iterations. "
                       "Unique feature: Team-level shared budget pool across agents. "
                       "Agent A consuming iterations reduces Agent B's available budget.",
                "has_team_budget": True,
                "has_cumulative_token_budget": True,
            },
        )

    except Exception as e:
        return RunResult(
            framework="agno",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
