"""
Cost-Source Divergence — attribute-name and value fork across the LLM
cost-recording ecosystem.

Same LLM call, six emitters, four distinct attribute schemas. When a
consumer wants to answer "what did this call cost," each emitter says
something different — and no verifier can reconcile them without knowing
which layer computed the number.

This module is the empirical companion to `open-telemetry/semantic-conventions-genai#443`
(gen_ai.usage.cost.*). PR #443 proposes a convergent shape: `.amount`,
`.currency`, `.source` (enum: provider | local). The measurements below
show what today's ecosystem emits AND what each entry maps to under the
proposed shape.

The `cost.source=local` value covers three layer patterns that share
one reliability characteristic (locally computed from token counts +
pricing table): gateway pricing tables, client-library packages that
ship bundled pricing data (e.g. `genai-prices`), and inline constants.
Post-hoc backend enrichment is out of scope for `gen_ai.usage.cost.*`
because it reconstructs cost from stored tokens against pricing that
may have drifted since the call. The stale-pricing case below is the
evidence for that scope decision.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from cost_divergence import PRICING_MODELS, PricingModel


@dataclass
class SimulatedCall:
    """One LLM call for which multiple emitters would each record cost."""
    model: str
    input_tokens: int
    output_tokens: int
    provider_returned_cost: Optional[float] = None
    """The provider's own cost value in the response body, when present."""


@dataclass
class EmissionCase:
    """What one emitter records for a given call.

    An emitter is a real-world (or proposed) instrumentation pattern:
    a client-library that ships bundled pricing, a gateway that keeps
    its own pricing table, a provider that returns cost in the response,
    or a post-hoc backend job.
    """
    name: str
    """Human name for the emitter (Pydantic AI + Logfire, LiteLLM, etc.)."""

    layer: str
    """client_library | gateway | provider_response | backend."""

    attributes: dict[str, Any] = field(default_factory=dict)
    """OTel attribute name → value pairs the emitter records today."""

    pr443_source: Optional[str] = None
    """The `cost.source` enum value under PR #443's proposed shape.
    None means the emitter is out-of-scope for `gen_ai.usage.cost.*`."""

    reliability_note: str = ""
    """One-line description of the accuracy/timing characteristics."""

    pricing_freshness: str = "request-time"
    """request-time | install-time | possibly-stale."""


def _token_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost from token counts and a pricing table, USD."""
    pricing = PRICING_MODELS[model]
    return (
        (input_tokens / 1000) * pricing.input_token_cost_per_1k
        + (output_tokens / 1000) * pricing.output_token_cost_per_1k
    )


def _stale_pricing_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """A post-hoc reconstruction using pricing that has drifted 10% since
    the request. Illustrative of backend-enrichment reliability limits."""
    pricing = PRICING_MODELS[model]
    stale_in = pricing.input_token_cost_per_1k * 0.9
    stale_out = pricing.output_token_cost_per_1k * 0.9
    return (input_tokens / 1000) * stale_in + (output_tokens / 1000) * stale_out


def emissions_for(call: SimulatedCall) -> list[EmissionCase]:
    """Return one EmissionCase per emitter that records cost for this call."""
    cases: list[EmissionCase] = []

    # 1. Pydantic AI + Logfire + genai-prices bundled package.
    #    Ships pricing tables as a versioned dependency; computes at
    #    request time; emits under Pydantic-namespace convention.
    logfire_cost = _token_cost(call.model, call.input_tokens, call.output_tokens)
    cases.append(EmissionCase(
        name="Pydantic AI + Logfire (genai-prices)",
        layer="client_library",
        attributes={"operation.cost": round(logfire_cost, 6)},
        pr443_source="local",
        reliability_note="Bundled pricing data, versioned separately, updated per SKU release.",
        pricing_freshness="install-time",
    ))

    # 2. OpenRouter's cost headers, as documented in xrmx's 2026-08-26
    #    comment on OTel semantic-conventions-genai#443. When the gateway
    #    forwards to a provider and the response arrives with cost fields.
    or_input = _token_cost(call.model, call.input_tokens, 0)
    or_output = _token_cost(call.model, 0, call.output_tokens)
    cases.append(EmissionCase(
        name="OpenRouter (cost headers)",
        layer="gateway",
        attributes={
            "gen_ai.usage.input_cost": round(or_input, 6),
            "gen_ai.usage.output_cost": round(or_output, 6),
            "gen_ai.usage.total_cost": round(or_input + or_output, 6),
        },
        pr443_source="provider",
        reliability_note="Gateway-computed but forwarded as if provider-returned.",
        pricing_freshness="request-time",
    ))

    # 3. LiteLLM proxy: gateway with pricing table, emits under gen_ai
    #    span attrs + histogram. Aug 22 Elan comment on PR #443 documented
    #    this shape.
    litellm_cost = _token_cost(call.model, call.input_tokens, call.output_tokens)
    cases.append(EmissionCase(
        name="LiteLLM proxy",
        layer="gateway",
        attributes={
            "gen_ai.usage.cost": round(litellm_cost, 6),
            "gen_ai.cost.amount": round(litellm_cost, 6),
        },
        pr443_source="local",
        reliability_note="Gateway pricing table maintained as configuration.",
        pricing_freshness="request-time",
    ))

    # 4. Direct SDK call: no cost captured by client instrumentation.
    cases.append(EmissionCase(
        name="Direct provider SDK",
        layer="client_library",
        attributes={},
        pr443_source=None,
        reliability_note="No cost telemetry captured; consumer must derive if needed.",
        pricing_freshness="n/a",
    ))

    # 5. Hypothetical provider that returns cost in the response body.
    #    Rare today but growing (some enterprise APIs, some fine-tuning
    #    endpoints, some managed-agent services).
    if call.provider_returned_cost is not None:
        cases.append(EmissionCase(
            name="Provider-returned cost (hypothetical)",
            layer="provider_response",
            attributes={},
            pr443_source="provider",
            reliability_note="Provider's own cost value from response headers or body.",
            pricing_freshness="request-time",
        ))

    # 6. Backend enrichment job: joins stored tokens against a pricing
    #    table hours or days after the fact. Semantically distinct from
    #    local computation at request time.
    stale_cost = _stale_pricing_cost(call.model, call.input_tokens, call.output_tokens)
    cases.append(EmissionCase(
        name="Backend enrichment (stale pricing)",
        layer="backend",
        attributes={"gen_ai.usage.cost.amount": round(stale_cost, 6)},
        pr443_source=None,
        reliability_note="Post-hoc reconstruction; pricing may have drifted since the call.",
        pricing_freshness="possibly-stale",
    ))

    return cases


def pr443_unified(call: SimulatedCall, source: str) -> dict[str, Any]:
    """The convergent shape PR #443 proposes at v0.1.

    `source` must be one of "provider" or "local".
    """
    if source not in ("provider", "local"):
        raise ValueError(f"cost.source must be provider|local, got {source!r}")
    cost = (
        call.provider_returned_cost
        if source == "provider" and call.provider_returned_cost is not None
        else _token_cost(call.model, call.input_tokens, call.output_tokens)
    )
    return {
        "gen_ai.usage.cost.amount": round(cost, 6),
        "gen_ai.usage.cost.currency": "USD",
        "gen_ai.usage.cost.source": source,
    }


def attribute_schema_count(cases: list[EmissionCase]) -> int:
    """How many distinct attribute-name schemas are in play across emitters.

    A schema is the set of attribute keys (values ignored). An empty
    schema counts as one shape (the "no cost captured" case).
    """
    schemas: set[frozenset[str]] = set()
    for c in cases:
        schemas.add(frozenset(c.attributes.keys()))
    return len(schemas)


def print_divergence_table(call: SimulatedCall) -> None:
    """Print the emitter-by-emitter divergence table for one call."""
    cases = emissions_for(call)
    print(f"\nCost-source divergence — {call.model}, "
          f"{call.input_tokens} in / {call.output_tokens} out tokens")
    print(f"Ground truth cost (request-time pricing): "
          f"${_token_cost(call.model, call.input_tokens, call.output_tokens):.6f}")
    if call.provider_returned_cost is not None:
        print(f"Provider-returned cost: ${call.provider_returned_cost:.6f}")
    print()

    header = f"{'Emitter':<40} {'Layer':<18} {'Attrs':<44} {'cost.source':<10}"
    print(header)
    print("-" * len(header))

    for c in cases:
        attrs = ", ".join(sorted(c.attributes.keys())) or "(none)"
        if len(attrs) > 43:
            attrs = attrs[:40] + "..."
        source = c.pr443_source or "out-of-scope"
        print(f"{c.name:<40} {c.layer:<18} {attrs:<44} {source:<10}")

    print()
    print(f"Distinct attribute schemas: {attribute_schema_count(cases)}")
    print()
    print("Under PR #443's proposed v0.1 shape, each in-scope emitter converges to:")
    for src in ("provider", "local"):
        unified = pr443_unified(call, src)
        print(f"  cost.source={src}: " +
              ", ".join(f"{k}={v}" for k, v in unified.items()))
    print()
    print("Backend enrichment stays out of scope. Its pricing may have drifted "
          "since the call, and the recording layer cannot claim the same "
          "request-time reliability the enum promises.")


def emission_report(call: SimulatedCall) -> dict[str, Any]:
    """Structured summary usable by tests and by report_generator."""
    cases = emissions_for(call)
    ground_truth = _token_cost(call.model, call.input_tokens, call.output_tokens)
    return {
        "call": {
            "model": call.model,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "provider_returned_cost": call.provider_returned_cost,
            "ground_truth_cost_usd": round(ground_truth, 6),
        },
        "emitters": [
            {
                "name": c.name,
                "layer": c.layer,
                "attributes": c.attributes,
                "pr443_source": c.pr443_source,
                "reliability_note": c.reliability_note,
                "pricing_freshness": c.pricing_freshness,
            }
            for c in cases
        ],
        "distinct_attribute_schemas": attribute_schema_count(cases),
        "pr443_unified": {
            source: pr443_unified(call, source)
            for source in ("provider", "local")
        },
    }


if __name__ == "__main__":
    print("=" * 72)
    print("COST-SOURCE DIVERGENCE: same call, forked attribute schemas")
    print("=" * 72)

    print_divergence_table(SimulatedCall(
        model="gpt-4o",
        input_tokens=350,
        output_tokens=128,
        provider_returned_cost=None,
    ))

    print()
    print_divergence_table(SimulatedCall(
        model="claude-sonnet-4",
        input_tokens=1200,
        output_tokens=400,
        provider_returned_cost=0.0075,
    ))
