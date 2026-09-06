"""Detect synthesized token budgets on invoke_agent spans.

The OTel semconv-genai#425 proposal carries a normative MUST NOT clause:

    Instrumentations MUST NOT synthesize a token budget by multiplying
    iteration limits by per-call max_tokens.

Mandark-droid's Point 3 on the issue (issuecomment-5547801633, 2026-09-04)
observes that of the five agent frameworks in the mapping table, only one
exposes a real aggregate token cap; the other four expose only an iteration
budget. The temptation to manufacture the missing token budget by
multiplying iteration_limit × per_call_max_tokens is therefore strong and
near-universal, and the product is a number nobody actually configured.

This module provides:

  * `is_synthesized(span_attrs)` — one-shot check on a single span's
    attributes; returns a Finding when synthesis is detected, None otherwise.

  * `scan(traces_or_attrs)` — iterate over a collection of spans or attr
    dicts and return every Finding.

  * `enforce_no_synthesis(...)` — raises `SynthesizedBudgetError` on any
    finding. Intended for CI use: a spec-conformant emitter must pass.

The detection heuristic is intentionally narrow: it fires when the ratio
token_budget.limit / (iteration_budget.limit * max_tokens) rounds to 1.0
within a small tolerance, AND one of the two factors is a well-known SDK
per-call cap (128, 256, 512, 1024, 2048, 4096). This catches the mechanical
"multiply the two configuration knobs" mistake without flagging legitimate
token caps that happen to be integer multiples of iteration limits.
"""

from dataclasses import dataclass
from typing import Iterable, Optional


# Common per-call max_tokens values that show up in framework defaults and
# tutorials. If a token_budget.limit is a product involving one of these, we
# suspect synthesis. Extend this list as new frameworks introduce distinctive
# per-call defaults.
#
# Set covers powers of two (framework defaults for LangChain, LlamaIndex,
# Semantic Kernel) plus round decimal values that appear in OpenAI/Anthropic
# example code (500, 1000, 1500, 3000, 5000).
COMMON_MAX_TOKENS = {
    128, 256, 500, 512, 1000, 1024, 1500, 2000, 2048,
    3000, 4000, 4096, 5000, 6000, 8000, 8192, 16384,
}

# Tolerance for detecting "close to a product" — token budgets set as a
# product will hit exactly, but we allow a small integer slop for cases like
# rounding up to a nearby power of two.
PRODUCT_MATCH_TOLERANCE = 0.02

# Minimum iteration limit below which the product-shape heuristic is
# ambiguous: at iter_limit=1 any token_limit value trivially equals
# 1 × token_limit, and a one-shot agent with a real token cap is a
# legitimate configuration we cannot distinguish from a synthesized product.
# Findings on iter_limit < this threshold are suppressed.
MIN_ITER_LIMIT_FOR_DETECTION = 2


@dataclass
class Finding:
    """One case of a suspected synthesized token budget."""
    framework: str
    iteration_limit: int
    token_limit: int
    matched_max_tokens: int
    ratio: float

    def __str__(self) -> str:
        return (
            f"{self.framework}: token_budget.limit={self.token_limit} looks "
            f"like iteration_budget.limit({self.iteration_limit}) × "
            f"per_call_max_tokens({self.matched_max_tokens}) "
            f"(ratio={self.ratio:.4f})"
        )


class SynthesizedBudgetError(RuntimeError):
    """Raised when enforce_no_synthesis finds one or more Findings."""

    def __init__(self, findings: list[Finding]):
        self.findings = findings
        msg = (
            "Detected synthesized token budget(s), violating the OTel "
            "semconv-genai#425 MUST NOT clause:\n  "
            + "\n  ".join(str(f) for f in findings)
        )
        super().__init__(msg)


def is_synthesized(
    span_attrs: dict,
    framework: str = "?",
) -> Optional[Finding]:
    """Return a Finding if this span's token_budget.limit looks synthesized.

    Reads `gen_ai.agent.token_budget.limit` and
    `gen_ai.agent.iteration_budget.limit` from span_attrs. If either is
    absent or None the span cannot be synthesized under this rule; returns
    None.
    """
    token_limit = span_attrs.get("gen_ai.agent.token_budget.limit")
    iter_limit = span_attrs.get("gen_ai.agent.iteration_budget.limit")

    if token_limit is None or iter_limit is None:
        return None
    if not isinstance(token_limit, (int, float)) or not isinstance(iter_limit, (int, float)):
        return None
    if iter_limit <= 0 or token_limit <= 0:
        return None
    # One-shot agents cannot be disambiguated: iter=1 makes any token_limit
    # trivially match itself as a "product." Suppress findings under the
    # threshold — false-positive prevention outweighs the loss of coverage
    # (a genuinely synthesized budget on iter=1 is a null case anyway).
    if iter_limit < MIN_ITER_LIMIT_FOR_DETECTION:
        return None

    quotient = token_limit / iter_limit

    for candidate in COMMON_MAX_TOKENS:
        if candidate == 0:
            continue
        ratio = quotient / candidate
        if abs(ratio - 1.0) <= PRODUCT_MATCH_TOLERANCE:
            return Finding(
                framework=framework,
                iteration_limit=int(iter_limit),
                token_limit=int(token_limit),
                matched_max_tokens=candidate,
                ratio=ratio,
            )

    return None


def scan(entries: Iterable[dict], framework_key: str = "framework") -> list[Finding]:
    """Return every Finding across a collection of span-attr dicts.

    Each entry is treated as a dict with span attributes plus an optional
    `framework` key naming the emitting framework (used only for reporting).
    """
    findings = []
    for entry in entries:
        framework = entry.get(framework_key, "?")
        # If the entry itself is a full attrs dict, use it directly; if it's
        # a nested dict with an `attributes` key, prefer that.
        attrs = entry.get("attributes", entry)
        finding = is_synthesized(attrs, framework=framework)
        if finding is not None:
            findings.append(finding)
    return findings


def enforce_no_synthesis(entries: Iterable[dict], framework_key: str = "framework") -> None:
    """Raise SynthesizedBudgetError if any entry is synthesized.

    CI-friendly entry point: exit-code-nonzero on any hit.
    """
    findings = scan(entries, framework_key=framework_key)
    if findings:
        raise SynthesizedBudgetError(findings)
