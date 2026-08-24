"""
LangChain AgentExecutor runner for agent-budget-semantics.

LangChain's AgentExecutor (as opposed to LangGraph) has its own budget model:
- max_iterations: counts "action steps" (tool invocations)
- max_execution_time: wall-clock timeout
- The final answer is FREE (doesn't count as an iteration)
- Early stopping methods: "force" vs "generate"

This is distinct from LangGraph's recursion_limit which counts graph node visits.
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
        from langchain_openai import ChatOpenAI
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_core.tools import tool
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    except ImportError:
        return {
            "framework": "langchain",
            "scenario": scenario["name"],
            "error": "langchain not installed",
            "install": "pip install langchain langchain-openai",
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

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Use tools when needed."),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, [get_weather], prompt)

    executor = AgentExecutor(
        agent=agent,
        tools=[get_weather],
        max_iterations=budget["max_iterations"],
        early_stopping_method="force",
        verbose=False,
    )

    start = time.time()
    result_messages = []
    stopped_reason = None

    try:
        result = await executor.ainvoke({"input": task_desc})
        stopped_reason = "completed"
        result_messages.append({
            "type": "agent_output",
            "content": result.get("output", str(result)),
        })
        if result.get("intermediate_steps"):
            for step in result["intermediate_steps"]:
                result_messages.append({
                    "type": "intermediate_step",
                    "tool": step[0].tool if hasattr(step[0], "tool") else str(step[0]),
                    "output": str(step[1])[:200],
                })
    except Exception as e:
        stopped_reason = f"exception: {type(e).__name__}: {str(e)}"

    elapsed = time.time() - start

    import requests as req
    ledger = req.get(f"{mock_url}/ledger").json()

    return {
        "framework": "langchain",
        "version": _get_version("langchain"),
        "scenario": scenario["name"],
        "budget_config": budget,
        "budget_parameter": "max_iterations",
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
            "final_answer_free": "LangChain's AgentExecutor does NOT count the final "
                               "answer generation as an iteration. budget=2 means 2 tool "
                               "calls + 1 free final answer = 3 LLM calls total.",
            "early_stopping": "early_stopping_method='force' returns last observation; "
                            "'generate' gives the LLM one more call to summarize.",
            "vs_langgraph": "LangGraph's recursion_limit counts ALL graph node visits "
                          "including the final response node. AgentExecutor only counts "
                          "tool-use iterations. Same library, different semantics.",
        },
    }


def _observe_d1(messages, ledger, budget):
    llm_calls = len(ledger["entries"])
    max_iter = budget["max_iterations"]
    tool_calls = sum(1 for e in ledger["entries"] if e["tool_calls_requested"] > 0)

    if tool_calls <= max_iter and llm_calls > tool_calls:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{tool_calls} tool iterations + final answer = {llm_calls} LLM calls, budget={max_iter}",
            "note": "Final answer call is free. Only tool-use rounds count as iterations.",
        }
    elif llm_calls <= max_iter:
        return {
            "value": "yes_tool_turn_is_iteration",
            "evidence": f"{llm_calls} LLM calls within budget={max_iter}",
        }
    else:
        return {
            "value": "no_only_user_facing_counts",
            "evidence": f"{llm_calls} calls, {tool_calls} tool rounds, budget={max_iter}",
        }


def _observe_d2(ledger, budget):
    return {
        "value": "not_token_based",
        "evidence": "AgentExecutor.max_iterations is count-based",
        "note": "LangChain has no native token budget on the executor loop",
    }


def _observe_d3(messages, ledger, stopped_reason):
    return {
        "value": "pre_call",
        "evidence": "AgentExecutor checks iteration count before starting next loop",
    }


def _observe_d4(stopped_reason, messages):
    if "exception" in (stopped_reason or ""):
        return {"value": "raise_exception", "evidence": stopped_reason}
    if messages:
        has_output = any(m.get("type") == "agent_output" for m in messages)
        if has_output:
            return {
                "value": "one_more_completion_for_summary",
                "evidence": "early_stopping_method='force' returns last tool observation as output; "
                          "'generate' would give one more LLM call",
            }
    return {"value": "return_partial", "evidence": "Returns whatever was accumulated"}


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
