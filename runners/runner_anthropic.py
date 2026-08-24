"""
Anthropic Claude budget enforcement runner.

Budget primitive: NONE (client-side only)
What it counts: Client implements iteration loop; each API call = 1 iteration
Unique: No server-side budget. max_tokens caps output per call, not cumulative.

This runner demonstrates that for Claude tool use, ALL budget enforcement is
client-side. The OTel gen_ai.agent.iteration_budget.limit attribute is purely
synthetic for Anthropic's API.
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario with client-side iteration budget on Anthropic API."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        return RunResult(
            framework="anthropic",
            scenario=scenario["name"],
            budget_param="client_max_iterations",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    client = AsyncAnthropic(base_url=mock_url, api_key="mock-key")
    tool_calls_observed = 0
    llm_calls = 0

    tools = [
        {
            "name": "get_weather",
            "description": "Get weather for a city",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
        {
            "name": "calculate",
            "description": "Perform arithmetic",
            "input_schema": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    ]

    messages = [{"role": "user", "content": "Perform the requested task."}]
    iterations = 0

    try:
        while iterations < budget_value:
            response = await client.messages.create(
                model="mock-budget-llm",
                max_tokens=1024,
                messages=messages,
                tools=tools,
            )
            llm_calls += 1
            iterations += 1

            if response.stop_reason == "end_turn":
                return RunResult(
                    framework="anthropic",
                    scenario=scenario["name"],
                    budget_param="client_max_iterations",
                    budget_value=budget_value,
                    actual_llm_calls=llm_calls,
                    actual_tool_calls=tool_calls_observed,
                    stopped_by="natural_end",
                    metadata={"iterations_used": iterations},
                )

            elif response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_calls_observed += 1
                        result_text = default_tool_handler(block.name, json.dumps(block.input))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        return RunResult(
            framework="anthropic",
            scenario=scenario["name"],
            budget_param="client_max_iterations",
            budget_value=budget_value,
            actual_llm_calls=llm_calls,
            actual_tool_calls=tool_calls_observed,
            stopped_by="budget_exhausted",
            metadata={
                "note": "Client loop stopped. No server-side enforcement exists. "
                       "Agent may have pending tool calls that will never be fulfilled.",
            },
        )

    except Exception as e:
        return RunResult(
            framework="anthropic",
            scenario=scenario["name"],
            budget_param="client_max_iterations",
            budget_value=budget_value,
            actual_llm_calls=llm_calls,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
