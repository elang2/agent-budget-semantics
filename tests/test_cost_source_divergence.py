"""Tests for cost_source_divergence.py.

Every claim about cost-recording ecosystem divergence flows through this
module. If these tests pass, the empirical evidence attached to
OTel semantic-conventions-genai#443 is reproducible from the same inputs
a reviewer can re-run.
"""

import pytest

from cost_source_divergence import (
    EmissionCase,
    SimulatedCall,
    _stale_pricing_cost,
    _token_cost,
    attribute_schema_count,
    emission_report,
    emissions_for,
    pr443_unified,
)


class TestSimulatedCall:
    """SimulatedCall is the input surface. Its fields determine which
    emitters produce entries (provider-returned only fires when its cost
    field is populated)."""

    def test_basic_construction(self):
        c = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        assert c.model == "gpt-4o"
        assert c.input_tokens == 100
        assert c.output_tokens == 50
        assert c.provider_returned_cost is None

    def test_with_provider_cost(self):
        c = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.002,
        )
        assert c.provider_returned_cost == 0.002


class TestTokenCost:
    """Ground-truth cost derivation from token counts + pricing model."""

    def test_gpt4o_pricing(self):
        cost = _token_cost("gpt-4o", 1000, 1000)
        assert cost == pytest.approx(0.005 + 0.015, rel=1e-6)

    def test_gpt4o_mini_smaller_pricing(self):
        cost = _token_cost("gpt-4o-mini", 1000, 1000)
        assert cost == pytest.approx(0.00015 + 0.0006, rel=1e-6)

    def test_zero_tokens_is_zero_cost(self):
        assert _token_cost("gpt-4o", 0, 0) == 0.0

    def test_pricing_scales_linearly(self):
        c1 = _token_cost("gpt-4o", 100, 50)
        c2 = _token_cost("gpt-4o", 200, 100)
        assert c2 == pytest.approx(c1 * 2, rel=1e-6)


class TestStalePricing:
    """Backend-enrichment case: pricing has drifted since the call."""

    def test_stale_pricing_diverges_from_ground_truth(self):
        model = "gpt-4o"
        gt = _token_cost(model, 1000, 500)
        stale = _stale_pricing_cost(model, 1000, 500)
        assert stale != gt
        assert stale == pytest.approx(gt * 0.9, rel=1e-6)


class TestEmissionsFor:
    """The core divergence measurement."""

    def test_baseline_call_produces_expected_emitters(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=350, output_tokens=128)
        cases = emissions_for(call)
        names = [c.name for c in cases]
        assert "Pydantic AI + Logfire (genai-prices)" in names
        assert "OpenRouter (cost headers)" in names
        assert "LiteLLM proxy" in names
        assert "Direct provider SDK" in names
        assert "Backend enrichment (stale pricing)" in names

    def test_provider_returned_hidden_without_cost_field(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        names = [c.name for c in cases]
        assert "Provider-returned cost (hypothetical)" not in names

    def test_provider_returned_appears_when_cost_field_set(self):
        call = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.003,
        )
        cases = emissions_for(call)
        names = [c.name for c in cases]
        assert "Provider-returned cost (hypothetical)" in names

    def test_pydantic_logfire_uses_operation_cost_key(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        pai = next(c for c in cases if c.name.startswith("Pydantic AI"))
        assert list(pai.attributes.keys()) == ["operation.cost"]

    def test_openrouter_uses_three_cost_keys(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        or_case = next(c for c in cases if c.name.startswith("OpenRouter"))
        expected = {
            "gen_ai.usage.input_cost",
            "gen_ai.usage.output_cost",
            "gen_ai.usage.total_cost",
        }
        assert set(or_case.attributes.keys()) == expected

    def test_litellm_uses_two_cost_keys(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        ll = next(c for c in cases if c.name.startswith("LiteLLM"))
        expected = {"gen_ai.usage.cost", "gen_ai.cost.amount"}
        assert set(ll.attributes.keys()) == expected

    def test_direct_sdk_emits_no_cost(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        direct = next(c for c in cases if c.name.startswith("Direct"))
        assert direct.attributes == {}

    def test_backend_enrichment_out_of_scope(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        be = next(c for c in cases if c.name.startswith("Backend enrichment"))
        assert be.pr443_source is None

    def test_pydantic_and_litellm_agree_on_ground_truth(self):
        """Both compute at request-time from the same pricing model. The
        values should be byte-equal despite different attribute names."""
        call = SimulatedCall(model="gpt-4o", input_tokens=350, output_tokens=128)
        cases = emissions_for(call)
        pai = next(c for c in cases if c.name.startswith("Pydantic AI"))
        ll = next(c for c in cases if c.name.startswith("LiteLLM"))
        assert pai.attributes["operation.cost"] == ll.attributes["gen_ai.usage.cost"]
        assert pai.attributes["operation.cost"] == ll.attributes["gen_ai.cost.amount"]

    def test_backend_enrichment_value_drifts(self):
        """Stale-pricing case does NOT match the request-time value."""
        call = SimulatedCall(model="gpt-4o", input_tokens=1000, output_tokens=500)
        cases = emissions_for(call)
        pai = next(c for c in cases if c.name.startswith("Pydantic AI"))
        be = next(c for c in cases if c.name.startswith("Backend enrichment"))
        pai_cost = pai.attributes["operation.cost"]
        be_cost = be.attributes["gen_ai.usage.cost.amount"]
        assert pai_cost != be_cost
        assert be_cost < pai_cost  # 10% price drop was modeled


class TestAttributeSchemaCount:
    """The count of distinct attribute schemas is the headline number
    the PR uses to argue convergence is needed."""

    def test_baseline_has_multiple_schemas(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        n = attribute_schema_count(cases)
        assert n >= 4  # Pydantic, OpenRouter, LiteLLM, backend, and empty

    def test_provider_returned_shape_matches_pr443_convergent(self):
        """When provider returns cost, the emitter records nothing new
        by itself — the PR-#443 convergent shape carries the value."""
        call = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.002,
        )
        cases = emissions_for(call)
        pr = next(c for c in cases if c.name.startswith("Provider-returned"))
        assert pr.pr443_source == "provider"


class TestPR443Unified:
    """The convergent shape PR #443 proposes."""

    def test_local_source_shape(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=350, output_tokens=128)
        u = pr443_unified(call, "local")
        assert set(u.keys()) == {
            "gen_ai.usage.cost.amount",
            "gen_ai.usage.cost.currency",
            "gen_ai.usage.cost.source",
        }
        assert u["gen_ai.usage.cost.currency"] == "USD"
        assert u["gen_ai.usage.cost.source"] == "local"

    def test_provider_source_uses_provider_returned_value(self):
        call = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.999,
        )
        u = pr443_unified(call, "provider")
        assert u["gen_ai.usage.cost.amount"] == 0.999
        assert u["gen_ai.usage.cost.source"] == "provider"

    def test_provider_source_falls_back_to_local_calc_when_no_provider_cost(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        u = pr443_unified(call, "provider")
        # No provider cost supplied → recording layer computes it.
        assert u["gen_ai.usage.cost.amount"] > 0

    def test_invalid_source_raises(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        with pytest.raises(ValueError):
            pr443_unified(call, "estimate")
        with pytest.raises(ValueError):
            pr443_unified(call, "gateway")


class TestEmissionReport:
    """Structured JSON output used by tests and report_generator."""

    def test_report_has_expected_top_level_keys(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        r = emission_report(call)
        assert "call" in r
        assert "emitters" in r
        assert "distinct_attribute_schemas" in r
        assert "pr443_unified" in r

    def test_report_call_echoes_inputs(self):
        call = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.005,
        )
        r = emission_report(call)
        assert r["call"]["model"] == "gpt-4o"
        assert r["call"]["provider_returned_cost"] == 0.005

    def test_report_pr443_unified_shape(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        r = emission_report(call)
        assert set(r["pr443_unified"].keys()) == {"provider", "local"}
        for src_shape in r["pr443_unified"].values():
            assert "gen_ai.usage.cost.amount" in src_shape
            assert "gen_ai.usage.cost.currency" in src_shape
            assert "gen_ai.usage.cost.source" in src_shape


class TestReliabilityCharacteristics:
    """Each emitter carries a reliability_note explaining its accuracy
    and timing. These are stability tests — if the notes change, the
    PR#443 comment references them by content."""

    def test_all_emitters_have_reliability_note(self):
        call = SimulatedCall(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            provider_returned_cost=0.005,
        )
        for c in emissions_for(call):
            assert c.reliability_note, f"{c.name} missing reliability note"

    def test_backend_enrichment_notes_freshness_risk(self):
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        be = next(c for c in cases if c.name.startswith("Backend enrichment"))
        assert be.pricing_freshness == "possibly-stale"

    def test_pydantic_marks_install_time_freshness(self):
        """genai-prices ships at install time; the note must reflect
        that this is different from request-time gateway computation."""
        call = SimulatedCall(model="gpt-4o", input_tokens=100, output_tokens=50)
        cases = emissions_for(call)
        pai = next(c for c in cases if c.name.startswith("Pydantic AI"))
        assert pai.pricing_freshness == "install-time"
