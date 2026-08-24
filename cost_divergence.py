"""
Cost Divergence Calculator — translates iteration/token divergence into real dollars.

The same work (same LLM calls, same tokens) produces different COST REPORTS
depending on which framework's budget telemetry is used for billing/metering.

This makes the abstract OTel divergence tangible:
  "Framework A says you used 3 budget units, Framework B says 7.
   At $0.03/unit, that's $0.09 vs $0.21 for the same work."

For enterprises billing internal teams by agent-iteration-consumption,
this is a 2.3x difference in chargeback depending on instrumentation choice.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PricingModel:
    name: str
    input_token_cost_per_1k: float
    output_token_cost_per_1k: float
    per_iteration_cost: Optional[float] = None
    per_tool_call_cost: Optional[float] = None


PRICING_MODELS = {
    "gpt-4o": PricingModel(
        name="GPT-4o",
        input_token_cost_per_1k=0.005,
        output_token_cost_per_1k=0.015,
    ),
    "gpt-4o-mini": PricingModel(
        name="GPT-4o-mini",
        input_token_cost_per_1k=0.00015,
        output_token_cost_per_1k=0.0006,
    ),
    "claude-sonnet-4": PricingModel(
        name="Claude Sonnet 4",
        input_token_cost_per_1k=0.003,
        output_token_cost_per_1k=0.015,
    ),
    "claude-opus-4": PricingModel(
        name="Claude Opus 4",
        input_token_cost_per_1k=0.015,
        output_token_cost_per_1k=0.075,
    ),
    "enterprise-chargeback": PricingModel(
        name="Enterprise Chargeback",
        input_token_cost_per_1k=0.01,
        output_token_cost_per_1k=0.03,
        per_iteration_cost=0.03,
        per_tool_call_cost=0.01,
    ),
}


FRAMEWORK_ITERATION_COUNTS = {
    "autogen": lambda llm, tools: llm + tools,
    "openai_agents": lambda llm, tools: llm,
    "langchain": lambda llm, tools: tools,
    "langgraph": lambda llm, tools: llm + tools,
    "crewai": lambda llm, tools: tools,
    "adk": lambda llm, tools: tools,
    "semantic_kernel": lambda llm, tools: tools,
    "anthropic": lambda llm, tools: llm,
    "swarm": lambda llm, tools: llm + (tools * 2),
    "llamaindex": lambda llm, tools: tools,
    "agno": lambda llm, tools: tools,
}


def calculate_cost_per_framework(llm_calls: int, tool_calls: int,
                                  total_input_tokens: int,
                                  total_output_tokens: int,
                                  pricing: PricingModel) -> dict:
    """Calculate cost attribution per framework based on their counting semantics."""
    results = {}

    base_token_cost = (
        (total_input_tokens / 1000) * pricing.input_token_cost_per_1k +
        (total_output_tokens / 1000) * pricing.output_token_cost_per_1k
    )

    for fw, counter in FRAMEWORK_ITERATION_COUNTS.items():
        iterations = counter(llm_calls, tool_calls)

        iteration_cost = 0
        if pricing.per_iteration_cost:
            iteration_cost = iterations * pricing.per_iteration_cost

        tool_cost = 0
        if pricing.per_tool_call_cost:
            tool_cost = tool_calls * pricing.per_tool_call_cost

        total = base_token_cost + iteration_cost + tool_cost

        results[fw] = {
            "iterations_reported": iterations,
            "token_cost": round(base_token_cost, 6),
            "iteration_cost": round(iteration_cost, 6),
            "tool_cost": round(tool_cost, 6),
            "total_cost": round(total, 6),
        }

    return results


def print_cost_comparison(scenario: str, llm_calls: int, tool_calls: int,
                          input_tokens: int, output_tokens: int,
                          pricing_key: str = "enterprise-chargeback"):
    """Print cost divergence table for a scenario."""
    pricing = PRICING_MODELS[pricing_key]
    results = calculate_cost_per_framework(
        llm_calls, tool_calls, input_tokens, output_tokens, pricing
    )

    print(f"\nCost Divergence — {scenario}")
    print(f"Pricing: {pricing.name}")
    print(f"Ground truth: {llm_calls} LLM calls, {tool_calls} tool calls, "
          f"{input_tokens} input + {output_tokens} output tokens")
    print()

    header = f"{'Framework':<16} {'Iterations':<12} {'Token $':<10} {'Iter $':<10} {'Tool $':<10} {'Total $':<10}"
    print(header)
    print("-" * 70)

    costs = []
    for fw, r in sorted(results.items(), key=lambda x: x[1]["total_cost"]):
        print(f"{fw:<16} {r['iterations_reported']:<12} "
              f"${r['token_cost']:<9.4f} ${r['iteration_cost']:<9.4f} "
              f"${r['tool_cost']:<9.4f} ${r['total_cost']:<9.4f}")
        costs.append(r["total_cost"])

    min_cost = min(costs)
    max_cost = max(costs)
    ratio = max_cost / min_cost if min_cost > 0 else float("inf")

    print()
    print(f"Cost range: ${min_cost:.4f} — ${max_cost:.4f}")
    print(f"Divergence ratio: {ratio:.1f}x")
    print(f"Same work, same LLM, same tokens. {ratio:.1f}x cost difference in billing.")


def print_monthly_projection(daily_agent_runs: int, llm_calls_per_run: int,
                              tool_calls_per_run: int, input_tokens_per_run: int,
                              output_tokens_per_run: int):
    """Project monthly cost divergence for a production workload."""
    pricing = PRICING_MODELS["enterprise-chargeback"]
    results = calculate_cost_per_framework(
        llm_calls_per_run, tool_calls_per_run,
        input_tokens_per_run, output_tokens_per_run, pricing
    )

    monthly_runs = daily_agent_runs * 30

    print(f"\nMonthly Cost Projection ({daily_agent_runs} runs/day × 30 days = {monthly_runs} runs)")
    print("=" * 70)

    monthly_costs = {}
    for fw, r in results.items():
        monthly_costs[fw] = r["total_cost"] * monthly_runs

    sorted_costs = sorted(monthly_costs.items(), key=lambda x: x[1])

    header = f"{'Framework':<16} {'Per-run $':<12} {'Monthly $':<14} {'vs cheapest'}"
    print(header)
    print("-" * 70)

    cheapest = sorted_costs[0][1]
    for fw, monthly in sorted_costs:
        per_run = results[fw]["total_cost"]
        diff = monthly - cheapest
        pct = ((monthly / cheapest) - 1) * 100 if cheapest > 0 else 0
        extra = f"+${diff:.2f} (+{pct:.0f}%)" if diff > 0 else "baseline"
        print(f"{fw:<16} ${per_run:<11.4f} ${monthly:<13.2f} {extra}")

    print()
    spread = sorted_costs[-1][1] - sorted_costs[0][1]
    print(f"Monthly spread: ${spread:.2f}")
    print(f"Annual spread: ${spread * 12:.2f}")
    print(f"This is ONLY from how iterations are counted. Same work. Same model.")


if __name__ == "__main__":
    print("=" * 70)
    print("COST DIVERGENCE: Same work, different bills")
    print("=" * 70)

    print_cost_comparison(
        scenario="S2-budget-exhaustion (typical agent loop)",
        llm_calls=4,
        tool_calls=3,
        input_tokens=350,
        output_tokens=128,
    )

    print("\n")
    print_cost_comparison(
        scenario="S4-parallel-tools (3 parallel tool calls)",
        llm_calls=2,
        tool_calls=3,
        input_tokens=240,
        output_tokens=130,
    )

    print("\n")
    print_cost_comparison(
        scenario="S8-tool-output-explosion (large tool response)",
        llm_calls=3,
        tool_calls=2,
        input_tokens=10500,
        output_tokens=160,
    )

    print("\n")
    print("=" * 70)
    print("PRODUCTION PROJECTION")
    print("=" * 70)

    print_monthly_projection(
        daily_agent_runs=1000,
        llm_calls_per_run=5,
        tool_calls_per_run=4,
        input_tokens_per_run=2000,
        output_tokens_per_run=500,
    )
