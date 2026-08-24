"""
LangGraph runner for agent-budget-semantics.

Runs a scenario through LangGraph's ReAct agent and captures budget semantics.
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
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent
        from langchain_core.tools import tool
    except ImportError:
        return {
            "framework": "langgraph",
            "scenario": scenario["name"],
            "error": "langgraph not installed",
            "install": "pip install langgraph langchain-openai",
        }

    llm = ChatOpenAI(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    @tool
    def get_weather(city: str) -> str:
        """Get current weather for a city."""
        return json.dumps({"city": city, "temp_c": 22, "condition": "sunny"})

    agent = create_react_agent(
        llm,
        tools=[get_weather],
        recursion_limit=budget["max_iterations"],
    )

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]},
        )
        stopped_reason = "completed"
        for msg in result.get("messages", []):
            result_messages.append({
                "type": type(msg).__name__,
                "content": str(msg.content) if hasattr(msg, "content") else str(msg),
                "role": getattr(msg, "type", "unknown"),
            })
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "langgraph",
        "version": _get_version("langgraph"),
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
    if "GraphRecursionError" in (stopped_reason or ""):
        return {"value": "pre_call", "evidence": "GraphRecursionError raised before next step"}
    if "exception" in (stopped_reason or ""):
        return {"value": "pre_call", "evidence": stopped_reason}
    return {"value": "post_call", "evidence": "Graph completed within recursion limit"}


def _observe_d4(stopped_reason, messages):
    if "GraphRecursionError" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": "GraphRecursionError"}
    if "exception" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        return {"value": "return_partial", "evidence": "Returned message history"}
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
