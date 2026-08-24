"""
Google ADK runner for agent-budget-semantics.

Runs a scenario through Google's Agent Development Kit and captures:
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


async def run_scenario(scenario_path: str, mock_url: str = "http://127.0.0.1:9111"):
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    budget = scenario["budget"]
    task = scenario["task"]
    tools_spec = scenario["tools"]

    try:
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types
        import google.genai as genai
    except ImportError:
        return {
            "framework": "google_adk",
            "scenario": scenario["name"],
            "error": "google-adk not installed",
            "install": "pip install google-adk",
        }

    client = genai.Client(
        api_key="mock-key",
        http_options=types.HttpOptions(base_url=mock_url),
    )

    def get_weather(city: str) -> dict:
        return {"city": city, "temp_c": 22, "condition": "sunny"}

    agent = Agent(
        name="budget_test_agent",
        model="mock-budget-llm",
        description="Test agent for budget semantics",
        instruction="Answer the user's question using available tools.",
        tools=[get_weather],
        max_iterations=budget["max_iterations"],
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="budget_test", user_id="test_user"
    )

    runner = Runner(
        agent=agent,
        app_name="budget_test",
        session_service=session_service,
    )

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        user_msg = types.Content(
            role="user", parts=[types.Part.from_text(task)]
        )

        async for event in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=user_msg,
        ):
            if event.content:
                result_messages.append({
                    "author": event.author,
                    "content": str(event.content),
                    "type": type(event).__name__,
                })
        stopped_reason = "completed"
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests
    ledger = requests.get(f"{mock_url}/ledger").json()

    return {
        "framework": "google_adk",
        "version": _get_version("google-adk"),
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
            "evidence": f"Only {llm_calls} LLM calls made with budget={max_iter}",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} LLM calls with budget={max_iter}, tool turns free",
        }


def _observe_d2(ledger, budget):
    entries = ledger["entries"]
    if not entries:
        return {"value": "unknown", "evidence": "no entries"}
    return {
        "value": "needs_investigation",
        "evidence": f"Total: {sum(e['total_tokens'] for e in entries)} tokens across {len(entries)} calls",
        "note": "ADK token budget enforcement behavior varies by version",
    }


def _observe_d3(messages, ledger, stopped_reason):
    if "exception" in stopped_reason:
        return {"value": "pre_call", "evidence": stopped_reason}
    return {
        "value": "post_call",
        "evidence": "Iteration check happens after agent loop step",
    }


def _observe_d4(stopped_reason, messages):
    if "exception" in stopped_reason:
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        return {"value": "return_partial", "evidence": "Last message returned before stop"}
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
