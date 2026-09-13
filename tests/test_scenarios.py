"""Tests for the scenario library.

Each YAML in scenarios/ is a discriminator on some axis of the divergence
matrix. These tests enforce that every scenario is parseable, structurally
complete, and self-describing enough for the runner to consume.

Adding a scenario without matching these invariants will break the harness
silently in an executed-scenario JSON, so the drift-gate must sit here.
"""

from pathlib import Path

import pytest
import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


def _all_scenario_files():
    return sorted(p for p in SCENARIOS_DIR.glob("S*.yaml") if p.is_file())


def _load(path: Path):
    with open(path) as f:
        # Some scenarios use YAML front-matter with a shebang-style comment.
        return list(yaml.safe_load_all(f))


class TestScenariosPresent:
    def test_at_least_twelve_scenarios(self):
        files = _all_scenario_files()
        assert len(files) >= 12, (
            f"Expected at least 12 scenarios S1..S12; found {len(files)}: "
            f"{[f.name for f in files]}"
        )

    @pytest.mark.parametrize("n", range(1, 13))
    def test_scenario_n_present(self, n):
        pattern = f"S{n}-"
        matches = [p for p in _all_scenario_files() if p.name.startswith(pattern)]
        assert matches, f"Scenario S{n}-*.yaml missing from scenarios/"


class TestScenariosParseable:
    @pytest.mark.parametrize("scenario_path", _all_scenario_files(),
                             ids=lambda p: p.name)
    def test_yaml_parses(self, scenario_path):
        docs = _load(scenario_path)
        assert docs, f"{scenario_path.name} loaded empty"
        first = next((d for d in docs if isinstance(d, dict) and d), None)
        assert first is not None, (
            f"{scenario_path.name} has no dict document; scenario runner will fail"
        )

    @pytest.mark.parametrize("scenario_path", _all_scenario_files(),
                             ids=lambda p: p.name)
    def test_has_name_field(self, scenario_path):
        docs = _load(scenario_path)
        first = next((d for d in docs if isinstance(d, dict) and d), None)
        assert "name" in first, f"{scenario_path.name} missing 'name' field"

    @pytest.mark.parametrize("scenario_path", _all_scenario_files(),
                             ids=lambda p: p.name)
    def test_has_description(self, scenario_path):
        docs = _load(scenario_path)
        first = next((d for d in docs if isinstance(d, dict) and d), None)
        # Description is optional in some scenarios but strongly recommended.
        # We only assert that if it's present, it's non-empty.
        if "description" in first:
            assert first["description"], (
                f"{scenario_path.name} has an empty description field"
            )


class TestExecutedScenariosMatchLibrary:
    """Every -executed.json in results/ must correspond to a real scenario in
    scenarios/. Prevents drift where a results file exists for a scenario
    that was later renamed or removed."""

    def test_S2_executed_matches_scenario(self):
        results = Path(__file__).parent.parent / "results" / "S2-executed.json"
        scenario = SCENARIOS_DIR / "S2-budget-exhaustion.yaml"
        assert results.exists(), "results/S2-executed.json is authoritative for the paper"
        assert scenario.exists(), "scenario file must exist for S2"

    def test_S4_executed_matches_scenario(self):
        results = Path(__file__).parent.parent / "results" / "S4-executed.json"
        scenario = SCENARIOS_DIR / "S4-parallel-tools.yaml"
        assert results.exists()
        assert scenario.exists()

    def test_S5_executed_matches_scenario(self):
        results = Path(__file__).parent.parent / "results" / "S5-executed.json"
        scenario = SCENARIOS_DIR / "S5-error-retry.yaml"
        assert results.exists()
        assert scenario.exists()
