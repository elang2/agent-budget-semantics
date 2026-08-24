"""
LlamaIndex agent budget enforcement runner.

Budget primitive: max_iterations on .run() (v0.14.24+)
What it counts: Each LLM response (parse_agent_output calls)
Observed behavior (v0.14.24):
  num_iterations increments on EVERY parse_agent_output call, regardless of
  whether the response contains tool_calls or not. The counter fires BEFORE
  tool dispatch, so on the Nth iteration tools are never executed.
  budget=N → N LLM calls, N-1 tool executions (when all N responses have tools).
  Consumed = llm_calls (same semantics as OpenAI Agents SDK).
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through LlamaIndex ReActAgent with max_iterations."""
    try:
        from llama_index.core.agent.workflow import FunctionAgent
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
        model="gpt-4o",
        api_base=mock_url + "/v1",
        api_key="mock-key",
    )

    agent = FunctionAgent(
        tools=tools,
        llm=llm,
        streaming=False,
        early_stopping_method="force",
    )

    import httpx

    try:
        httpx.post(f"{mock_url}/reset")

        handler = agent.run(
            user_msg="Perform the requested task.",
            max_iterations=budget_value,
        )
        response = await handler

        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        return RunResult(
            framework="llamaindex",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by="completed" if response else "empty",
            metadata={
                "note": "LlamaIndex 0.14.24 counts each LLM response as 1 iteration "
                       "(same as OpenAI Agents). budget=N → N LLM calls, N-1 tool "
                       "executions. Counter fires before tool dispatch on Nth iteration.",
            },
        )

    except Exception as e:
        error_str = str(e)
        stopped_by = "budget_exceeded" if "max iterations" in error_str.lower() else "error"

        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger

        return RunResult(
            framework="llamaindex",
            scenario=scenario["name"],
            budget_param="max_iterations",
            budget_value=budget_value,
            actual_llm_calls=len(ledger_entries),
            actual_tool_calls=tool_calls_observed,
            stopped_by=stopped_by,
            error=f"{type(e).__name__}: {error_str[:200]}",
        )
