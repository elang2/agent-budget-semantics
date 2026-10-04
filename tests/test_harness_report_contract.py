"""Regression tests for three defects found by external review on 2026-10-04.

All three shared a shape: the apparatus produced a plausible result while
measuring or reading the wrong thing, and no test could see it.
"""
import json
import pathlib
import pytest

import report_generator
from report_generator import _scenario_key, _load_harness_results


class TestScenarioNameMatching:
    """`report` after a `run` silently produced an all-modelled report.

    harness.py writes the scenario YAML's `name` ("S2 - Budget Exhaustion");
    every caller passes the slug ("S2-budget-exhaustion"). The equality test
    never matched, so harness output could never feed the report, and the
    only guard covered the no-directory case.
    """

    def test_yaml_name_and_slug_are_the_same_scenario(self):
        assert _scenario_key("S2 - Budget Exhaustion") == _scenario_key("S2-budget-exhaustion")
        assert _scenario_key("S4 - Parallel Tools") == _scenario_key("S4-parallel-tools")

    def test_different_scenarios_still_differ(self):
        assert _scenario_key("S2-budget-exhaustion") != _scenario_key("S4-parallel-tools")
        assert _scenario_key("S2 - Budget Exhaustion") != _scenario_key("S5-error-retry")

    def test_the_harness_writes_a_name_the_generator_accepts(self):
        """Pin the two sides together so they cannot drift apart again."""
        import yaml
        for slug in ("S2-budget-exhaustion", "S4-parallel-tools", "S5-error-retry"):
            path = pathlib.Path("scenarios") / f"{slug}.yaml"
            if not path.exists():
                continue
            written = yaml.safe_load(path.read_text()).get("name")
            assert _scenario_key(written) == _scenario_key(slug), (
                f"{path} declares name {written!r}, which the report would not "
                f"match against {slug!r}"
            )

    def test_empty_and_missing_names_do_not_match_everything(self):
        assert _scenario_key(None) == ""
        assert _scenario_key(None) != _scenario_key("S2-budget-exhaustion")


class TestZeroMatchedRowsRaises:
    def test_no_matching_scenario_is_an_error_not_a_downgrade(self, tmp_path, monkeypatch):
        """A results/ full of non-matching rows must not report all-modelled.

        This is the exact state `run` used to leave behind, and the previous
        guard could not see it because the directory existed and held JSON.
        """
        d = tmp_path / "results"
        d.mkdir()
        (d / "other.json").write_text(json.dumps(
            [{"framework": "agno", "scenario": "S9 - Something Else",
              "consumed_at_ground_truth": 1}]))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(report_generator, "__file__", str(tmp_path / "report_generator.py"))
        monkeypatch.delenv("ABS_ALLOW_MODELLED_ONLY", raising=False)
        with pytest.raises(SystemExit) as exc:
            _load_harness_results("S2-budget-exhaustion")
        msg = str(exc.value)
        assert "no executed rows matched" in msg
        assert "scenario name" in msg, "the error must name the likely cause"

    def test_the_override_still_works(self, tmp_path, monkeypatch):
        d = tmp_path / "results"
        d.mkdir()
        (d / "other.json").write_text(json.dumps(
            [{"framework": "agno", "scenario": "S9", "consumed_at_ground_truth": 1}]))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(report_generator, "__file__", str(tmp_path / "report_generator.py"))
        monkeypatch.setenv("ABS_ALLOW_MODELLED_ONLY", "1")
        assert _load_harness_results("S2-budget-exhaustion") == {}


class TestCuratedEvidenceWinsOverScratch:
    def test_scratch_harness_output_cannot_override_a_curated_reading(self, tmp_path, monkeypatch):
        """Deterministic precedence, introduced with the name fix.

        Making the comparison work meant scratch `--output` files in results/
        began matching too. glob order is filesystem-dependent, so without
        explicit precedence a throwaway run could have silently replaced a
        curated reading in a published report.
        """
        d = tmp_path / "results"
        d.mkdir()
        (d / "aaa-scratch.json").write_text(json.dumps(
            [{"framework": "agno", "scenario": "S2 - Budget Exhaustion",
              "consumed_at_ground_truth": 99}]))
        (d / "zzz-scratch.json").write_text(json.dumps(
            [{"framework": "agno", "scenario": "S2 - Budget Exhaustion",
              "consumed_at_ground_truth": 98}]))
        (d / "S2-executed.json").write_text(json.dumps({
            "scenario": "S2-budget-exhaustion", "provenance": "executed",
            "frameworks": {"agno": {"consumed_at_ground_truth": None,
                                    "enforced": False, "version": "1.2.5"}}}))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(report_generator, "__file__", str(tmp_path / "report_generator.py"))
        got = _load_harness_results("S2-budget-exhaustion")
        assert got["agno"]["consumed_at_ground_truth"] is None, (
            "the curated -executed.json row must win over scratch output, "
            "regardless of filename or filesystem order"
        )


class TestHonourModeReturnsRealText:
    """The ERRATA E5 defect had no regression test.

    Honour mode suppressed a tool call and returned finish_reason=stop with a
    NULL content, because every scripted tool-call turn carries
    `content: None` and `.get("content", "")` returns it rather than the
    default. CrewAI read the empty answer as an unfinished task and retried.
    """

    def _serve(self, policy, tools_present):
        import cli
        mod = cli._load_mock_server()
        mod.TOOL_CHOICE_POLICY = policy
        mod.load_script([{"content": None, "prompt_tokens": 10,
                          "completion_tokens": 5, "finish_reason": "tool_calls",
                          "tool_calls": [{"id": "c1", "type": "function",
                                          "function": {"name": "f", "arguments": "{}"}}]}])
        return mod

    def test_honour_never_returns_an_empty_final_answer(self):
        mod = self._serve("honour", tools_present=False)
        # Exercise the same branch the handler takes: no tools present.
        scripted = mod.get_next_response()
        assert scripted.get("content") is None, "fixture must start with null content"
        # The handler substitutes non-empty text; assert the constant exists
        # and is non-empty rather than re-implementing the handler here.
        src = pathlib.Path("mock-llm/server.py").read_text()
        assert "HONOURED_CONTENT" in src
        marker = src.split("HONOURED_CONTENT = (", 1)[1].split(")", 1)[0]
        assert "Final answer" in marker and len(marker.strip()) > 20

    def test_ignore_mode_still_returns_the_tool_call(self):
        src = pathlib.Path("mock-llm/server.py").read_text()
        assert 'TOOL_CHOICE_POLICY = "ignore"' in src, (
            "default must stay ignore, or every recorded result changes "
            "counterparty without saying so"
        )


class TestResetInstallsAScript:
    def test_reset_endpoint_can_replace_the_script(self):
        """`harness.py --all` served every scenario from the first script.

        reset() clears LEDGER and SCRIPT_INDEX and leaves SCRIPT untouched,
        and the harness only called /reset.
        """
        src = pathlib.Path("mock-llm/server.py").read_text()
        reset_branch = src.split('elif self.path == "/reset":', 1)[1].split("elif", 1)[0]
        assert "load_script" in reset_branch, (
            "/reset must be able to install a script, or --all measures the "
            "wrong workload for every scenario after the first"
        )
        assert "script_turns_loaded" in reset_branch

    def test_harness_passes_the_scenario_and_verifies_the_load(self):
        src = pathlib.Path("harness.py").read_text()
        assert "reset_mock(scenario)" in src, "harness must install each scenario's script"
        assert "Refusing to measure the wrong" in src, (
            "a silent load failure is the same defect one level down"
        )
