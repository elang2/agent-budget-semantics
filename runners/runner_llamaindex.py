"""
LlamaIndex agent budget enforcement runner.

Budget primitive: max_iterations on AgentRunner/ReActAgent
What it counts: Each reasoning step (thought + action + observation = 1 iteration)
Unique: Has early_stopping_method='generate' that gives one extra LLM call to
summarize when budget is hit. Same concept as LangChain's AgentExecutor but
with a different default behavior.

Also has max_function_calls as a separate budget for total tool invocations
across all iterations (parallel tool calls in one step count individually).
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through LlamaIndex ReActAgent with max_iterations."""
    try:
        from llama_index.core.agent import ReActAgent
        from llama_index.core.tools import FunctionTool
        from llama_index.llms.openai import OpenAI as LlamaOpenAI
    except ImportError as e:
        return RunResult(
            framework="llamaindex",
            scenario=scenario["name"],
            budget_param="max_iterations",
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
            tools.append(FunctionTool.from_defaults(fn=get_weather))
        elif td["name"] == "calculate":
            tools.append(FunctionTool.from_defaults(fn=calculate))

    llm = LlamaOpenAI(
        model="mock-budget-llm",
        api_base=mock_url + "/v1",
        api_key="mock-key",
    )

    agent = ReActAgent.from_tools(
        tools=tools,
        llm=llm,
        max_iterations=budget_value,
        verbose=False,
    )

    try:
        response = await agent.achat("Perform the requested task.")

        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        return RunResult(
            framework="llamaindex",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by="completed" if str(response) else "empty",
            metadata={
                "note": "LlamaIndex ReAct counts thought+action+observation as 1 iteration. "
                       "The Thought LLM call and Action execution are part of the same step. "
                       "Different from LangGraph where each is a separate node visit.",
                "has_max_function_calls": True,
            },
        )

    except Exception as e:
        return RunResult(
            framework="llamaindex",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
