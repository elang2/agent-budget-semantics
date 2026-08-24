"""
Anthropic Claude runner for agent-budget-semantics.

Claude's tool use model is fundamentally different from OpenAI-compatible frameworks:
- No native "max_iterations" on the API level
- max_tokens caps OUTPUT tokens per individual response (not cumulative)
- Iteration budget is entirely client-side (the caller decides when to stop)
- The Anthropic Python SDK's tool-use loop has no built-in budget

This runner tests what happens when we implement a client-side iteration budget
on top of Claude's tool use, exposing how the absence of server-side budget
enforcement creates a different telemetry profile.
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
        from anthropic import AsyncAnthropic
    except ImportError:
        return {
            "framework": "anthropic",
            "scenario": scenario["name"],
            "error": "anthropic not installed",
            "install": "pip install anthropic",
        }

    client = AsyncAnthropic(
        base_url=mock_url,
        api_key="mock-key",
    )

    tools = [
        {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]

    max_iterations = budget["max_iterations"]
    messages = [{"role": "user", "content": task_desc}]

    start = time.time()
    result_messages = []
    stopped_reason = None
    iterations_used = 0

    try:
        while iterations_used < max_iterations:
            response = await client.messages.create(
                model="mock-budget-llm",
                max_tokens=1024,
                messages=messages,
                tools=tools,
            )

            iterations_used += 1
            result_messages.append({
                "type": "assistant_response",
                "stop_reason": response.stop_reason,
                "content_blocks": len(response.content),
            })

            if response.stop_reason == "end_turn":
                stopped_reason = "completed"
                break
            elif response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"city": "Tokyo", "temp_c": 22, "condition": "sunny"}),
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                stopped_reason = f"unexpected_stop_reason: {response.stop_reason}"
                break
        else:
            stopped_reason = "budget_exhausted"

    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "anthropic",
        "version": _get_version("anthropic"),
        "scenario": scenario["name"],
        "budget_config": budget,
        "budget_parameter": "client_side_max_iterations",
        "elapsed_seconds": round(elapsed, 3),
        "iterations_used": iterations_used,
        "messages_produced": len(result_messages),
        "messages": result_messages,
        "stopped_reason": stopped_reason,
        "llm_calls_made": len(ledger["entries"]),
        "total_prompt_tokens": sum(e["prompt_tokens"] for e in ledger["entries"]),
        "total_completion_tokens": sum(e["completion_tokens"] for e in ledger["entries"]),
        "total_tokens": sum(e["total_tokens"] for e in ledger["entries"]),
        "ledger": ledger["entries"],
        "observations": {
            "D1_iteration_unit": _observe_d1(result_messages, ledger, budget, iterations_used),
            "D2_token_accounting": _observe_d2(ledger, budget),
            "D3_enforcement_point": _observe_d3(result_messages, ledger, stopped_reason),
            "D4_exhaustion_behavior": _observe_d4(stopped_reason, result_messages),
        },
        "notes": {
            "no_server_budget": "Anthropic API has no server-side iteration budget. "
                              "All budget enforcement is client-side. This means OTel "
                              "telemetry for Claude tool use MUST come from the client "
                              "library, not the API response.",
            "max_tokens_semantics": "max_tokens in Claude = output cap per call. "
                                  "It's NOT cumulative across the tool-use loop. "
                                  "A 4096 max_tokens budget means each individual response "
                                  "can use up to 4096 tokens, and the loop runs indefinitely.",
            "implication_for_otel": "gen_ai.agent.iteration_budget.limit is purely synthetic "
                                  "for Claude. The instrumenting library defines what counts "
                                  "as an iteration, not the model provider.",
        },
    }


def _observe_d1(messages, ledger, budget, iterations_used):
    llm_calls = len(ledger["entries"])
    return {
        "value": "client_defined",
        "evidence": f"Client loop ran {iterations_used} iterations = {llm_calls} LLM calls",
        "note": "No server-side concept of iteration. Each API call = 1 iteration in our loop. "
               "Tool-call responses count as iterations because we chose to count them that way.",
    }


def _observe_d2(ledger, budget):
    entries = ledger["entries"]
    if not entries:
        return {"value": "unknown", "evidence": "no entries"}
    return {
        "value": "client_must_implement",
        "evidence": "Anthropic API reports usage per call but doesn't enforce cumulative limits",
        "note": "Token budget enforcement is 100% client responsibility. The API will happily "
               "serve requests indefinitely as long as rate limits aren't hit.",
    }


def _observe_d3(messages, ledger, stopped_reason):
    return {
        "value": "client_pre_call",
        "evidence": "Our loop checks budget before making the next API call",
        "note": "This is our design choice, not Claude's. A different client could check "
               "post-call or not at all.",
    }


def _observe_d4(stopped_reason, messages):
    if stopped_reason == "budget_exhausted":
        return {
            "value": "hard_stop_no_output",
            "evidence": "Client loop stops; last response may have been a tool_use with no final answer",
            "note": "Unlike frameworks that force a final answer, a naive client-side budget "
                   "just stops the loop. The agent never gets to summarize.",
        }
    if stopped_reason == "completed":
        return {"value": "return_partial", "evidence": "Completed naturally within budget"}
    return {"value": "raise_exception", "evidence": stopped_reason}


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
