"""Tests that pin reports/ to the data it is derived from.

The committed reports/ had drifted from results/S2-executed.json and from the
prediction model that generated them. divergence-matrix.md published
`[3, 4, 7, 10]` while the model yielded `[3, 4, 5, 8, 10]`; framework-cards.md
described LlamaIndex as counting ReAct steps after the model had been corrected
to LLM responses; report.json claimed tier "executed" for adk and anthropic,
which were never run, and for swarm, which is archived. Nothing caught any of
it, because no test regenerated the reports and compared.

These tests do that. The four markdown artifacts are compared byte-for-byte.
report.json is compared field-for-field with only the generation date
normalised, since that field is wall-clock by design.

The second group pins the per-cell validity contract in results/S2-executed.json
and the scoring rule that reads it, so a null reading cannot silently become a
number again.
"""

import json
import re
from pathlib import Path

import pytest

import report_generator
from report_generator import (
    _load_harness_results,
    generate_json_report,
    write_full_report,
)

REPO_ROOT = Path(__file__).parent.parent
REPORTS = REPO_ROOT / "reports"
RESULTS = REPO_ROOT / "results"
SCENARIO = "S2-budget-exhaustion"

# The ground-truth workload write_full_report() publishes. Kept here so a change
# to either side has to be made deliberately in both.
GT = dict(llm_calls=4, tool_calls=3, total_tokens=478, budget_limit=3)

MARKDOWN_ARTIFACTS = [
    "divergence-matrix.md",
    "dimension-evidence.md",
    "framework-cards.md",
    "otel-recommendations.md",
]


@pytest.fixture
def at_repo_root(monkeypatch):
    """_load_harness_results() resolves Path("results") against the cwd."""
    monkeypatch.chdir(REPO_ROOT)


@pytest.fixture
def regenerated(at_repo_root, tmp_path):
    """Regenerate every artifact into a scratch dir. Never writes to reports/."""
    out = tmp_path / "reports"
    write_full_report(output_dir=str(out))
    return out


@pytest.fixture(scope="module")
def readme_text():
    """README.md as text, so prose figures can be asserted against computed ones."""
    return (REPO_ROOT / "README.md").read_text()


@pytest.fixture(scope="module")
def report_json():
    """The committed reports/report.json, which is the source the README must track."""
    return json.loads((REPORTS / "report.json").read_text())


@pytest.fixture(scope="module")
def s2():
    return json.loads((RESULTS / "S2-executed.json").read_text())


class TestReportsMatchGenerator:
    """The committed reports are what the generator currently produces."""

    @pytest.mark.parametrize("name", MARKDOWN_ARTIFACTS)
    def test_markdown_is_byte_identical(self, regenerated, name):
        committed = (REPORTS / name).read_bytes()
        fresh = (regenerated / name).read_bytes()
        assert committed == fresh, (
            f"reports/{name} has drifted from report_generator.py. Run "
            f"`python report_generator.py` and commit the result. Do not hand-edit "
            f"a generated report: that is how the published divergence set went "
            f"stale against the data it summarised."
        )

    def test_report_json_matches_except_generation_date(self, regenerated):
        committed = json.loads((REPORTS / "report.json").read_text())
        fresh = json.loads((regenerated / "report.json").read_text())

        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", committed["generated"]), (
            "report.json must carry an ISO date in `generated`; got "
            f"{committed['generated']!r}"
        )
        committed.pop("generated")
        fresh.pop("generated")
        assert committed == fresh, (
            "reports/report.json has drifted from report_generator.py. Run "
            "`python report_generator.py` and commit the result."
        )


class TestPublishedFiguresComeFromTheData:
    """Key figures, re-derived from results/ rather than restated."""

    def test_unique_consumed_values_are_the_data(self, at_repo_root, s2):
        report = generate_json_report(scenario=SCENARIO, **GT)

        executed = {
            row["consumed_at_ground_truth"]
            for row in s2["frameworks"].values()
            if row["consumed_at_ground_truth"] is not None
        }
        modeled = {
            r["consumed"]
            for r in report["frameworks"].values()
            if r["provenance"] == "modeled"
        }
        expected = sorted(executed | modeled)

        assert report["summary"]["unique_consumed_values"] == expected
        assert report["summary"]["disagreement_factor"] == len(expected)

    def test_stale_published_set_is_gone(self):
        """`[3, 4, 7, 10]` was generated from the pre-correction model."""
        matrix = (REPORTS / "divergence-matrix.md").read_text()
        assert "[3, 4, 7, 10]" not in matrix
        report = json.loads((REPORTS / "report.json").read_text())
        assert report["summary"]["unique_consumed_values"] != [3, 4, 7, 10]

    def test_every_executed_row_reports_its_measured_value(self, at_repo_root, s2):
        report = generate_json_report(scenario=SCENARIO, **GT)
        for fw, row in s2["frameworks"].items():
            assert report["frameworks"][fw]["provenance"] == "executed", (
                f"{fw} has an executed row in results/ and must not be reported "
                f"as modeled"
            )
            assert (
                report["frameworks"][fw]["consumed"]
                == row["consumed_at_ground_truth"]
            ), f"{fw}: report must carry the measured reading, not a prediction"

    def test_tier_is_derived_not_asserted(self, at_repo_root, s2):
        """adk, anthropic and swarm were never executed. A hand-edited
        report.json once claimed tier "executed" for all three."""
        report = generate_json_report(scenario=SCENARIO, **GT)
        versions = report["framework_versions"]
        for fw in s2["frameworks"]:
            assert versions[fw]["tier"] == "executed"
        assert versions["adk"]["tier"] == "modeled"
        assert versions["anthropic"]["tier"] == "modeled"
        assert versions["swarm"]["tier"] == "archived"

    def test_denominators_partition_the_executed_rows(self, at_repo_root):
        report = generate_json_report(scenario=SCENARIO, **GT)
        d = report["summary"]["denominators"]
        assert d["rows_informative"] + d["rows_uninformative"] == d["rows_executed"]
        assert d["rows_executed"] == report["summary"]["provenance_breakdown"]["executed"]
        assert d["rows_total"] == len(report["frameworks"])


class TestAgnoNonEnforcementSurvivesTheReport:
    """Defect 3: `or` on a legitimate null demoted agno to `modeled` and
    replaced its missing counter with the prediction model's 3."""

    def test_agno_is_loaded_at_all(self, at_repo_root):
        loaded = _load_harness_results(SCENARIO)
        assert "agno" in loaded, (
            "agno was dropped at load time by an `if consumed is not None` gate, "
            "which is why it could be re-materialised downstream from the model"
        )
        assert loaded["agno"]["consumed_at_ground_truth"] is None

    def test_agno_stays_executed_with_no_fabricated_count(self, at_repo_root):
        report = generate_json_report(scenario=SCENARIO, **GT)
        agno = report["frameworks"]["agno"]
        assert agno["provenance"] == "executed"
        assert agno["consumed"] is None, (
            "a null reading must not fall through to _calculate_consumed(), which "
            "returns 3 for a counter that never emitted"
        )
        assert agno["utilization"] is None
        assert agno["exceeded"] is None
        assert agno["enforced"] is False
        assert agno["status"] == "uninformative"
        assert agno["reason"] == "budget_not_enforced_no_counter_emitted"
        assert report["summary"]["frameworks_uninformative"] == ["agno"]

    def test_agno_excluded_from_the_disagreement_count(self, at_repo_root):
        """A framework reporting no value did not report a different one."""
        report = generate_json_report(scenario=SCENARIO, **GT)
        assert None not in report["summary"]["unique_consumed_values"]

    def test_matrix_row_names_the_real_parameter(self):
        matrix = (REPORTS / "divergence-matrix.md").read_text()
        agno_row = next(
            line for line in matrix.splitlines() if line.startswith("| agno ")
        )
        assert "tool_call_limit" in agno_row, (
            "the matrix published agno's parameter as `max_iterations`; the real "
            "parameter is `tool_call_limit`"
        )
        assert "NOT ENFORCED" in agno_row
        assert "100%" not in agno_row

    def test_zero_is_not_treated_as_absent(self, at_repo_root):
        """`a or b` swallows 0 as well as None. No framework reads 0 today, so
        this guards the fix rather than a current row."""
        injected = {
            "langchain": {
                "framework": "langchain",
                "scenario": SCENARIO,
                "consumed_at_ground_truth": 0,
                "unit_observed": "tool_cycles",
                "enforced": True,
                "framework_version": "test",
                "provenance": "executed",
                "tier": "executed",
                "status": "informative",
                "reason": None,
                "budget_param": "AgentExecutor(max_iterations=N)",
                "budget_value": 3,
            }
        }
        report = generate_json_report(
            scenario=SCENARIO, harness_results=injected, **GT
        )
        assert report["frameworks"]["langchain"]["consumed"] == 0
        assert report["frameworks"]["langchain"]["provenance"] == "executed"

    def test_missing_keys_still_fall_back_to_the_model(self, at_repo_root):
        """The fallback is for a row with no reading of either name, which is
        different from a row carrying a null one."""
        report = generate_json_report(scenario=SCENARIO, harness_results={}, **GT)
        assert all(
            r["provenance"] == "modeled" for r in report["frameworks"].values()
        )
        assert report["frameworks"]["agno"]["consumed"] == 3


class TestValidityContract:
    """Per-cell validity gate in results/S2-executed.json."""

    def test_every_cell_declares_tier_status_and_reason(self, s2):
        for fw, row in s2["frameworks"].items():
            assert row["tier"] == "executed", f"{fw} missing tier"
            assert row["status"] in {"informative", "uninformative", "error"}, (
                f"{fw} status {row['status']!r} outside the enum"
            )
            if row["status"] == "informative":
                assert row["reason"] is None
            else:
                assert isinstance(row["reason"], str) and row["reason"]

    def test_status_is_derivable_from_fields_already_present(self, s2):
        """status is derived, never typed. Re-derive it and compare."""
        for fw, row in s2["frameworks"].items():
            if row["consumed_at_ground_truth"] is None:
                if row.get("stopped_by") == "error":
                    derived = "error"
                else:
                    derived = "uninformative"
            else:
                assert row["unit_observed"] is not None
                assert row["counter_at_budget_stop"] is not None
                derived = "informative"
            assert row["status"] == derived, (
                f"{fw}: status {row['status']!r} is not what its own fields imply "
                f"({derived!r})"
            )

    def test_uninformative_cells_have_no_reading_of_any_kind(self, s2):
        for fw, row in s2["frameworks"].items():
            if row["status"] != "informative":
                assert row["consumed_at_ground_truth"] is None
                assert row["counter_at_budget_stop"] is None
                assert row["unit_observed"] is None

    def test_reason_enum_is_closed(self, s2):
        allowed = {
            "budget_not_enforced_no_counter_emitted",
            "runtime_error_before_budget_stop",
        }
        for fw, row in s2["frameworks"].items():
            if row["reason"] is not None:
                assert row["reason"] in allowed, f"{fw}: unknown reason"

    def test_schema_documents_the_contract(self, s2):
        schema = s2["schema"]
        for key in ("tier", "status", "reason", "validity_contract"):
            assert key in schema, f"schema must document {key}"
        assert "None, not zero" in schema["validity_contract"]


class TestBothDenominatorsReported:
    """Defect 2: an uninformative cell scored as a miss inside the denominator."""

    def test_original_figure_is_preserved(self, s2):
        score = s2["prediction_model_score"]
        assert score["total"] == 8
        assert score["correct"] == 4
        assert score["wrong"] == 2
        assert score["partial"] == 1
        assert score["invalid"] == 1

    def test_informative_figure_is_four_of_seven(self, s2):
        score = s2["prediction_model_score"]
        assert score["informative_total"] == 7
        assert score["informative_correct"] == 4

    def test_informative_denominator_equals_the_informative_cells(self, s2):
        informative = [
            fw for fw, row in s2["frameworks"].items()
            if row["status"] == "informative"
        ]
        score = s2["prediction_model_score"]
        assert score["informative_total"] == len(informative)
        assert sorted(score["frameworks_informative"]) == sorted(informative)
        assert score["informative_correct"] == sum(
            1 for fw in informative if s2["frameworks"][fw]["matched"]
        )

    def test_uninformative_cells_are_the_difference(self, s2):
        score = s2["prediction_model_score"]
        assert score["total"] - score["informative_total"] == len(
            score["frameworks_uninformative"]
        )
        assert score["frameworks_uninformative"] == score["frameworks_invalid"]

    def test_denominator_note_names_the_standard(self, s2):
        note = s2["prediction_model_score"]["denominator_note"]
        assert "2608.29930" in note
        assert "None, not zero" in note

    def test_matched_is_untouched(self, s2):
        """`matched` stays a per-cell equality test, including for agno."""
        for fw, row in s2["frameworks"].items():
            expected = row["consumed_at_ground_truth"] == row["predicted_consumed"]
            assert row["matched"] == expected, f"{fw}: matched is not recomputable"
        assert s2["frameworks"]["agno"]["matched"] is False


class TestAmendmentsAreDeclared:
    """Defect 1: a post-execution prediction revision carried only in prose."""

    def test_amendments_exist(self, s2):
        assert isinstance(s2["amendments"], list)
        assert len(s2["amendments"]) >= 1

    def test_every_amendment_carries_the_required_fields(self, s2):
        for entry in s2["amendments"]:
            for field in ("target", "field", "old_value", "new_value",
                          "reason", "revised_after_execution"):
                assert field in entry, f"amendment missing {field}"
            assert isinstance(entry["revised_after_execution"], bool)

    def test_sequences_are_unique_and_monotonic(self, s2):
        """Append-only: a correction is a new entry at a higher sequence."""
        seqs = [e["sequence"] for e in s2["amendments"]]
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))

    def test_llamaindex_revision_is_declared(self, s2):
        entry = next(
            e for e in s2["amendments"]
            if e["target"] == "frameworks.llamaindex"
        )
        assert entry["revised_after_execution"] is True
        assert entry["old_value"] == "tool_cycles"
        assert entry["new_value"] == "llm_invocations"
        assert entry["new_value"] == s2["frameworks"]["llamaindex"]["unit_observed"]

    def test_amendment_targets_resolve(self, s2):
        for entry in s2["amendments"]:
            prefix, _, fw = entry["target"].partition(".")
            assert prefix == "frameworks"
            assert fw in s2["frameworks"], f"amendment targets unknown row {fw!r}"

    def test_revision_did_not_move_the_score(self, s2):
        """The llamaindex prediction stayed wrong under both units, so the
        revision changed the explanation and not the denominator."""
        row = s2["frameworks"]["llamaindex"]
        assert row["predicted_consumed"] == 3
        assert row["consumed_at_ground_truth"] == 4
        assert row["matched"] is False
        assert "llamaindex" in s2["prediction_model_score"]["frameworks_wrong"]
        entry = next(
            e for e in s2["amendments"]
            if e["target"] == "frameworks.llamaindex"
        )
        assert entry["affects_prediction_model_score"] is False

    def test_corrected_prefix_no_longer_carries_the_disclosure(self, s2):
        """A revision recorded only as a prose note is indistinguishable from a
        prediction retrofitted to its result."""
        notes = s2["frameworks"]["llamaindex"]["notes"]
        assert not notes.startswith("CORRECTED:")
        assert "amendments[0]" in notes


class TestMeasuredValuesAreImmutable:
    """Observations, not metadata. Pinned so a future metadata pass cannot
    edit one by accident."""

    @pytest.mark.parametrize("framework,llm,tool,mock", [
        ("autogen", 2, 2, 2),
        ("openai_agents", 3, 3, 3),
        ("langchain", 3, 3, 3),
        ("langgraph", 3, 2, 3),
        ("semantic_kernel", 4, 3, 4),
        ("crewai", 4, 3, 4),
        ("llamaindex", 3, 2, 3),
        ("agno", 10, 9, 10),
    ])
    def test_observed_call_counts(self, s2, framework, llm, tool, mock):
        row = s2["frameworks"][framework]
        assert row["actual_llm_calls"] == llm
        assert row["actual_tool_calls"] == tool
        assert row["mock_confirmed_calls"] == mock

    @pytest.mark.parametrize("framework,counter,unit,enforced", [
        ("autogen", 3, "composite_messages", True),
        ("openai_agents", 3, "llm_invocations", True),
        ("langchain", 3, "tool_cycles", True),
        ("langgraph", 6, "graph_nodes", True),
        ("semantic_kernel", 3, "auto_invoke_rounds", True),
        ("crewai", 3, "tool_cycles", True),
        ("llamaindex", 3, "llm_invocations", True),
        ("agno", None, None, False),
    ])
    def test_counter_unit_and_enforcement(self, s2, framework, counter, unit,
                                          enforced):
        row = s2["frameworks"][framework]
        assert row["counter_at_budget_stop"] == counter
        assert row["unit_observed"] == unit
        assert row["enforced"] is enforced


class TestReadmeFiguresTrackTheReport:
    """The README's headline figures must come from the same source the matrix does.

    These exist because README.md:257 carried "fires for 5/11 but not 6/11" for
    weeks while the regenerated matrix said 6 fire, 4 do not, and 1 emits
    nothing. A prose figure that restates a computed one drifts; the drift gate
    catches reports/ against results/, and this catches README against reports/.

    The expected values are DERIVED from reports/report.json on every run, never
    written down here, so this test cannot itself become the stale figure.
    """

    THRESHOLD = 3

    def _counts(self, report):
        fw = report["frameworks"]
        fire = [k for k, v in fw.items()
                if v.get("consumed") is not None and v["consumed"] > self.THRESHOLD]
        silent = [k for k, v in fw.items()
                  if v.get("consumed") is not None and v["consumed"] <= self.THRESHOLD]
        mute = [k for k, v in fw.items() if v.get("consumed") is None]
        return fire, silent, mute

    def test_alert_counts_in_readme_match_the_report(self, report_json, readme_text):
        fire, silent, mute = self._counts(report_json)
        total = len(report_json["frameworks"])
        assert len(fire) + len(silent) + len(mute) == total
        # The README must state each derived count, and must not state a count
        # for a partition it does not have.
        assert f"fires for {len(fire)} of the {total} rows" in readme_text, (
            f"README alert sentence is stale: report.json gives {len(fire)} firing, "
            f"{len(silent)} silent, {len(mute)} emitting nothing out of {total}"
        )
        assert f"not for {len(silent)}" in readme_text
        assert f"{len(mute)} (Agno) emits no counter" in readme_text or \
               f"{len(mute)} (Agno)" in readme_text

    def test_executed_tier_is_not_an_agreement_claim(self, readme_text):
        # "executed" is a tier. Asserting it means the observed value matched the
        # model is the claim the validity contract exists to separate.
        assert "observed values match model" not in readme_text
        assert "whether the run happened" in readme_text

    def test_matched_count_in_readme_matches_the_data(self, s2, readme_text):
        fw = s2["frameworks"]
        matched = [k for k, v in fw.items() if v.get("matched") is True]
        informative = [k for k, v in fw.items() if v.get("status") == "informative"]
        assert f"{len(matched)} of the {len(informative)} informative rows" in readme_text, (
            f"README matched figure is stale: data gives {len(matched)}/{len(informative)}"
        )

    # Three of the eleven rows were never run (Google ADK and Anthropic are
    # modelled, OpenAI Swarm is archived), so the all-rows value set mixes
    # readings with predictions and may not be described as answers to one
    # execution. Both phrasings are banned, because the generator said "same"
    # where an earlier version of this test forbade only "identical" -- and
    # that test passed while reports/ carried the claim.
    BANNED_EXECUTION_PHRASES = ("identical execution", "same execution")

    @staticmethod
    def _execution_claim_violations(text):
        """Lines asserting that the full value set answers one execution.

        A negation is allowed, but only when the negator is adjacent to the
        phrase. The previous rule was `or "not" in line.lower()`, which passed
        ANY line containing the word "not" anywhere -- so reinstating the
        banned claim alongside an unrelated "not" passed every test. The
        adjacency window is what makes this check mean something.
        """
        import re
        violations = []
        for raw in text.splitlines():
            low = raw.lower()
            for phrase in TestReadmeFiguresTrackTheReport.BANNED_EXECUTION_PHRASES:
                for m in re.finditer(re.escape(phrase), low):
                    window = low[max(0, m.start() - 40):m.start()]
                    # The negator must be in the SAME clause as the phrase, so
                    # the tail may not cross a sentence or clause break. With
                    # `[^.]*` instead, "this is not a modelled row; 5 answers
                    # for the same execution" was accepted -- the `not` came
                    # from the clause before the semicolon. Found by the
                    # positive control below, not by reading this regex.
                    if re.search(r"\b(not|never|rather than)\b[^.;,:]*$", window):
                        continue
                    violations.append(raw.strip())
        return violations

    def test_execution_claim_not_made_in_readme_or_reports(self, readme_text):
        import pathlib
        targets = {"README.md": readme_text}
        for p in sorted(pathlib.Path("reports").glob("*.md")):
            targets[str(p)] = p.read_text()
        for name, text in targets.items():
            bad = self._execution_claim_violations(text)
            assert not bad, (
                f"{name} claims the value set answers one execution, but three of "
                f"the eleven rows were never run: {bad[:3]}"
            )

    def test_the_execution_claim_check_can_be_loud(self):
        # A check that is never shown to fire is indistinguishable from a check
        # that cannot fire. Both banned phrasings must be caught, the adjacent
        # negation must be allowed, and -- the case the old assertion missed --
        # a banned phrase with an unrelated "not" elsewhere on the line must
        # still be caught.
        caught = self._execution_claim_violations(
            "5 different answers for same execution")
        assert len(caught) == 1, "unqualified 'same execution' not caught"
        caught = self._execution_claim_violations(
            "produces 5 different values for the identical execution")
        assert len(caught) == 1, "unqualified 'identical execution' not caught"
        assert not self._execution_claim_violations(
            "the five-value set is not a set of answers to identical execution"
        ), "adjacent negation should be permitted"
        assert self._execution_claim_violations(
            "this is not a modelled row; 5 answers for the same execution"
        ), "banned phrase slipped through on an unrelated 'not' -- the exact "\
           "hole the previous assertion had"
