"""Tests for synthesis_detector — the enforcement side of #425's MUST NOT."""

import pytest

from synthesis_detector import (
    Finding,
    SynthesizedBudgetError,
    enforce_no_synthesis,
    is_synthesized,
    scan,
)


def _attrs(iter_limit=None, token_limit=None):
    d = {}
    if iter_limit is not None:
        d["gen_ai.agent.iteration_budget.limit"] = iter_limit
    if token_limit is not None:
        d["gen_ai.agent.token_budget.limit"] = token_limit
    return d


class TestPositiveDetection:
    """Cases the detector must catch."""

    def test_exact_product_of_common_max_tokens(self):
        # iteration=10, max_tokens=1024, product=10240
        finding = is_synthesized(_attrs(10, 10240), framework="fake")
        assert finding is not None
        assert finding.matched_max_tokens == 1024
        assert finding.ratio == pytest.approx(1.0)

    def test_product_with_2048(self):
        finding = is_synthesized(_attrs(5, 10240), framework="fake")
        assert finding is not None
        assert finding.matched_max_tokens == 2048

    def test_product_with_4096(self):
        finding = is_synthesized(_attrs(20, 81920), framework="fake")
        assert finding is not None
        assert finding.matched_max_tokens == 4096

    def test_product_within_2_percent(self):
        # iteration=10, expected product=10240, actual=10400 (~1.6% high)
        finding = is_synthesized(_attrs(10, 10400), framework="fake")
        assert finding is not None
        assert finding.matched_max_tokens == 1024


class TestNegativeDetection:
    """Cases the detector must NOT flag."""

    def test_neither_limit_set(self):
        assert is_synthesized(_attrs(), framework="fake") is None

    def test_only_iteration_limit(self):
        assert is_synthesized(_attrs(iter_limit=5), framework="fake") is None

    def test_only_token_limit(self):
        assert is_synthesized(_attrs(token_limit=5000), framework="fake") is None

    def test_token_limit_not_a_product(self):
        # 3000 is not close to any common (iter * max_tokens) product
        assert is_synthesized(_attrs(5, 3000), framework="fake") is None

    def test_ratio_far_from_common_max_tokens(self):
        # iter=10, token=15000 -> quotient=1500, not near any of 128/256/512/1024/2048/4096
        assert is_synthesized(_attrs(10, 15000), framework="fake") is None

    def test_zero_iteration_limit_rejected(self):
        assert is_synthesized(_attrs(0, 1024), framework="fake") is None

    def test_negative_values_rejected(self):
        assert is_synthesized(_attrs(-1, 1024), framework="fake") is None

    def test_non_numeric_values_rejected(self):
        assert is_synthesized(
            {"gen_ai.agent.iteration_budget.limit": "10", "gen_ai.agent.token_budget.limit": 1024},
            framework="fake",
        ) is None


class TestScanAndEnforce:
    """Iteration + CI enforcement surface."""

    def test_scan_returns_findings_across_frameworks(self):
        entries = [
            {"framework": "clean_one", **_attrs(5, 3000)},
            {"framework": "synthesized_one", **_attrs(10, 10240)},
            {"framework": "clean_two", **_attrs(iter_limit=8)},
            {"framework": "synthesized_two", **_attrs(3, 12288)},
        ]
        findings = scan(entries)
        assert len(findings) == 2
        frameworks = {f.framework for f in findings}
        assert frameworks == {"synthesized_one", "synthesized_two"}

    def test_scan_reads_nested_attributes_key(self):
        entries = [{
            "framework": "nested",
            "attributes": _attrs(10, 10240),
        }]
        findings = scan(entries)
        assert len(findings) == 1
        assert findings[0].framework == "nested"

    def test_enforce_passes_when_clean(self):
        entries = [
            {"framework": "a", **_attrs(5, 3000)},
            {"framework": "b", **_attrs(iter_limit=8)},
        ]
        # Should not raise.
        enforce_no_synthesis(entries)

    def test_enforce_raises_on_hit(self):
        entries = [{"framework": "bad", **_attrs(10, 10240)}]
        with pytest.raises(SynthesizedBudgetError) as excinfo:
            enforce_no_synthesis(entries)
        assert len(excinfo.value.findings) == 1
        assert excinfo.value.findings[0].framework == "bad"

    def test_enforce_reports_every_finding_in_message(self):
        entries = [
            {"framework": "bad_one", **_attrs(10, 10240)},
            {"framework": "bad_two", **_attrs(3, 12288)},
        ]
        with pytest.raises(SynthesizedBudgetError) as excinfo:
            enforce_no_synthesis(entries)
        msg = str(excinfo.value)
        assert "bad_one" in msg
        assert "bad_two" in msg


class TestCurrentReporterOutput:
    """The 11 tracked frameworks must currently pass the detector.

    This is the regression guard: as soon as any runner starts emitting a
    synthesized token budget, this test breaks the build.
    """

    def test_current_11_framework_shape_passes(self):
        # Mirrors what otel_comparison.simulate_otel_attributes emits today:
        # every framework has an iteration_budget.limit and no token_budget.limit.
        entries = [
            {"framework": fw, **_attrs(iter_limit=3, token_limit=None)}
            for fw in [
                "autogen", "openai_agents", "langchain", "langgraph",
                "crewai", "adk", "semantic_kernel", "anthropic",
                "swarm", "llamaindex", "agno",
            ]
        ]
        enforce_no_synthesis(entries)  # must not raise
