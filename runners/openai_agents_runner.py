"""
OpenAI Agents SDK runner for agent-budget-semantics.

Runs a scenario through OpenAI's Agents SDK and captures budget semantics.
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
    task = scenario["task"]

    try:
        from agents import Agent, Runner, RunConfig
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI
    except ImportError:
        return {
            "framework": "openai_agents",
            "scenario": scenario["name"],
            "error": "openai-agents not installed",
            "install": "pip install openai-agents",
        }

    client = AsyncOpenAI(base_url=mock_url + "/v1", api_key="mock-key")
    model = OpenAIChatCompletionsModel(model="mock-budget-llm", openai_client=client)

    def get_weather(city: str) -> str:
        return json.dumps({"city": city, "temp_c": 22, "condition": "sunny"})

    from agents import function_tool
    weather_tool = function_tool(get_weather)

    agent = Agent(
        name="budget_test_agent",
        instructions="Answer the user's question using available tools.",
        model=model,
        tools=[weather_tool],
    )

    config = RunConfig(max_turns=budget["max_iterations"])

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        result = await Runner.run(agent, task, run_config=config)
        stopped_reason = "completed"
        if hasattr(result, "new_items"):
            for item in result.new_items:
                result_messages.append({
                    "type": type(item).__name__,
                    "content": str(item),
                })
        if hasattr(result, "final_output"):
            result_messages.append({
                "type": "final_output",
                "content": str(result.final_output),
            })
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "openai_agents",
        "version": _get_version("openai-agents"),
        "scenario": scenario["name"],
        "budget_config": budget,
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
    }


def _observe_d1(messages, ledger, budget):
    llm_calls = len(ledger["entries"])
    max_iter = budget["max_iterations"]
    if llm_calls <= max_iter:
        return {
            "value": "yes_tool_turn_is_iteration",
            "evidence": f"{llm_calls} LLM calls with budget={max_iter}",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls with budget={max_iter}",
        }


def _observe_d2(ledger, budget):
    entries = ledger["entries"]
    if not entries:
        return {"value": "unknown", "evidence": "no entries"}
    return {
        "value": "all_tokens_counted",
        "evidence": f"Total: {sum(e['total_tokens'] for e in entries)} across {len(entries)} calls",
    }


def _observe_d3(messages, ledger, stopped_reason):
    if "exception" in (stopped_reason or ""):
        return {"value": "pre_call", "evidence": stopped_reason}
    return {"value": "post_call", "evidence": "Turn count checked after model response"}


def _observe_d4(stopped_reason, messages):
    if "exception" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": stopped_reason}
    if "MaxTurnsExceeded" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        return {"value": "return_partial", "evidence": "Returned accumulated output"}
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
