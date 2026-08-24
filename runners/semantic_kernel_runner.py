"""
Semantic Kernel runner for agent-budget-semantics.

Microsoft's Semantic Kernel has a unique budget model:
- FunctionChoiceBehavior with max_auto_invoke_attempts
- Token budget via PromptExecutionSettings.max_tokens (output cap only)
- No native iteration budget on the agent loop itself (prior to agents framework)
- SK Agents (newer) has termination strategies

This tests FunctionChoiceBehavior.auto() with max_auto_invoke_attempts
which is the closest to other frameworks' iteration budget.
"""

import json
import sys
import time
import asyncio
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


async def run_scenario(scenario_path: str, mock_url: str = "http://127.0.0.1:9111"):
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    budget = scenario["budget"]
    task_desc = scenario["task"]

    try:
        from semantic_kernel import Kernel
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
        from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
        from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_chat_prompt_execution_settings import OpenAIChatPromptExecutionSettings
        from semantic_kernel.contents.chat_history import ChatHistory
        from semantic_kernel.functions import kernel_function
    except ImportError:
        return {
            "framework": "semantic_kernel",
            "scenario": scenario["name"],
            "error": "semantic-kernel not installed",
            "install": "pip install semantic-kernel",
        }

    kernel = Kernel()

    service = OpenAIChatCompletion(
        service_id="mock",
        ai_model_id="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )
    kernel.add_service(service)

    class WeatherPlugin:
        @kernel_function(name="get_weather", description="Get current weather for a city")
        def get_weather(self, city: str) -> str:
            return json.dumps({"city": city, "temp_c": 22, "condition": "sunny"})

    kernel.add_plugin(WeatherPlugin(), plugin_name="weather")

    settings = OpenAIChatPromptExecutionSettings(
        service_id="mock",
        function_choice_behavior=FunctionChoiceBehavior.Auto(
            maximum_auto_invoke_attempts=budget["max_iterations"]
        ),
    )

    history = ChatHistory()
    history.add_user_message(task_desc)

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        result = await kernel.invoke_prompt(
            prompt=task_desc,
            settings=settings,
        )
        stopped_reason = "completed"
        result_messages.append({
            "type": "kernel_result",
            "content": str(result),
        })
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "semantic_kernel",
        "version": _get_version("semantic-kernel"),
        "scenario": scenario["name"],
        "budget_config": budget,
        "budget_parameter": "maximum_auto_invoke_attempts",
        "elapsed_seconds": round(elapsed, 3),
        "messages_produced": len(result_messages),
        "messages": result_messages,
        "stopped_reason": stopped_reason,
        "llm_calls_made": len(ledger["entries"]),
        "total_prompt_tokens": sum(e["prompt_tokens"] for e in ledger["entries"]),
        "total_completion_tokens": sum(e["completion_tokens"] for e in ledger["entries"]),
        "total_tokens": sum(e["total_tokens"] for e in ledger["entries"]),
        "ledger": ledger["entries"],
        "observations": {
            "D1_iteration_unit": _observe_d1(result_messages, ledger, budget),
            "D2_token_accounting": _observe_d2(ledger, budget),
            "D3_enforcement_point": _observe_d3(result_messages, ledger, stopped_reason),
            "D4_exhaustion_behavior": _observe_d4(stopped_reason, result_messages),
        },
        "notes": {
            "budget_model": "SK uses 'auto invoke attempts' not 'iterations'. "
                          "Each attempt = one round of tool calling. If the LLM requests "
                          "3 parallel tool calls, that's still 1 attempt. Fundamentally "
                          "different from frameworks that count individual tool calls.",
            "parallel_tools": "SK handles parallel tool calls in a single attempt, "
                            "making budget=2 more generous than AutoGen's budget=2",
            "token_budget": "SK has no native token budget on the loop. max_tokens in "
                          "settings caps OUTPUT tokens per call, not cumulative usage.",
        },
    }


def _observe_d1(messages, ledger, budget):
    llm_calls = len(ledger["entries"])
    max_iter = budget["max_iterations"]
    tool_calls = sum(1 for e in ledger["entries"] if e["tool_calls_requested"] > 0)

    if tool_calls <= max_iter and llm_calls > max_iter:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls, {tool_calls} tool-call rounds, budget={max_iter}",
            "note": "SK counts 'auto invoke attempts' (tool-call rounds), not LLM calls. "
                   "The final non-tool LLM call doesn't count against the budget.",
        }
    elif llm_calls <= max_iter:
        return {
            "value": "yes_tool_turn_is_iteration",
            "evidence": f"{llm_calls} LLM calls within budget={max_iter}",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls exceed budget={max_iter}",
        }


def _observe_d2(ledger, budget):
    return {
        "value": "not_token_based",
        "evidence": "SK maximum_auto_invoke_attempts is count-based, not token-based",
        "note": "No cumulative token budget exists in SK's auto-invoke loop",
    }


def _observe_d3(messages, ledger, stopped_reason):
    return {
        "value": "pre_call",
        "evidence": "SK checks attempt count BEFORE making the next auto-invoke call",
        "note": "If attempts exhausted, SK returns last LLM response as-is (may contain "
               "unfulfilled tool_calls that get stripped)",
    }


def _observe_d4(stopped_reason, messages):
    if "exception" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        return {
            "value": "return_partial",
            "evidence": "SK returns the last LLM response when attempts exhausted",
            "note": "Unique: if last response had tool_calls, they're silently dropped. "
                   "The user gets whatever content the LLM produced alongside the tool request.",
        }
    return {"value": "hard_stop_no_output", "evidence": stopped_reason}


def _get_version(package: str) -> str:
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return "unknown"


if __name__ == "__main__":
    scenario_path = sys.argv[1] if len(sys.argv) > 1 else "scenarios/S2-tool-turn.yaml"
    mock_url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9111"
    result = asyncio.run(run_scenario(scenario_path, mock_url))
    print(json.dumps(result, indent=2))
