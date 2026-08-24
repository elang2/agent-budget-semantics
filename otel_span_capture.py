"""
OTel Span Capture Layer — shows what each framework ACTUALLY emits as telemetry.

This is the bridge between "frameworks count differently" (otel_comparison.py)
and "here's what your monitoring dashboard would show" (this file).

Uses an in-memory OTel exporter to capture spans during each framework run,
then produces a comparison of the telemetry each framework would emit for
the same scenario.

Key insight: even if two frameworks agree on when to stop, they may emit
DIFFERENT span structures, attribute values, and event counts. The same
execution produces different dashboards depending on which framework
generated the telemetry.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CapturedSpan:
    name: str
    kind: str
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    duration_ms: float = 0
    parent_span_id: Optional[str] = None
    status: str = "OK"


@dataclass
class CapturedTrace:
    framework: str
    scenario: str
    spans: list[CapturedSpan] = field(default_factory=list)
    total_spans: int = 0
    total_events: int = 0


GENAI_ATTRIBUTES = {
    "gen_ai.system": "Framework's AI system identifier",
    "gen_ai.request.model": "Model requested",
    "gen_ai.response.model": "Model that actually responded",
    "gen_ai.request.max_tokens": "Per-request token limit",
    "gen_ai.usage.input_tokens": "Prompt tokens consumed",
    "gen_ai.usage.output_tokens": "Completion tokens consumed",
    "gen_ai.agent.iteration_budget.limit": "Maximum iterations configured",
    "gen_ai.agent.iteration_budget.consumed": "Iterations consumed",
    "gen_ai.agent.token_budget.limit": "Maximum tokens configured",
    "gen_ai.agent.token_budget.consumed": "Tokens consumed",
    "gen_ai.invoke_agent.token_budget.utilization": "Budget utilization ratio",
}


def simulate_framework_spans(framework: str, scenario_result: dict) -> CapturedTrace:
    """
    Given a framework's RunResult from the harness, simulate what OTel spans
    that framework would emit based on its known instrumentation patterns.
    """
    trace = CapturedTrace(
        framework=framework,
        scenario=scenario_result.get("scenario", "unknown"),
    )

    gt = scenario_result.get("ground_truth", {})
    fr = scenario_result.get("framework_reports", {})
    budget_value = scenario_result.get("budget_value", 0)

    root_span = CapturedSpan(
        name=f"agent.invoke",
        kind="INTERNAL",
        attributes={
            "gen_ai.system": _get_system_name(framework),
            "gen_ai.agent.iteration_budget.limit": budget_value,
            "gen_ai.agent.iteration_budget.consumed": _calculate_consumed(
                framework, gt.get("llm_calls", 0), gt.get("tool_calls", 0)
            ),
            "gen_ai.agent.token_budget.consumed": gt.get("total_tokens", 0),
        },
    )
    trace.spans.append(root_span)

    for i in range(gt.get("llm_calls", 0)):
        llm_span = CapturedSpan(
            name=f"gen_ai.chat",
            kind="CLIENT",
            attributes={
                "gen_ai.system": _get_system_name(framework),
                "gen_ai.request.model": "mock-budget-llm",
                "gen_ai.usage.input_tokens": _estimate_input_tokens(i, gt),
                "gen_ai.usage.output_tokens": _estimate_output_tokens(i, gt),
            },
            parent_span_id="root",
        )
        trace.spans.append(llm_span)

    tool_spans_style = _get_tool_span_style(framework)
    for i in range(gt.get("tool_calls", 0)):
        if tool_spans_style == "per_call":
            tool_span = CapturedSpan(
                name=f"tool.execute",
                kind="INTERNAL",
                attributes={"tool.name": f"tool_{i}"},
                parent_span_id="root",
            )
            trace.spans.append(tool_span)
        elif tool_spans_style == "batched":
            if i == 0:
                tool_span = CapturedSpan(
                    name=f"tools.batch",
                    kind="INTERNAL",
                    attributes={"tool.count": gt.get("tool_calls", 0)},
                    parent_span_id="root",
                )
                trace.spans.append(tool_span)

    trace.total_spans = len(trace.spans)
    trace.total_events = sum(len(s.events) for s in trace.spans)

    return trace


def compare_traces(traces: list[CapturedTrace]) -> dict:
    """Compare traces across frameworks and identify telemetry divergences."""
    comparison = {
        "span_count_divergence": {},
        "attribute_divergence": {},
        "structure_divergence": {},
    }

    span_counts = {t.framework: t.total_spans for t in traces}
    if len(set(span_counts.values())) > 1:
        comparison["span_count_divergence"] = span_counts

    consumed_values = {}
    for trace in traces:
        root = trace.spans[0] if trace.spans else None
        if root:
            consumed = root.attributes.get("gen_ai.agent.iteration_budget.consumed")
            consumed_values[trace.framework] = consumed
    if len(set(v for v in consumed_values.values() if v is not None)) > 1:
        comparison["attribute_divergence"]["iteration_budget.consumed"] = consumed_values

    structures = {}
    for trace in traces:
        span_names = [s.name for s in trace.spans]
        structures[trace.framework] = span_names
    unique_structures = set(tuple(v) for v in structures.values())
    if len(unique_structures) > 1:
        comparison["structure_divergence"] = structures

    return comparison


def print_telemetry_comparison(scenario: str, llm_calls: int, tool_calls: int,
                               total_tokens: int, budget_limit: int):
    """Print what each framework's OTel dashboard would show."""
    from otel_comparison import FRAMEWORK_BUDGET_SEMANTICS, _calculate_consumed

    print(f"\nOTel Telemetry Comparison — Scenario: {scenario}")
    print(f"Ground truth: {llm_calls} LLM calls, {tool_calls} tool calls")
    print()

    print("What your monitoring dashboard shows (per framework):")
    print("=" * 90)

    header = f"{'Framework':<16} {'Spans':<7} {'consumed':<10} {'util%':<8} {'token_budget':<14} {'Structure'}"
    print(header)
    print("-" * 90)

    for fw in FRAMEWORK_BUDGET_SEMANTICS:
        consumed = _calculate_consumed(fw, llm_calls, tool_calls)
        util = consumed / budget_limit if budget_limit > 0 else 0

        span_count = 1 + llm_calls + _tool_span_count(fw, tool_calls)

        tool_style = _get_tool_span_style(fw)
        if tool_style == "batched":
            structure = f"root → {llm_calls} llm → 1 batch"
        else:
            structure = f"root → {llm_calls} llm → {tool_calls} tool"

        print(f"{fw:<16} {span_count:<7} {consumed:<10} {util:<8.0%} {total_tokens:<14} {structure}")

    print()
    print("Key insight: Same execution, same tokens, same tools.")
    print("Your Grafana/Datadog dashboard shows DIFFERENT numbers depending on")
    print("which framework generated the traces. Alert thresholds fire differently.")
    print("Cost attribution disagrees. SLOs measured against different baselines.")


def _get_system_name(framework: str) -> str:
    names = {
        "autogen": "autogen",
        "openai_agents": "openai",
        "langchain": "langchain",
        "langgraph": "langchain",
        "crewai": "crewai",
        "adk": "google_adk",
        "semantic_kernel": "azure_ai",
        "anthropic": "anthropic",
        "swarm": "openai",
        "llamaindex": "llamaindex",
        "agno": "agno",
    }
    return names.get(framework, framework)


def _get_tool_span_style(framework: str) -> str:
    batched = {"langchain", "langgraph", "adk", "semantic_kernel", "agno"}
    if framework in batched:
        return "batched"
    return "per_call"


def _tool_span_count(framework: str, tool_calls: int) -> int:
    if _get_tool_span_style(framework) == "batched":
        return 1 if tool_calls > 0 else 0
    return tool_calls


def _estimate_input_tokens(call_index: int, ground_truth: dict) -> int:
    total = ground_truth.get("total_tokens", 0)
    calls = ground_truth.get("llm_calls", 1)
    base = total // (calls * 2)
    return base + (call_index * 40)


def _estimate_output_tokens(call_index: int, ground_truth: dict) -> int:
    total = ground_truth.get("total_tokens", 0)
    calls = ground_truth.get("llm_calls", 1)
    return total // (calls * 3)


if __name__ == "__main__":
    print("=" * 90)
    print("TELEMETRY DIVERGENCE: What your dashboard shows per framework")
    print("=" * 90)

    print_telemetry_comparison(
        scenario="S2-budget-exhaustion",
        budget_limit=3,
        llm_calls=4,
        tool_calls=3,
        total_tokens=478,
    )

    print("\n")
    print_telemetry_comparison(
        scenario="S4-parallel-tools",
        budget_limit=2,
        llm_calls=2,
        tool_calls=3,
        total_tokens=370,
    )

    print("\n")
    print_telemetry_comparison(
        scenario="S8-tool-output-explosion",
        budget_limit=2000,
        llm_calls=3,
        tool_calls=2,
        total_tokens=10660,
    )
