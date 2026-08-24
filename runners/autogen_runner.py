"""
AutoGen runner for agent-budget-semantics.

Runs a scenario through Microsoft AutoGen and captures:
- How many iterations it counts
- Where it enforces the budget
- What happens at exhaustion
- Token accounting method
"""

import json
import sys
import time
import asyncio
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from mock_llm_client import MockLLMClient


async def run_scenario(scenario_path: str, mock_url: str = "http://127.0.0.1:9111"):
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    budget = scenario["budget"]
    task = scenario["task"]
    tools = scenario["tools"]

    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.conditions import MaxMessageTermination
        from autogen_agentchat.teams import RoundRobinGroupChat
        from autogen_ext.models.openai import OpenAIChatCompletionClient
    except ImportError:
        return {
            "framework": "autogen",
            "scenario": scenario["name"],
            "error": "autogen not installed",
            "install": "pip install autogen-agentchat autogen-ext[openai]",
        }

    model_client = OpenAIChatCompletionClient(
        model="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )

    def get_weather(city: str) -> str:
        return json.dumps({"city": city, "temp_c": 22, "condition": "sunny"})

    agent = AssistantAgent(
        name="budget_test_agent",
        model_client=model_client,
        tools=[get_weather],
    )

    termination = MaxMessageTermination(max_messages=budget["max_iterations"])

    team = RoundRobinGroupChat(
        participants=[agent],
        termination_condition=termination,
    )

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        async for msg in team.run_stream(task=task):
            if hasattr(msg, "source"):
                result_messages.append({
                    "source": msg.source if hasattr(msg, "source") else "unknown",
                    "content": str(msg.content) if hasattr(msg, "content") else str(msg),
                    "type": type(msg).__name__,
                })
        stopped_reason = "completed"
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests
    ledger = requests.get(f"{mock_url}/ledger").json()

    return {
        "framework": "autogen",
        "version": _get_version("autogen-agentchat"),
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
    tool_calls_in_ledger = sum(1 for e in ledger["entries"] if e["tool_calls_requested"] > 0)

    if llm_calls <= max_iter:
        return {
            "value": "yes_tool_turn_is_iteration",
            "evidence": f"Only {llm_calls} LLM calls made with budget={max_iter}, tool turns consumed iterations",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls made with budget={max_iter}, tool turns did not count",
        }


def _observe_d2(ledger, budget):
    entries = ledger["entries"]
    if not entries:
        return {"value": "unknown", "evidence": "no ledger entries"}
    return {
        "value": "all_tokens_counted",
        "evidence": f"Total tokens across {len(entries)} calls: {sum(e['total_tokens'] for e in entries)}",
        "note": "AutoGen counts all tokens by default; need to check if budget enforcement uses this",
    }


def _observe_d3(messages, ledger, stopped_reason):
    if "exception" in stopped_reason:
        return {"value": "pre_call", "evidence": "Exception raised, likely pre-call check"}
    return {
        "value": "post_call",
        "evidence": "Agent completed or terminated after message count check",
        "note": "MaxMessageTermination checks after each message is produced",
    }


def _observe_d4(stopped_reason, messages):
    if "exception" in stopped_reason:
        return {"value": "raise_exception", "evidence": stopped_reason}
    elif messages and "completed" in stopped_reason:
        last = messages[-1] if messages else None
        if last and last.get("content"):
            return {"value": "return_partial", "evidence": "Agent returned last message content"}
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
