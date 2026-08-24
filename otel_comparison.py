"""
OTel Budget Telemetry Comparison

Shows what each framework WOULD report for the same execution using
proposed OTel GenAI semantic conventions from PR #439.

This is the key evidence: same scenario, same mock LLM, same tokens consumed,
but each framework would emit different values for the same OTel attributes.

Proposed attributes (from open-telemetry/semantic-conventions-genai#439):
  gen_ai.agent.iteration_budget.limit    - configured maximum iterations
  gen_ai.agent.iteration_budget.consumed - iterations used
  gen_ai.agent.token_budget.limit        - configured maximum tokens
  gen_ai.agent.token_budget.consumed     - tokens used
  gen_ai.invoke_agent.token_budget.utilization - ratio (consumed/limit)
"""

import json
from pathlib import Path


FRAMEWORK_BUDGET_SEMANTICS = {
    "autogen": {
        "budget_param": "max_turns",
        "iteration_definition": "Each message (LLM response OR tool result) in the group chat",
        "what_counts": "assistant_message + tool_result_message",
        "parallel_tools": "Each tool result is a separate message = separate turn",
        "final_answer": "Counts as a turn",
        "token_budget": "Not natively enforced (callback-based)",
    },
    "openai_agents": {
        "budget_param": "max_turns",
        "iteration_definition": "Each full LLM invocation",
        "what_counts": "LLM API calls only (tool execution is transparent)",
        "parallel_tools": "Multiple parallel tool calls = 1 turn (1 LLM response)",
        "final_answer": "Counts as a turn",
        "token_budget": "Not enforced",
    },
    "langchain": {
        "budget_param": "max_iterations",
        "iteration_definition": "Each tool-use cycle (action + observation)",
        "what_counts": "Tool invocations only; final answer is FREE",
        "parallel_tools": "Batch of parallel tools = 1 iteration",
        "final_answer": "Does NOT count (free extra call)",
        "token_budget": "Not natively enforced (per-call max_tokens only)",
    },
    "langgraph": {
        "budget_param": "recursion_limit",
        "iteration_definition": "Each graph node execution",
        "what_counts": "Node visits (agent node + tool node = 2 per iteration)",
        "parallel_tools": "Tool node processes all parallel calls as 1 visit",
        "final_answer": "Counts as a node visit",
        "token_budget": "Not enforced",
    },
    "crewai": {
        "budget_param": "max_iter",
        "iteration_definition": "Each tool-use cycle",
        "what_counts": "Tool-use cycles; retries are FREE",
        "parallel_tools": "N/A (CrewAI doesn't support parallel tool calls)",
        "final_answer": "Gets one forced extra call to produce final_answer",
        "token_budget": "Not enforced (max_rpm is rate limit, not budget)",
    },
    "adk": {
        "budget_param": "max_iterations",
        "iteration_definition": "Each full agent loop (plan + act + observe)",
        "what_counts": "Complete agent loops",
        "parallel_tools": "Multiple tools in one loop = 1 iteration",
        "final_answer": "Part of the last iteration",
        "token_budget": "Configurable via callbacks",
    },
    "semantic_kernel": {
        "budget_param": "maximum_auto_invoke_attempts",
        "iteration_definition": "Each auto-invoke round",
        "what_counts": "Rounds where tools were auto-invoked (not the LLM calls themselves)",
        "parallel_tools": "N parallel tools = 1 attempt (batch is atomic)",
        "final_answer": "Not counted (only tool-invoking rounds count)",
        "token_budget": "max_tokens per call only (not cumulative)",
    },
    "anthropic": {
        "budget_param": "NONE (client-side only)",
        "iteration_definition": "Client-defined (no server concept)",
        "what_counts": "Whatever the client library decides",
        "parallel_tools": "Client decides",
        "final_answer": "Client decides",
        "token_budget": "max_tokens per response (not cumulative, not enforced across loop)",
    },
    "swarm": {
        "budget_param": "max_turns",
        "iteration_definition": "Messages added to history since start",
        "what_counts": "ALL messages: assistant + tool_result + user (tool call = 2 messages)",
        "parallel_tools": "Each tool result is a separate message in history",
        "final_answer": "Counts as a message",
        "token_budget": "Not enforced",
    },
    "llamaindex": {
        "budget_param": "max_iterations",
        "iteration_definition": "Each ReAct step (Thought + Action + Observation)",
        "what_counts": "Complete reasoning steps; partial steps don't count",
        "parallel_tools": "Counted individually via max_function_calls (separate budget!)",
        "final_answer": "Gets one extra call via early_stopping_method='generate'",
        "token_budget": "Not enforced natively",
    },
    "agno": {
        "budget_param": "max_iterations",
        "iteration_definition": "Each tool-use cycle",
        "what_counts": "Tool-use cycles at agent level; TEAM has separate shared pool",
        "parallel_tools": "Batch = 1 iteration",
        "final_answer": "Part of normal flow",
        "token_budget": "Cumulative output token budget (unique feature)",
    },
}


def simulate_otel_attributes(scenario_name: str, llm_calls: int, tool_calls: int,
                              total_tokens: int, budget_limit: int) -> dict:
    """
    Given ground truth from the mock LLM ledger, show what each framework
    would report for OTel budget attributes.
    """
    results = {}

    for fw, semantics in FRAMEWORK_BUDGET_SEMANTICS.items():
        consumed = _calculate_consumed(fw, llm_calls, tool_calls)
        utilization = consumed / budget_limit if budget_limit > 0 else 0

        results[fw] = {
            "gen_ai.agent.iteration_budget.limit": budget_limit,
            "gen_ai.agent.iteration_budget.consumed": consumed,
            "gen_ai.agent.token_budget.limit": None,
            "gen_ai.agent.token_budget.consumed": total_tokens,
            "gen_ai.invoke_agent.token_budget.utilization": round(utilization, 3),
            "budget_param_name": semantics["budget_param"],
            "counting_method": semantics["iteration_definition"],
        }

    return results


def _calculate_consumed(framework: str, llm_calls: int, tool_calls: int) -> int:
    """Estimate what each framework would report as iterations consumed."""
    if framework == "autogen":
        return llm_calls + tool_calls
    elif framework == "openai_agents":
        return llm_calls
    elif framework == "langchain":
        return tool_calls
    elif framework == "langgraph":
        return llm_calls + tool_calls
    elif framework == "crewai":
        return tool_calls
    elif framework == "adk":
        return tool_calls
    elif framework == "semantic_kernel":
        return tool_calls
    elif framework == "anthropic":
        return llm_calls
    elif framework == "swarm":
        return llm_calls + (tool_calls * 2)
    elif framework == "llamaindex":
        return tool_calls
    elif framework == "agno":
        return tool_calls
    return llm_calls


def print_comparison(scenario: str = "S2", budget_limit: int = 3,
                     llm_calls: int = 4, tool_calls: int = 3, total_tokens: int = 478):
    """Print the divergence table for a scenario."""
    results = simulate_otel_attributes(scenario, llm_calls, tool_calls, total_tokens, budget_limit)

    print(f"\nOTel Budget Telemetry Comparison — Scenario: {scenario}")
    print(f"Ground truth: {llm_calls} LLM calls, {tool_calls} tool calls, {total_tokens} tokens")
    print(f"Budget limit: {budget_limit}")
    print(f"\n{'Framework':<18} {'consumed':<10} {'utilization':<13} {'Counting method'}")
    print("-" * 80)

    consumed_values = set()
    for fw, attrs in results.items():
        consumed = attrs["gen_ai.agent.iteration_budget.consumed"]
        util = attrs["gen_ai.invoke_agent.token_budget.utilization"]
        method = FRAMEWORK_BUDGET_SEMANTICS[fw]["iteration_definition"][:40]
        consumed_values.add(consumed)
        exceeded = " !! EXCEEDED" if consumed > budget_limit else ""
        print(f"{fw:<18} {consumed:<10} {util:<13.1%} {method}{exceeded}")

    print(f"\nUnique 'consumed' values: {sorted(consumed_values)}")
    print(f"Disagreement factor: {len(consumed_values)} different answers for the same execution")
    print(f"\nThis means gen_ai.agent.iteration_budget.consumed = {sorted(consumed_values)}")
    print(f"depending on which framework is instrumented. Same work. Same LLM calls.")
    print(f"Same tokens. {len(consumed_values)} different telemetry values.")


if __name__ == "__main__":
    print("=" * 80)
    print("EVIDENCE: OTel budget attributes are framework-dependent")
    print("=" * 80)

    print_comparison(
        scenario="S2-budget-exhaustion",
        budget_limit=3,
        llm_calls=4,
        tool_calls=3,
        total_tokens=478,
    )

    print("\n")
    print_comparison(
        scenario="S4-parallel-tools",
        budget_limit=2,
        llm_calls=2,
        tool_calls=3,
        total_tokens=370,
    )
