"""Context-local accumulator for iteration and token consumption.

Rationale: an agent's iteration_budget.consumed and token_budget.consumed
attributes must not be computed by summing child inference spans at the end
of the agent run. Head-based sampling drops child spans probabilistically,
which is exactly the failure mode issue #425 (open-telemetry/semantic-conventions-genai)
was raised to address: runaway agents are high-volume, and high-volume traces
are exactly what head samplers throw away, so the naive "sum from children at
end" approach reports zero consumption for the traces that matter most.

The fix is a context-local accumulator that every inference call writes to
regardless of whether its own span is sampled. This module provides that
accumulator. Instrumentations wrap their invoke_agent in `budget_context()`
and update the accumulator on each inference call; at agent end they read
`snapshot()` and set it as attributes on the parent span.

Reference: Mandark-droid's implementation note on issue #425 (comment id
5547801633, 2026-09-04) confirms this discipline works in practice across
five agent frameworks.
"""

from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class BudgetSnapshot:
    input_tokens: int = 0
    output_tokens: int = 0
    iterations: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


_current: ContextVar[BudgetSnapshot | None] = ContextVar(
    "agent_budget_accumulator", default=None
)


def current() -> BudgetSnapshot | None:
    """Return the active accumulator, or None if outside a budget_context()."""
    return _current.get()


def record_inference(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Record one inference call's token usage into the active accumulator.

    No-op if called outside a `budget_context()`; that lets instrumentation
    call this unconditionally without guarding on whether the caller opted in.
    """
    snap = _current.get()
    if snap is None:
        return
    snap.input_tokens += input_tokens
    snap.output_tokens += output_tokens


def record_iteration(n: int = 1) -> None:
    """Record `n` completed iterations into the active accumulator."""
    snap = _current.get()
    if snap is None:
        return
    snap.iterations += n


def snapshot() -> BudgetSnapshot:
    """Return a copy of the active accumulator.

    Raises RuntimeError if called outside a `budget_context()`, because a
    consumer that thinks it's reading real consumption but reads a zero-init
    default is exactly the failure mode this module exists to prevent.
    """
    snap = _current.get()
    if snap is None:
        raise RuntimeError(
            "budget_accumulator.snapshot() called outside a budget_context(). "
            "Wrap the invoke_agent execution in `with budget_context():` first."
        )
    return BudgetSnapshot(
        input_tokens=snap.input_tokens,
        output_tokens=snap.output_tokens,
        iterations=snap.iterations,
    )


@contextmanager
def budget_context():
    """Open a fresh accumulator for the duration of an invoke_agent run.

    The accumulator is context-local (contextvars), so concurrent agent runs
    on the same thread — including asyncio tasks — see independent state.
    """
    token = _current.set(BudgetSnapshot())
    try:
        yield _current.get()
    finally:
        _current.reset(token)
