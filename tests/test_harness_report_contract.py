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


class TestScenarioKeysDoNotCollide:
    def test_no_two_scenario_files_share_a_key(self):
        """A normaliser that collapses distinct scenarios would silently merge
        their rows, which is the same class of defect as the equality test that
        matched nothing."""
        import collections, glob, pathlib, yaml
        keys = collections.defaultdict(set)
        files = sorted(glob.glob("scenarios/*.yaml"))
        assert len(files) >= 3, f"only {len(files)} scenario files found; walker is wrong"
        for f in files:
            slug = pathlib.Path(f).stem
            name = (yaml.safe_load(pathlib.Path(f).read_text()) or {}).get("name")
            keys[_scenario_key(slug)].add(f)
            if name:
                keys[_scenario_key(name)].add(f)
        collisions = {k: v for k, v in keys.items() if len(v) > 1}
        assert not collisions, f"scenario keys collide across files: {collisions}"

    def test_absent_scenario_never_matches_a_real_one(self):
        for empty in (None, ""):
            assert _scenario_key(empty) == ""
            assert _scenario_key(empty) != _scenario_key("S2-budget-exhaustion")


class TestOpenAISdkConflictIsRecorded:
    """openai-agents and crewai constrain the openai SDK incompatibly.

    openai-agents 0.22.0 wants >=3,<4; crewai 1.15.16 wants >=2.30,<3. No
    single environment satisfies both, so a run covering both is outside at
    least one framework's declared range by construction, and a result that
    does not name the resolved version cannot be replicated.
    """

    def test_every_cell_records_the_sdk_version_and_range_compliance(self):
        import json, pathlib
        p = pathlib.Path("results/S2-toolchoice-2026-10-04.json")
        if not p.exists():
            import pytest
            pytest.skip("toolchoice results not present")
        cells = json.loads(p.read_text())["cells"]
        assert cells, "no cells to check"
        for name, cell in cells.items():
            assert "openai_sdk_version" in cell, f"{name} does not record the SDK version"
            assert "openai_sdk_within_framework_declared_range" in cell, (
                f"{name} does not record whether the SDK is in range")

    def test_the_conflict_is_real_and_documented(self):
        """Read from package metadata, so this fails if the constraint changes."""
        import importlib.metadata as md
        import pathlib
        try:
            from packaging.requirements import Requirement
        except ImportError:
            import pytest
            pytest.skip("packaging not available")
        spec = {}
        for dist in ("openai-agents", "crewai"):
            try:
                reqs = md.requires(dist) or []
            except md.PackageNotFoundError:
                import pytest
                pytest.skip(f"{dist} not installed")
            for raw in reqs:
                try:
                    r = Requirement(raw)
                except Exception:
                    continue
                if r.name.lower() == "openai" and r.marker is None and str(r.specifier):
                    spec[dist] = str(r.specifier)
        if len(spec) == 2:
            assert spec["openai-agents"] != spec["crewai"], (
                "the two constraints are now identical; if the conflict is gone, "
                "PINS.md's note and the README's CrewAI attribution must be revised"
            )
            pins = pathlib.Path("PINS.md").read_text()
            assert "openai" in pins and "incompatibl" in pins.lower(), (
                "PINS.md must document the shared-dependency conflict")


class TestTheDriverOwnsItsServer:
    """A cell must not be measured against a server the driver did not start.

    On 2026-10-04 an orphaned mock on 127.0.0.1:9803 answered the health check
    for the openai_agents/ignore cell. The driver's start() polled /health and
    proceeded on the first healthy answer, so the cell ran against a foreign
    server with a different script and policy and recorded 9 model calls
    against a baseline of 3. That wrong value reached a commit.
    """

    def _driver(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "abs_drv", "experiments/S2_toolchoice_rerun.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_importing_the_driver_does_not_run_the_experiment(self):
        """The guard that makes every other test in this class safe."""
        import hashlib, pathlib
        target = pathlib.Path("results/S2-toolchoice-2026-10-04.json")
        before = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        self._driver()
        after = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        assert before == after, "importing the driver rewrote the results file"

    def test_free_port_returns_a_bindable_unused_port(self):
        import socket
        m = self._driver()
        port = m.free_port()
        assert isinstance(port, int) and port > 1024
        with socket.socket() as sk:
            sk.bind(("127.0.0.1", port))  # must still be free

    def test_start_refuses_a_server_it_did_not_launch(self):
        """The control: stand up a foreign mock and assert start() refuses it."""
        import json as _json
        import subprocess, sys, time, urllib.request
        m = self._driver()
        port = m.free_port()
        foreign = subprocess.Popen(
            [sys.executable, "mock-llm/server.py", f"--port={port}",
             "--script=scenarios/S2-budget-exhaustion.yaml",
             "--tool-choice-policy=honour"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4)
                    break
                except Exception:
                    time.sleep(0.2)
            else:
                pytest.skip("foreign mock never came up")
            with pytest.raises(SystemExit) as exc:
                m.start(port, "ignore", "scenarios/S2-budget-exhaustion.yaml")
            msg = str(exc.value)
            assert "do not own" in msg or "pid" in msg, msg
        finally:
            foreign.kill()

    def test_health_reports_identity_not_just_liveness(self):
        src = pathlib.Path("mock-llm/server.py").read_text()
        branch = src.split('elif self.path == "/health":', 1)[1].split("else:", 1)[0]
        for field in ("pid", "tool_choice_policy", "script_turns", "ledger_entries"):
            assert field in branch, f"/health must report {field} so a caller can verify ownership"


class TestHarnessOwnsItsServerToo:
    """The audit's top finding: harness.py had the identical defect the driver
    had just been fixed for, and the /reset-installs-a-script change made it
    QUIETER — the correct script gets installed into the wrong process and the
    turn-count check passes.
    """

    def test_harness_does_not_hardcode_a_port(self):
        src = pathlib.Path("harness.py").read_text()
        assert "MOCK_PORT = 9111" not in src, (
            "a fixed port is how a run measures against a stranger")
        assert "free_port()" in src

    def test_harness_checks_the_child_is_alive_and_asserts_ownership(self):
        src = pathlib.Path("harness.py").read_text()
        body = src.split("def start_mock_server", 1)[1].split("\ndef ", 1)[0]
        assert "proc.poll()" in body, (
            "a bind failure must not be waited out against someone else's port")
        assert "assert_owned" in body

    def test_reset_mock_reasserts_identity_not_just_turn_count(self):
        src = pathlib.Path("harness.py").read_text()
        body = src.split("def reset_mock", 1)[1].split("\ndef ", 1)[0]
        assert "assert_owned" in body, (
            "a stranger will accept our script and report the expected turn "
            "count; only pid distinguishes it")

    def test_ownership_logic_is_shared_not_duplicated(self):
        """The root cause was two copies, one fixed and one not."""
        for f in ("harness.py", "experiments/S2_toolchoice_rerun.py"):
            src = pathlib.Path(f).read_text()
            assert "from mock_control import" in src, f"{f} must use the shared module"

    def test_assert_owned_rejects_a_mock_that_cannot_identify_itself(self):
        from mock_control import MockOwnershipError, assert_owned
        class P:
            pid = 1234
        with pytest.raises(MockOwnershipError):
            assert_owned({"status": "ok"}, P())          # no pid reported
        with pytest.raises(MockOwnershipError):
            assert_owned({"pid": 9999}, P())             # wrong pid
        with pytest.raises(MockOwnershipError):
            assert_owned({"pid": 1234, "ledger_entries": 3}, P())
        with pytest.raises(MockOwnershipError):
            assert_owned({"pid": 1234}, P(), policy="ignore")  # policy absent
        assert_owned({"pid": 1234, "ledger_entries": 0}, P())  # the happy path


class TestHarnessRowsDoNotCrashTheReport:
    """The scenario-name fix made harness output matchable for the first time,
    and harness rows carry no `consumed_at_ground_truth`. The list branch had
    no guard where the dict branch has always had one, so `report` after a
    default `run` died with KeyError.
    """

    def test_a_harness_shaped_row_is_skipped_not_fatal(self, tmp_path, monkeypatch):
        import json
        d = tmp_path / "results"
        d.mkdir()
        (d / "latest.json").write_text(json.dumps([{
            "framework": "adk", "scenario": "S2 - Budget Exhaustion",
            "budget_param": "max_iterations", "budget_value": 3,
            "framework_reports": {"llm_calls": 4, "tool_calls": 3},
            "ground_truth": {"llm_calls": 4, "tool_calls": 4, "total_tokens": 800},
            "divergences": {}, "error": None}]))
        (d / "S2-executed.json").write_text(json.dumps({
            "scenario": "S2-budget-exhaustion", "provenance": "executed",
            "frameworks": {"agno": {"consumed_at_ground_truth": None,
                                    "enforced": False, "version": "1.2.5"}}}))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(report_generator, "__file__", str(tmp_path / "report_generator.py"))
        got = _load_harness_results("S2-budget-exhaustion")
        assert "adk" not in got, (
            "a row with no consumed reading must not be loaded as executed")
        assert "agno" in got, "the curated row must still load"
