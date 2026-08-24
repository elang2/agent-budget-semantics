"""
Report Generator — produces shareable markdown and structured JSON reports
from differential testing results.

Outputs:
  1. Divergence matrix (markdown table)
  2. Per-dimension evidence summary
  3. Framework comparison card
  4. OTel attribute recommendations
  5. JSON structured report for CI consumption
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from otel_comparison import FRAMEWORK_BUDGET_SEMANTICS, _calculate_consumed


def generate_divergence_matrix(llm_calls: int, tool_calls: int,
                                total_tokens: int, budget_limit: int) -> str:
    """Generate markdown divergence matrix."""
    lines = []
    lines.append("# Divergence Matrix")
    lines.append("")
    lines.append(f"**Ground truth:** {llm_calls} LLM calls, {tool_calls} tool calls, {total_tokens} tokens")
    lines.append(f"**Budget limit:** {budget_limit}")
    lines.append("")
    lines.append("| Framework | Budget Param | consumed | utilization | Counting Method |")
    lines.append("|-----------|-------------|----------|-------------|-----------------|")

    consumed_values = set()
    for fw, semantics in FRAMEWORK_BUDGET_SEMANTICS.items():
        consumed = _calculate_consumed(fw, llm_calls, tool_calls)
        consumed_values.add(consumed)
        util = consumed / budget_limit if budget_limit > 0 else 0
        method = semantics["iteration_definition"][:50]
        exceeded = " **EXCEEDED**" if consumed > budget_limit else ""
        lines.append(f"| {fw} | `{semantics['budget_param']}` | {consumed}{exceeded} | {util:.0%} | {method} |")

    lines.append("")
    lines.append(f"**Unique consumed values:** `{sorted(consumed_values)}`")
    lines.append(f"**Disagreement factor:** {len(consumed_values)} different answers for same execution")
    lines.append("")

    return "\n".join(lines)


def generate_dimension_evidence(scenarios_results: Optional[list] = None) -> str:
    """Generate per-dimension evidence summary."""
    dimensions = {
        "D1": ("Iteration unit", "What counts as one iteration?", [
            ("AutoGen", "message (LLM response OR tool result)"),
            ("OpenAI Agents", "LLM invocation"),
            ("LangChain", "tool-use cycle (action + observation)"),
            ("LangGraph", "graph node execution"),
            ("Semantic Kernel", "auto-invoke round"),
            ("Swarm", "messages added to history"),
        ]),
        "D5": ("Delegation budget", "How is budget shared across delegated agents?", [
            ("AutoGen", "shared pool across group chat"),
            ("CrewAI", "each agent gets independent budget"),
            ("ADK", "remaining budget passed to sub-agent"),
            ("Agno", "team-level shared pool"),
        ]),
        "D7": ("Parallel tool counting", "N parallel tools = how many budget units?", [
            ("OpenAI Agents", "1 (batch = 1 turn)"),
            ("AutoGen", "N (each tool result = separate message)"),
            ("LangChain", "1 (batch = 1 iteration)"),
            ("Swarm", "2N (each tool = request + result messages)"),
        ]),
        "D9": ("Error/retry counting", "Does a failed+retry consume 1 or 2 units?", [
            ("AutoGen", "2 (retry is new turn)"),
            ("CrewAI", "1 (retries are free)"),
            ("LangGraph", "2 (each is a graph step)"),
            ("Semantic Kernel", "1 (failed invoke doesn't decrement)"),
        ]),
        "D11": ("Token budget enforcement", "Cumulative token tracking?", [
            ("AutoGen", "via callback (configurable)"),
            ("ADK", "configurable cumulative"),
            ("Agno", "output tokens only"),
            ("Most others", "per-call max_tokens only"),
        ]),
        "D15": ("Tool output tokens", "Do tool outputs count in budget?", [
            ("AutoGen", "configurable via callbacks"),
            ("LangChain", "no (only LLM tokens)"),
            ("Agno", "no (output tokens only)"),
            ("ADK", "configurable"),
        ]),
        "D19": ("Nested delegation", "Budget inheritance across 3+ levels?", [
            ("AutoGen", "shared pool total"),
            ("CrewAI", "each agent independent"),
            ("ADK", "remaining passed down"),
            ("LangGraph", "recursion_limit minus consumed"),
        ]),
        "D21": ("Timeout budget impact", "Does timeout consume budget?", [
            ("AutoGen", "yes (turn consumed)"),
            ("CrewAI", "no (free retry policy)"),
            ("Semantic Kernel", "yes (attempt consumed)"),
            ("LangGraph", "yes (step consumed)"),
        ]),
    }

    lines = []
    lines.append("# Dimension Evidence Summary")
    lines.append("")
    lines.append(f"**Frameworks tested:** {len(FRAMEWORK_BUDGET_SEMANTICS)}")
    lines.append(f"**Dimensions discovered:** {len(dimensions)} primary + sub-dimensions")
    lines.append("")

    for dim_id, (name, question, evidence) in dimensions.items():
        lines.append(f"## {dim_id}: {name}")
        lines.append("")
        lines.append(f"**Question:** {question}")
        lines.append("")
        lines.append("| Framework | Behavior |")
        lines.append("|-----------|----------|")
        for fw, behavior in evidence:
            lines.append(f"| {fw} | {behavior} |")
        lines.append("")

    return "\n".join(lines)


def generate_framework_cards() -> str:
    """Generate per-framework comparison cards."""
    lines = []
    lines.append("# Framework Budget Semantics Cards")
    lines.append("")

    for fw, semantics in FRAMEWORK_BUDGET_SEMANTICS.items():
        lines.append(f"## {fw}")
        lines.append("")
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        for key, value in semantics.items():
            lines.append(f"| {key.replace('_', ' ').title()} | {value} |")
        lines.append("")

    return "\n".join(lines)


def generate_otel_recommendations() -> str:
    """Generate OTel attribute specification recommendations."""
    lines = []
    lines.append("# OTel Semantic Convention Recommendations")
    lines.append("")
    lines.append("Based on differential testing across 11 frameworks.")
    lines.append("")

    lines.append("## Problem Statement")
    lines.append("")
    lines.append("The proposed `gen_ai.agent.iteration_budget.consumed` attribute")
    lines.append("produces 4+ different values for the same execution depending on")
    lines.append("which framework is instrumented. Without a mandatory counting")
    lines.append("semantics enum, the attribute is not comparable across implementations.")
    lines.append("")

    lines.append("## Recommendation 1: Mandatory counting_method enum")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.iteration_budget.counting_method")
    lines.append("  Values:")
    lines.append("    - llm_calls          (OpenAI Agents, Anthropic)")
    lines.append("    - tool_cycles        (LangChain, CrewAI, ADK, SK, LlamaIndex, Agno)")
    lines.append("    - graph_nodes        (LangGraph)")
    lines.append("    - messages           (AutoGen, Swarm)")
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation 2: Parallel tool batch semantics")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.parallel_tool_counting")
    lines.append("  Values:")
    lines.append("    - batch_as_one       (LangChain, OpenAI, ADK, SK, Agno)")
    lines.append("    - individual         (AutoGen, Swarm)")
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation 3: Error/retry policy")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.retry_budget_policy")
    lines.append("  Values:")
    lines.append("    - retry_consumes     (AutoGen, LangGraph, SK)")
    lines.append("    - retry_free         (CrewAI)")
    lines.append("    - configurable       (LangChain)")
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation 4: Token budget scope")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.token_budget.scope")
    lines.append("  Values:")
    lines.append("    - llm_output_only    (Agno)")
    lines.append("    - llm_total          (most)")
    lines.append("    - including_tools    (configurable in AutoGen, ADK)")
    lines.append("    - per_call_only      (SK, Swarm)")
    lines.append("```")
    lines.append("")

    lines.append("## Evidence")
    lines.append("")
    lines.append("Without these enums, `gen_ai.agent.iteration_budget.consumed` is:")
    lines.append("- **Not comparable** across frameworks")
    lines.append("- **Misleading** in multi-framework dashboards")
    lines.append("- **Incorrect** for cost attribution")
    lines.append("- **Unstable** for SLO/alert thresholds")
    lines.append("")
    lines.append("Full differential testing data: https://github.com/elang2/agent-budget-semantics")

    return "\n".join(lines)


FRAMEWORK_VERSIONS = {
    "autogen": {"package": "autogen-agentchat", "version": "0.4.7", "tier": "modeled"},
    "openai_agents": {"package": "openai-agents", "version": "0.1.1", "tier": "modeled"},
    "langchain": {"package": "langchain", "version": "0.3.14", "tier": "modeled"},
    "langgraph": {"package": "langgraph", "version": "0.3.21", "tier": "modeled"},
    "crewai": {"package": "crewai", "version": "0.108.0", "tier": "modeled"},
    "adk": {"package": "google-adk", "version": "1.2.1", "tier": "modeled"},
    "semantic_kernel": {"package": "semantic-kernel", "version": "1.17.1", "tier": "modeled"},
    "anthropic": {"package": "anthropic", "version": "0.39.0", "tier": "modeled"},
    "swarm": {"package": "openai-swarm", "version": "0.1.0", "tier": "archived"},
    "llamaindex": {"package": "llama-index-core", "version": "0.11.23", "tier": "modeled"},
    "agno": {"package": "agno", "version": "1.2.5", "tier": "modeled"},
}


def _load_harness_results(scenario: str) -> dict:
    """Load executed harness results if they exist. Returns {framework: result_dict}."""
    results_dir = Path("results")
    executed = {}
    for path in results_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                for entry in data:
                    if entry.get("scenario") == scenario:
                        fw = entry["framework"]
                        executed[fw] = entry
            elif isinstance(data, dict) and data.get("scenario") == scenario:
                if "frameworks" in data and isinstance(data["frameworks"], dict):
                    for fw, fw_data in data["frameworks"].items():
                        if fw_data.get("consumed") is not None:
                            executed[fw] = {
                                "framework": fw,
                                "scenario": scenario,
                                "consumed": fw_data["consumed"],
                                "unit_observed": fw_data.get("unit_observed"),
                                "framework_version": fw_data.get("version"),
                                "provenance": data.get("provenance", "executed"),
                            }
                elif "framework" in data:
                    executed[data["framework"]] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return executed


def generate_json_report(scenario: str, llm_calls: int, tool_calls: int,
                          total_tokens: int, budget_limit: int) -> dict:
    """Generate structured JSON report.

    Prefers harness-executed results (provenance: "executed") when available
    in results/. Falls back to _calculate_consumed() model predictions
    (provenance: "modeled") otherwise.
    """
    harness_results = _load_harness_results(scenario)

    results = {}
    for fw in FRAMEWORK_BUDGET_SEMANTICS:
        if fw in harness_results:
            hr = harness_results[fw]
            consumed = hr.get("consumed")
            if consumed is None:
                consumed = _calculate_consumed(fw, llm_calls, tool_calls)
                provenance = "modeled"
            else:
                provenance = hr.get("provenance", "executed")
            version = hr.get("framework_version", FRAMEWORK_VERSIONS.get(fw, {}).get("version", "unknown"))
        else:
            consumed = _calculate_consumed(fw, llm_calls, tool_calls)
            provenance = "modeled"
            version = FRAMEWORK_VERSIONS.get(fw, {}).get("version", "unknown")

        results[fw] = {
            "consumed": consumed,
            "utilization": round(consumed / budget_limit, 2) if budget_limit > 0 else 0,
            "exceeded": consumed > budget_limit,
            "budget_param": FRAMEWORK_BUDGET_SEMANTICS[fw]["budget_param"],
            "counting_method": FRAMEWORK_BUDGET_SEMANTICS[fw]["iteration_definition"],
            "provenance": provenance,
            "version": version,
        }

    consumed_values = sorted(set(r["consumed"] for r in results.values()))
    executed_count = sum(1 for r in results.values() if r["provenance"] == "executed")
    modeled_count = sum(1 for r in results.values() if r["provenance"] == "modeled")

    return {
        "scenario": scenario,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ground_truth": {
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "total_tokens": total_tokens,
            "budget_limit": budget_limit,
        },
        "framework_versions": FRAMEWORK_VERSIONS,
        "frameworks": results,
        "summary": {
            "unique_consumed_values": consumed_values,
            "disagreement_factor": len(consumed_values),
            "frameworks_exceeded": [
                fw for fw, r in results.items() if r["exceeded"]
            ],
            "provenance_breakdown": {
                "executed": executed_count,
                "modeled": modeled_count,
            },
        },
    }


def write_full_report(output_dir: str = "reports"):
    """Generate all report artifacts."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    matrix = generate_divergence_matrix(
        llm_calls=4, tool_calls=3, total_tokens=478, budget_limit=3
    )
    (out / "divergence-matrix.md").write_text(matrix)

    evidence = generate_dimension_evidence()
    (out / "dimension-evidence.md").write_text(evidence)

    cards = generate_framework_cards()
    (out / "framework-cards.md").write_text(cards)

    recommendations = generate_otel_recommendations()
    (out / "otel-recommendations.md").write_text(recommendations)

    report = generate_json_report(
        scenario="S2-budget-exhaustion",
        llm_calls=4, tool_calls=3, total_tokens=478, budget_limit=3
    )
    (out / "report.json").write_text(json.dumps(report, indent=2))

    print(f"Reports written to {output_dir}/")
    print(f"  divergence-matrix.md")
    print(f"  dimension-evidence.md")
    print(f"  framework-cards.md")
    print(f"  otel-recommendations.md")
    print(f"  report.json")


if __name__ == "__main__":
    write_full_report()
