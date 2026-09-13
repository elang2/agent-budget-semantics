"""Tests for the executed-results JSON schema.

The paper's Section 4 tables emit from these files. Any structural drift here
propagates into the paper's tables silently. These tests pin the schema so a
future run against a different framework version can't quietly change what
`consumed_at_ground_truth` means.

Every claim in the paper's abstract, Section 4, Section 5, and Section 7 that
cites a specific number is checked here against results/*-executed.json.
"""

import json
from pathlib import Path

import pytest

RESULTS_DIR = Path(__file__).parent.parent / "results"


def _load(name):
    with open(RESULTS_DIR / name) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def s2():
    return _load("S2-executed.json")


@pytest.fixture(scope="module")
def s4():
    return _load("S4-executed.json")


@pytest.fixture(scope="module")
def s5():
    return _load("S5-executed.json")


class TestS2GroundTruth:
    """The ground-truth workload the paper cites in §3."""

    def test_llm_calls_is_four(self, s2):
        assert s2["ground_truth"]["llm_calls"] == 4

    def test_tool_calls_is_three(self, s2):
        assert s2["ground_truth"]["tool_calls"] == 3

    def test_tokens_is_478(self, s2):
        assert s2["ground_truth"]["total_tokens"] == 478

    def test_budget_limit_is_three(self, s2):
        assert s2["ground_truth"]["budget_limit"] == 3


class TestS2FrameworkCoverage:
    def test_eight_frameworks_executed(self, s2):
        frameworks = list(s2["frameworks"].keys())
        assert len(frameworks) == 8, (
            f"Paper §4.1 reports 8 executed frameworks; found {len(frameworks)}: "
            f"{frameworks}"
        )

    @pytest.mark.parametrize("framework", [
        "autogen", "openai_agents", "langchain", "langgraph",
        "semantic_kernel", "crewai", "llamaindex", "agno"
    ])
    def test_framework_present(self, s2, framework):
        assert framework in s2["frameworks"], (
            f"{framework} row required for §4.1 table"
        )


class TestS2SameUnitTable:
    """The §4.1 same-unit table cells."""

    @pytest.mark.parametrize("framework,predicted,consumed", [
        ("autogen", 7, 5),
        ("openai_agents", 4, 4),
        ("langchain", 3, 3),
        ("semantic_kernel", 3, 3),
        ("crewai", 3, 3),
        ("llamaindex", 3, 4),
    ])
    def test_row(self, s2, framework, predicted, consumed):
        row = s2["frameworks"][framework]
        assert row["predicted_consumed"] == predicted, (
            f"§4.1 table: {framework} predicted={predicted} required"
        )
        assert row["consumed_at_ground_truth"] == consumed, (
            f"§4.1 table: {framework} consumed_at_ground_truth={consumed} required"
        )

    def test_langgraph_separate_row(self, s2):
        """LangGraph is reported in a separate table at budget=6."""
        row = s2["frameworks"]["langgraph"]
        assert row["budget_value"] == 6
        assert row["predicted_consumed"] == 7
        assert row["consumed_at_ground_truth"] == 8

    def test_agno_not_enforced(self, s2):
        row = s2["frameworks"]["agno"]
        assert row["enforced"] is False
        assert row["verification"]["enforcement_effective"] is False


class TestS2MatchedSplit:
    """§5's matched/mismatched partition."""

    def test_matched_set(self, s2):
        matched = {name for name, row in s2["frameworks"].items() if row["matched"]}
        expected = {"openai_agents", "langchain", "semantic_kernel", "crewai"}
        assert matched == expected, (
            f"§5 claims matched={expected}; artifact says {matched}"
        )

    def test_mismatched_set(self, s2):
        mismatched = {name for name, row in s2["frameworks"].items() if not row["matched"]}
        expected = {"autogen", "langgraph", "llamaindex", "agno"}
        assert mismatched == expected, (
            f"§5 claims mismatched={expected}; artifact says {mismatched}"
        )

    def test_half_the_frameworks_claim(self, s2):
        """§5's headline: 'my predictions matched runtime for four of the
        eight executed frameworks'. This test pins that ratio."""
        matched = sum(1 for row in s2["frameworks"].values() if row["matched"])
        total = len(s2["frameworks"])
        assert matched == 4
        assert total == 8
        assert matched / total == 0.5


class TestS2AgnoUnbounded:
    """§7's 'growing to nine tool calls' claim."""

    def test_agno_grew_to_nine(self, s2):
        assert s2["frameworks"]["agno"]["actual_tool_calls"] == 9


class TestS2AlertIncomparability:
    """§7 claim: 'alert when consumed exceeds three' fires on 4 of 7 same-unit
    enforcers (or 4 of 7 including LangGraph at a different unit)."""

    def test_four_enforcers_fire_at_threshold_three(self, s2):
        enforcers = ["autogen", "openai_agents", "langchain",
                     "semantic_kernel", "crewai", "llamaindex", "langgraph"]
        above_three = [
            fw for fw in enforcers
            if s2["frameworks"][fw]["consumed_at_ground_truth"] > 3
        ]
        assert len(above_three) == 4, (
            f"§7's alert incomparability claim expects 4 fires; got {len(above_three)}"
        )


class TestS4:
    """§4.2 parallel-tool table cells."""

    def test_four_frameworks_in_s4(self, s4):
        assert set(s4["frameworks"].keys()) == {
            "langchain", "langgraph", "semantic_kernel", "autogen"
        }

    @pytest.mark.parametrize("framework,predicted,cgt", [
        ("langchain", 1, 3),
        ("langgraph", 1, 1),
        ("semantic_kernel", 1, 4),
        ("autogen", 3, 2),
    ])
    def test_row(self, s4, framework, predicted, cgt):
        row = s4["frameworks"][framework]
        assert row["predicted_consumed"] == predicted
        assert row["consumed_at_ground_truth"] == cgt

    def test_ground_truth(self, s4):
        assert s4["ground_truth"]["parallel_tool_calls"] == 3
        assert s4["ground_truth"]["llm_calls"] == 2
        assert s4["ground_truth"]["budget_limit"] == 2


class TestS5:
    """§4.3 error-retry table cells."""

    def test_four_frameworks_in_s5(self, s5):
        assert set(s5["frameworks"].keys()) == {
            "autogen", "langgraph", "semantic_kernel", "langchain"
        }

    def test_autogen_retry_counts(self, s5):
        row = s5["frameworks"]["autogen"]
        assert row["retry_counting"] == "retry_counts"
        assert row["consumed_at_ground_truth"] == 3

    def test_langchain_errored(self, s5):
        row = s5["frameworks"]["langchain"]
        assert row["stopped_by"] == "error"
        assert row["consumed_at_ground_truth"] is None

    def test_semantic_kernel_retry_free(self, s5):
        row = s5["frameworks"]["semantic_kernel"]
        assert row["retry_counting"] == "retry_free"
        assert row["consumed_at_ground_truth"] == 4


class TestSchemaDocumented:
    """The schema description in each results file must include the four
    principal fields the paper references."""

    def test_s2_schema_documents_key_fields(self, s2):
        schema = s2.get("schema", {})
        assert "consumed_at_ground_truth" in schema
        assert "counter_at_budget_stop" in schema
        assert "predicted_consumed" in schema
        assert "matched" in schema
