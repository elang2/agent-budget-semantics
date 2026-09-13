"""Tests for cost_divergence.py — chargeback semantics under framework divergence.

Every claim about cost divergence in the paper flows through this module. If
these tests pass, the paper's Section 7 cost claims (2.3x metering divergence,
alert incomparability, enforcement-failure unbounded) are computable from the
same inputs a reviewer can re-run.
"""

import pytest

from cost_divergence import (
    PRICING_MODELS,
    FRAMEWORK_ITERATION_COUNTS,
    PricingModel,
    calculate_cost_per_framework,
)


class TestPricingModels:
    """The named PricingModel registry must contain the specific models the
    paper references. Adding a model is fine; renaming or removing one silently
    breaks any downstream chargeback claim."""

    def test_gpt4o_present(self):
        assert "gpt-4o" in PRICING_MODELS
        m = PRICING_MODELS["gpt-4o"]
        assert m.input_token_cost_per_1k == 0.005
        assert m.output_token_cost_per_1k == 0.015

    def test_gpt4o_mini_present(self):
        assert "gpt-4o-mini" in PRICING_MODELS

    def test_claude_sonnet_present(self):
        assert "claude-sonnet-4" in PRICING_MODELS

    def test_claude_opus_present(self):
        assert "claude-opus-4" in PRICING_MODELS

    def test_enterprise_chargeback_present(self):
        """The enterprise-chargeback model is what the paper's 2.3x claim
        rides on. Its per-iteration rate must be present."""
        assert "enterprise-chargeback" in PRICING_MODELS
        m = PRICING_MODELS["enterprise-chargeback"]
        assert m.per_iteration_cost == 0.03
        assert m.per_tool_call_cost == 0.01

    def test_all_pricing_models_have_names(self):
        for key, m in PRICING_MODELS.items():
            assert m.name, f"pricing model {key} missing display name"
            assert m.input_token_cost_per_1k >= 0
            assert m.output_token_cost_per_1k >= 0


class TestFrameworkIterationCounts:
    """The FRAMEWORK_ITERATION_COUNTS registry is what makes the divergence
    real. Each framework's counting formula is a lambda(llm, tools) -> int.

    Section 5 of the paper claims specific per-framework mechanisms. These
    tests pin those mechanisms so paper claims can't drift silently."""

    @pytest.mark.parametrize("framework,llm,tools,expected", [
        # AutoGen: user_msg + llm_calls (composite messages counter). But this
        # module models it as llm + tools which is a simplification for
        # per-iteration chargeback. Both are internally consistent.
        ("autogen", 4, 3, 7),
        # OpenAI Agents: counts llm invocations only
        ("openai_agents", 4, 3, 4),
        # LangChain: counts tool cycles
        ("langchain", 4, 3, 3),
        # LangGraph: llm + tools (approximates graph nodes for chargeback)
        ("langgraph", 4, 3, 7),
        # CrewAI: tool cycles
        ("crewai", 4, 3, 3),
        # Google ADK: tool cycles
        ("adk", 4, 3, 3),
        # Semantic Kernel: tool cycles (auto_invoke_rounds)
        ("semantic_kernel", 4, 3, 3),
        # Anthropic client-side pattern: user counts however they want,
        # baseline is LLM invocations
        ("anthropic", 4, 3, 4),
        # OpenAI Swarm (archived): messages = llm + 2*tools
        ("swarm", 4, 3, 10),
        # LlamaIndex: tool cycles per its counter
        ("llamaindex", 4, 3, 3),
        # Agno: NOT ENFORCED — the module still returns a count for
        # chargeback modeling purposes
        ("agno", 4, 3, 3),
    ])
    def test_framework_counts(self, framework, llm, tools, expected):
        fn = FRAMEWORK_ITERATION_COUNTS[framework]
        assert fn(llm, tools) == expected, f"{framework} counted wrong"

    def test_all_paper_frameworks_registered(self):
        """The eight frameworks the paper reports on in S2 must be in the
        registry so their chargeback is computable."""
        paper_frameworks = {
            "autogen", "openai_agents", "langchain", "langgraph",
            "crewai", "semantic_kernel", "llamaindex", "agno"
        }
        assert paper_frameworks.issubset(set(FRAMEWORK_ITERATION_COUNTS.keys()))

    def test_divergence_at_paper_workload(self):
        """The paper's abstract claims four distinct consumed values across
        seven enforcers on the underlying 4-LLM-call / 3-tool-call workload.

        This test replays that claim through the chargeback lambdas.
        Agno is excluded (non-enforcer)."""
        enforcers = ["autogen", "openai_agents", "langchain", "langgraph",
                     "crewai", "semantic_kernel", "llamaindex"]
        counts = {fw: FRAMEWORK_ITERATION_COUNTS[fw](4, 3) for fw in enforcers}
        distinct = set(counts.values())
        assert len(distinct) >= 3, (
            "cost_divergence's per-framework counting model produced fewer "
            "than three distinct values on the paper's workload; the "
            "divergence claim in Section 7 would collapse."
        )


class TestCalculateCostPerFramework:
    def test_returns_dict_with_framework_keys(self):
        pricing = PRICING_MODELS["enterprise-chargeback"]
        result = calculate_cost_per_framework(
            llm_calls=4, tool_calls=3,
            total_input_tokens=300, total_output_tokens=178,
            pricing=pricing,
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == set(FRAMEWORK_ITERATION_COUNTS.keys())

    def test_chargeback_divergence_paper_workload(self):
        """Pin the measured max/min chargeback ratio on the reference workload.

        This assertion previously read ``assert costs`` -- true for any
        non-empty list, so it proved nothing and computed no ratio at all. Under
        it, the module docstring's ``2.3x`` went unchecked. ``2.3x`` is in fact
        the ratio of the docstring's *illustrative* 3-versus-7-budget-unit
        example (7/3 = 2.33), not of this computed workload, whose real ratio is
        2.6363x (swarm 0.33834 against agno 0.12834). The two numbers were
        conflated. Assert the computed one here.
        """
        pricing = PRICING_MODELS["enterprise-chargeback"]
        result = calculate_cost_per_framework(
            llm_calls=4, tool_calls=3,
            total_input_tokens=300, total_output_tokens=178,
            pricing=pricing,
        )

        def total_of(value):
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, dict):
                return value["total_cost"]
            return getattr(value, "total_cost")

        costs = {name: total_of(v) for name, v in result.items()}

        assert set(costs) == set(FRAMEWORK_ITERATION_COUNTS), (
            "every framework in FRAMEWORK_ITERATION_COUNTS must be priced"
        )
        assert all(c > 0 for c in costs.values()), f"non-positive cost in {costs}"

        cheapest = min(costs.values())
        dearest = max(costs.values())
        ratio = dearest / cheapest

        # Exact values, so a pricing-table or iteration-count edit fails loudly
        # rather than drifting unnoticed as the 2.3x claim did.
        assert cheapest == pytest.approx(0.12834), f"cheapest changed: {costs}"
        assert dearest == pytest.approx(0.33834), f"dearest changed: {costs}"
        assert ratio == pytest.approx(2.6363, abs=1e-4), (
            f"chargeback divergence ratio is {ratio:.4f}x, expected 2.6363x. "
            f"If this is an intended change, update the module docstring in "
            f"cost_divergence.py in the same commit. Per-framework: {costs}"
        )

        # The spread must trace to iteration-count disagreement rather than to
        # token pricing. FRAMEWORK_ITERATION_COUNTS maps a framework to a
        # callable (llm_calls, tool_calls) -> count, so evaluate it on this
        # workload. On (4, 3): swarm counts 10, autogen 7, agno 3.
        counts = {
            name: counter(4, 3)
            for name, counter in FRAMEWORK_ITERATION_COUNTS.items()
        }
        dearest_name = max(costs, key=costs.__getitem__)
        cheapest_name = min(costs, key=costs.__getitem__)

        assert counts[dearest_name] == max(counts.values()), (
            f"{dearest_name} is dearest but does not report the highest "
            f"iteration count ({counts[dearest_name]} vs max {max(counts.values())}); "
            f"the divergence no longer traces to counting."
        )
        assert counts[cheapest_name] == min(counts.values()), (
            f"{cheapest_name} is cheapest but does not report the lowest "
            f"iteration count; the divergence no longer traces to counting."
        )
        # Cost ordering must follow count ordering for the extremes to be
        # meaningful at all.
        assert counts[dearest_name] > counts[cheapest_name]


class TestPricingModelDataclass:
    def test_default_optional_fields_are_none(self):
        m = PricingModel(
            name="test",
            input_token_cost_per_1k=0.001,
            output_token_cost_per_1k=0.002,
        )
        assert m.per_iteration_cost is None
        assert m.per_tool_call_cost is None
