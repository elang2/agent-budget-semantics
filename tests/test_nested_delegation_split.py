"""Empirical proof of Mandark-droid's Point 2 on OTel semconv-genai #425.

The proposal in issue #425 does not say what a supervisor delegating to
sub-agents should report for `gen_ai.agent.iteration_budget.consumed`.
Mandark-droid's comment (issuecomment-5547801633, 2026-09-04) argues that
both readings — "direct only" (supervisor's own inference calls) and
"subtree" (supervisor + delegates) — are defensible, and that whichever
way the SIG goes it must be stated because the two produce very different
numbers on the same trace.

The tests below show, on a controlled fake trace, exactly how different:

  * A supervisor makes 1 inference call, then delegates to two sub-agents.
    Sub-agent A makes 2 calls; sub-agent B makes 1. Same trace, four
    inference calls total.

  * Direct reading on the supervisor's span: iterations=1, tokens=150.
  * Subtree reading on the supervisor's span: iterations=4, tokens=825.

That is a 4x divergence on iterations and a 5.5x divergence on tokens for
the identical trace. An operator alerting on utilization > 0.9 will page
or not page based on which of two defensible attribute definitions the
instrumentation picked. The spec has to pick one and name it, or split
the name.
"""

from budget_accumulator import (
    budget_context,
    record_inference,
    record_iteration,
    snapshot,
)


# Supervisor makes one small inference call directly.
SUPERVISOR_DIRECT = {"input_tokens": 100, "output_tokens": 50}

# Sub-agent A makes two larger inference calls.
SUB_A_CALLS = [
    {"input_tokens": 200, "output_tokens": 100},
    {"input_tokens": 200, "output_tokens": 100},
]

# Sub-agent B makes one small inference call.
SUB_B_CALLS = [
    {"input_tokens": 50, "output_tokens": 25},
]

# Expectations derived from the constants above.
DIRECT_INPUT = SUPERVISOR_DIRECT["input_tokens"]                # 100
DIRECT_OUTPUT = SUPERVISOR_DIRECT["output_tokens"]              # 50
DIRECT_TOTAL = DIRECT_INPUT + DIRECT_OUTPUT                     # 150
DIRECT_ITERATIONS = 1

SUB_A_INPUT = sum(c["input_tokens"] for c in SUB_A_CALLS)       # 400
SUB_A_OUTPUT = sum(c["output_tokens"] for c in SUB_A_CALLS)     # 200
SUB_B_INPUT = sum(c["input_tokens"] for c in SUB_B_CALLS)       # 50
SUB_B_OUTPUT = sum(c["output_tokens"] for c in SUB_B_CALLS)     # 25

SUBTREE_INPUT = DIRECT_INPUT + SUB_A_INPUT + SUB_B_INPUT        # 550
SUBTREE_OUTPUT = DIRECT_OUTPUT + SUB_A_OUTPUT + SUB_B_OUTPUT    # 275
SUBTREE_TOTAL = SUBTREE_INPUT + SUBTREE_OUTPUT                  # 825
SUBTREE_ITERATIONS = DIRECT_ITERATIONS + len(SUB_A_CALLS) + len(SUB_B_CALLS)  # 4


def _run_supervisor_with_two_sub_agents():
    """Common trace shape reused by every test in this module."""
    with budget_context() as supervisor:
        record_inference(**SUPERVISOR_DIRECT)
        record_iteration()

        with budget_context():
            for call in SUB_A_CALLS:
                record_inference(**call)
                record_iteration()

        with budget_context():
            for call in SUB_B_CALLS:
                record_inference(**call)
                record_iteration()

        # snapshot() at end of supervisor, before context exit, so we see
        # the completed sub-agent frames folded in as children.
        return snapshot()


def test_supervisor_direct_reading():
    """Direct-only reading counts the supervisor's own inference calls."""
    snap = _run_supervisor_with_two_sub_agents()
    assert snap.input_tokens == DIRECT_INPUT
    assert snap.output_tokens == DIRECT_OUTPUT
    assert snap.total_tokens == DIRECT_TOTAL
    assert snap.iterations == DIRECT_ITERATIONS


def test_supervisor_subtree_reading():
    """Subtree reading folds in every sub-agent's contribution."""
    snap = _run_supervisor_with_two_sub_agents()
    assert snap.subtree_input_tokens() == SUBTREE_INPUT
    assert snap.subtree_output_tokens() == SUBTREE_OUTPUT
    assert snap.subtree_total_tokens == SUBTREE_TOTAL
    assert snap.subtree_iterations() == SUBTREE_ITERATIONS


def test_direct_and_subtree_diverge_meaningfully():
    """Same trace, two defensible readings, an order of magnitude apart.

    This test is the SIG-facing artifact: run it, read the numbers, decide
    whether the spec picks direct-only, subtree, or splits the attribute
    name to carry both. Any answer is defensible; leaving it under-specified
    is not.
    """
    snap = _run_supervisor_with_two_sub_agents()

    # Iterations: 4x divergence on the same trace.
    assert snap.iterations == 1
    assert snap.subtree_iterations() == 4
    iterations_ratio = snap.subtree_iterations() / snap.iterations
    assert iterations_ratio == 4.0

    # Tokens: 5.5x divergence on the same trace.
    assert snap.total_tokens == 150
    assert snap.subtree_total_tokens == 825
    tokens_ratio = snap.subtree_total_tokens / snap.total_tokens
    assert tokens_ratio == 5.5


def test_snapshot_is_a_deep_copy():
    """Callers holding a snapshot must not observe post-hoc mutations."""
    with budget_context():
        record_inference(input_tokens=10, output_tokens=10)
        record_iteration()

        with budget_context():
            record_inference(input_tokens=5, output_tokens=5)
            record_iteration()

        snap_at_readout = snapshot()

        # Mutate live state after the snapshot was taken.
        record_inference(input_tokens=1000, output_tokens=1000)
        record_iteration(n=100)

        # The snapshot must reflect state at readout time, not now.
        assert snap_at_readout.input_tokens == 10
        assert snap_at_readout.subtree_input_tokens() == 15
        assert snap_at_readout.iterations == 1
        assert snap_at_readout.subtree_iterations() == 2


def test_deep_nested_delegation_chain():
    """A 4-level delegation chain: each level folds in every deeper level."""
    with budget_context():
        record_inference(input_tokens=10, output_tokens=10)
        record_iteration()
        with budget_context():
            record_inference(input_tokens=20, output_tokens=20)
            record_iteration()
            with budget_context():
                record_inference(input_tokens=40, output_tokens=40)
                record_iteration()
                with budget_context():
                    record_inference(input_tokens=80, output_tokens=80)
                    record_iteration()

        root = snapshot()

    # Direct: level 1 only.
    assert root.total_tokens == 20
    assert root.iterations == 1

    # Subtree: 20 + 40 + 80 + 160 = 300, 1 + 1 + 1 + 1 = 4.
    assert root.subtree_total_tokens == 300
    assert root.subtree_iterations() == 4
