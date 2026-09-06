"""Empirical proof of Mandark-droid's Point 1 on OTel semconv-genai #425.

The comment (issuecomment-5547801633, 2026-09-04) argues that the obvious
implementation of gen_ai.agent.iteration_budget.consumed and its token twin —
sum from the child inference spans when the agent span ends — breaks under
head sampling: the child spans get dropped, so a sampled trace of a runaway
agent reports zero consumption. Runaway agents are high-volume, and
high-volume traces are exactly what a head sampler drops, so the runaway
case and the sampled case are the same case.

The two tests below demonstrate this empirically with a real OpenTelemetry
in-memory span exporter and a custom sampler that drops every span whose
name is not `invoke_agent`:

  * test_naive_sum_breaks_under_child_sampling — an implementation that
    reads finished child spans at end-of-agent shows 0 tokens consumed,
    even though 3 inference calls totaling 450 tokens happened.

  * test_accumulator_survives_child_sampling — the accumulator pattern
    in budget_accumulator.py reports the correct 450 tokens and 3
    iterations regardless of what the sampler does to child spans.

The pair is what a SIG reviewer needs to see to accept "MUST use an
accumulator" as a normative note on the four attributes, rather than
leaving implementers to discover the trap on their own.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
)

from budget_accumulator import (
    budget_context,
    record_inference,
    record_iteration,
    snapshot,
)


class DropNonAgentSpans(Sampler):
    """Sample every span named `invoke_agent`, drop everything else.

    Approximates head-sampling that keeps agent-root spans but drops the
    high-volume child inference spans — exactly the class of sampler #425's
    motivation section describes.
    """

    def should_sample(self, parent_context, trace_id, name, kind=None,
                      attributes=None, links=None, trace_state=None):
        if name == "invoke_agent":
            return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes or {})
        return SamplingResult(Decision.DROP, attributes or {})

    def get_description(self) -> str:
        return "DropNonAgentSpans"


def _make_tracer():
    """Fresh TracerProvider + InMemorySpanExporter pair for each test."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=DropNonAgentSpans())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.sampling_survivability")
    return tracer, exporter


# The three inference calls the fake agent will make. Total: 3 iterations,
# 250 input tokens, 200 output tokens, 450 total. Same shape as the S2
# baseline in the repo README (llm=4, tokens=478) but simplified for a test.
INFERENCE_CALLS = [
    {"input_tokens": 100, "output_tokens": 50},
    {"input_tokens": 80, "output_tokens": 70},
    {"input_tokens": 70, "output_tokens": 80},
]

EXPECTED_INPUT_TOKENS = sum(c["input_tokens"] for c in INFERENCE_CALLS)   # 250
EXPECTED_OUTPUT_TOKENS = sum(c["output_tokens"] for c in INFERENCE_CALLS)  # 200
EXPECTED_TOTAL_TOKENS = EXPECTED_INPUT_TOKENS + EXPECTED_OUTPUT_TOKENS     # 450
EXPECTED_ITERATIONS = len(INFERENCE_CALLS)                                 # 3


def test_naive_sum_breaks_under_child_sampling():
    """Naive impl: read child spans at end. Sampler drops them. Result: 0."""
    tracer, exporter = _make_tracer()

    with tracer.start_as_current_span("invoke_agent") as root:
        for call in INFERENCE_CALLS:
            with tracer.start_as_current_span("gen_ai.inference") as child:
                child.set_attribute("gen_ai.usage.input_tokens", call["input_tokens"])
                child.set_attribute("gen_ai.usage.output_tokens", call["output_tokens"])

        # End of agent — naive implementation sums from finished child spans.
        finished = exporter.get_finished_spans()
        child_spans = [s for s in finished if s.name == "gen_ai.inference"]
        naive_input = sum(s.attributes.get("gen_ai.usage.input_tokens", 0) for s in child_spans)
        naive_output = sum(s.attributes.get("gen_ai.usage.output_tokens", 0) for s in child_spans)
        naive_total = naive_input + naive_output
        naive_iterations = len(child_spans)

        root.set_attribute("gen_ai.agent.token_budget.consumed", naive_total)
        root.set_attribute("gen_ai.agent.iteration_budget.consumed", naive_iterations)

    # Assertions: root span survived, child spans were dropped, naive counts are wrong.
    finished = exporter.get_finished_spans()
    root_spans = [s for s in finished if s.name == "invoke_agent"]
    child_spans = [s for s in finished if s.name == "gen_ai.inference"]

    assert len(root_spans) == 1, "root invoke_agent span must survive sampling"
    assert len(child_spans) == 0, "child inference spans must be dropped by the sampler"

    root_span = root_spans[0]
    reported_consumed = root_span.attributes["gen_ai.agent.token_budget.consumed"]
    reported_iterations = root_span.attributes["gen_ai.agent.iteration_budget.consumed"]

    # The failure mode: the runaway agent that consumed 450 tokens reports 0.
    assert reported_consumed == 0, (
        f"naive-sum should report 0 under 100% child-span drop, got {reported_consumed}"
    )
    assert reported_iterations == 0, (
        f"naive-sum should report 0 iterations under 100% child-span drop, "
        f"got {reported_iterations}"
    )
    assert reported_consumed != EXPECTED_TOTAL_TOKENS, (
        "naive-sum must NOT match ground truth under sampling — that's the whole point"
    )


def test_accumulator_survives_child_sampling():
    """Accumulator impl: contextvars write on every inference. Sampler has no effect."""
    tracer, exporter = _make_tracer()

    with tracer.start_as_current_span("invoke_agent") as root:
        with budget_context():
            for call in INFERENCE_CALLS:
                with tracer.start_as_current_span("gen_ai.inference") as child:
                    child.set_attribute("gen_ai.usage.input_tokens", call["input_tokens"])
                    child.set_attribute("gen_ai.usage.output_tokens", call["output_tokens"])
                    # The key discipline: write to the accumulator on every
                    # inference call, regardless of whether this span itself
                    # is sampled. The write is a memory operation, not a
                    # trace operation, and does not go through the sampler.
                    record_inference(
                        input_tokens=call["input_tokens"],
                        output_tokens=call["output_tokens"],
                    )
                    record_iteration()

            # End of agent — read the accumulator.
            snap = snapshot()

        root.set_attribute("gen_ai.agent.token_budget.consumed", snap.total_tokens)
        root.set_attribute("gen_ai.agent.iteration_budget.consumed", snap.iterations)

    finished = exporter.get_finished_spans()
    root_spans = [s for s in finished if s.name == "invoke_agent"]
    child_spans = [s for s in finished if s.name == "gen_ai.inference"]

    assert len(root_spans) == 1, "root invoke_agent span must survive sampling"
    assert len(child_spans) == 0, "child inference spans dropped, same as naive case"

    root_span = root_spans[0]
    reported_consumed = root_span.attributes["gen_ai.agent.token_budget.consumed"]
    reported_iterations = root_span.attributes["gen_ai.agent.iteration_budget.consumed"]

    # The success mode: accumulator reports ground truth even though child
    # spans were dropped by the same sampler that broke the naive case above.
    assert reported_consumed == EXPECTED_TOTAL_TOKENS, (
        f"accumulator must report {EXPECTED_TOTAL_TOKENS}, got {reported_consumed}"
    )
    assert reported_iterations == EXPECTED_ITERATIONS, (
        f"accumulator must report {EXPECTED_ITERATIONS}, got {reported_iterations}"
    )


def test_accumulator_isolates_across_concurrent_agents():
    """Two invoke_agent contexts must not see each other's accumulator state."""
    with budget_context():
        record_inference(input_tokens=100, output_tokens=100)
        record_iteration()
        assert snapshot().total_tokens == 200
        assert snapshot().iterations == 1

        # A nested inner context (e.g. a sub-agent) starts fresh.
        with budget_context():
            record_inference(input_tokens=10, output_tokens=10)
            assert snapshot().total_tokens == 20
            assert snapshot().iterations == 0

        # Outer context is restored on inner exit; state unchanged.
        assert snapshot().total_tokens == 200
        assert snapshot().iterations == 1


def test_record_calls_outside_context_are_noop():
    """Instrumentation should be able to call record_inference unconditionally."""
    # These calls must not raise, and must not corrupt any future context.
    record_inference(input_tokens=100, output_tokens=100)
    record_iteration()

    with budget_context():
        assert snapshot().total_tokens == 0
        assert snapshot().iterations == 0
