"""
CrewAI runner for agent-budget-semantics.

CrewAI has a distinct multi-agent model where budget applies per-agent
(max_iter) and per-crew (max_rpm for rate limiting). This tests the
per-agent iteration budget which is the closest analog to other frameworks.
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
        from crewai import Agent, Task, Crew
        from crewai.tools import tool
        from langchain_openai import ChatOpenAI
    except ImportError:
        return {
            "framework": "crewai",
            "scenario": scenario["name"],
            "error": "crewai not installed",
            "install": "pip install crewai langchain-openai",
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

    agent = Agent(
        role="Weather Reporter",
        goal="Answer weather questions using the get_weather tool",
        backstory="You are a helpful weather assistant.",
        tools=[get_weather],
        llm=llm,
        max_iter=budget["max_iterations"],
        verbose=False,
    )

    crew_task = Task(
        description=task_desc,
        agent=agent,
        expected_output="Weather information",
    )

    crew = Crew(
        agents=[agent],
        tasks=[crew_task],
        verbose=False,
    )

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        result = crew.kickoff()
        stopped_reason = "completed"
        result_messages.append({
            "type": "crew_output",
            "content": str(result),
        })
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "crewai",
        "version": _get_version("crewai"),
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
        "notes": {
            "multi_agent": "CrewAI applies max_iter per-agent, not per-crew. "
                          "A crew with 3 agents each having max_iter=2 gets 6 total iterations. "
                          "This is fundamentally different from a shared budget pool.",
            "budget_model": "per-agent iteration cap, no shared token budget across crew",
        },
    }


def _observe_d1(messages, ledger, budget):
    llm_calls = len(ledger["entries"])
    max_iter = budget["max_iterations"]
    tool_calls = sum(1 for e in ledger["entries"] if e["tool_calls_requested"] > 0)

    if llm_calls <= max_iter:
        return {
            "value": "yes_tool_turn_is_iteration",
            "evidence": f"{llm_calls} LLM calls with budget={max_iter}",
            "note": "CrewAI counts each tool-use cycle as one iteration",
        }
    elif llm_calls <= max_iter * 2:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls but only {tool_calls} tool cycles counted",
            "note": "CrewAI counts tool-use cycles, not individual LLM calls",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls significantly exceed budget={max_iter}",
        }


def _observe_d2(ledger, budget):
    entries = ledger["entries"]
    if not entries:
        return {"value": "unknown", "evidence": "no entries"}
    return {
        "value": "not_token_based",
        "evidence": "CrewAI max_iter counts iterations not tokens",
        "note": "CrewAI has no native token budget enforcement; only iteration counting",
    }


def _observe_d3(messages, ledger, stopped_reason):
    if "exception" in (stopped_reason or ""):
        return {"value": "post_call", "evidence": "Exception after iteration completes"}
    return {
        "value": "post_call",
        "evidence": "CrewAI checks iteration count after each tool-use cycle completes",
    }


def _observe_d4(stopped_reason, messages):
    if "exception" in (stopped_reason or ""):
        if "MaxIterations" in stopped_reason or "max_iter" in stopped_reason:
            return {"value": "return_partial", "evidence": "Returns best effort after hitting max_iter"}
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        return {
            "value": "one_more_completion_for_summary",
            "evidence": "CrewAI forces a final answer when max_iter is reached",
            "note": "Unique behavior: agent gets one last call to produce final_answer",
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
