"""
LangChain AgentExecutor budget enforcement runner.

Budget primitive: max_iterations on AgentExecutor
What it counts: Each iteration = one LLM call that results in an AgentAction (tool call).
  A final LLM call that produces AgentFinish does NOT count as an iteration.
"""

import asyncio
import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through LangChain AgentExecutor with max_iterations budget."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from langchain_core.tools import tool as langchain_tool
    except ImportError as e:
        return RunResult(
            framework="langchain",
            scenario=scenario["name"],
            budget_param="max_iterations",
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

    llm = ChatOpenAI(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Use tools as needed."),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=budget_value,
        verbose=False,
    )

    llm_calls = 0
    stopped_by = "natural"

    try:
        result = await executor.ainvoke({"input": "Check the weather in various cities."})

        if isinstance(result, dict) and result.get("output", "").startswith("Agent stopped"):
            stopped_by = "budget"

    except Exception as e:
        error_msg = str(e)
        if "iteration" in error_msg.lower() or "max" in error_msg.lower():
            stopped_by = "budget"
        else:
            return RunResult(
                framework="langchain",
                scenario=scenario["name"],
                budget_param="max_iterations",
                budget_value=budget_value,
                actual_llm_calls=llm_calls,
                actual_tool_calls=tool_calls_observed,
                stopped_by="error",
                error=error_msg,
            )

    return RunResult(
        framework="langchain",
        scenario=scenario["name"],
        budget_param="max_iterations",
        budget_value=budget_value,
        actual_llm_calls=llm_calls,
        actual_tool_calls=tool_calls_observed,
        stopped_by=stopped_by,
    )
