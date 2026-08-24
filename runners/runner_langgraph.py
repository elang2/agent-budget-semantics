"""
LangGraph budget enforcement runner.

Budget primitive: recursion_limit on graph.invoke() config
What it counts: Each node execution counts as one recursion step.
  For a typical ReAct agent: LLM node + tool node = 2 recursions per iteration.
  So recursion_limit=6 allows ~3 LLM+tool pairs.
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through LangGraph with recursion_limit budget."""
    try:
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
        from langchain_core.tools import tool as langchain_tool
        from langgraph.errors import GraphRecursionError
    except ImportError as e:
        return RunResult(
            framework="langgraph",
            scenario=scenario["name"],
            budget_param="recursion_limit",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    @langchain_tool
    def get_weather(city: str) -> str:
        """Get weather for a city."""
        nonlocal tool_calls_observed
        tool_calls_observed += 1
        return default_tool_handler("get_weather", json.dumps({"city": city}))

    @langchain_tool
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

    from langchain_core.callbacks import BaseCallbackHandler

    class LLMCounter(BaseCallbackHandler):
        def __init__(self):
            self.count = 0
        def on_llm_start(self, *args, **kwargs):
            self.count += 1

    counter = LLMCounter()

    llm = ChatOpenAI(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
        disable_streaming=True,
        callbacks=[counter],
    )

    graph = create_react_agent(llm, tools)

    stopped_by = "natural"

    try:
        result = await graph.ainvoke(
            {"messages": [("user", "Check the weather in various cities.")]},
            config={"recursion_limit": budget_value},
        )

    except GraphRecursionError:
        stopped_by = "budget"
    except Exception as e:
        error_msg = str(e)
        if "recursion" in error_msg.lower():
            stopped_by = "budget"
        else:
            return RunResult(
                framework="langgraph",
                scenario=scenario["name"],
                budget_param="recursion_limit",
                budget_value=budget_value,
                actual_llm_calls=counter.count,
                actual_tool_calls=tool_calls_observed,
                stopped_by="error",
                error=error_msg,
            )

    return RunResult(
        framework="langgraph",
        scenario=scenario["name"],
        budget_param="recursion_limit",
        budget_value=budget_value,
        actual_llm_calls=counter.count,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
