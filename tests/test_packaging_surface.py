"""Guard the published-artifact import surface.

Why this file exists: through v0.5.0 the wheel shipped only ``runners/`` and
``mock-llm/``. Every root-level module was silently dropped, because
``[tool.hatch.build.targets.wheel]`` set ``packages = [...]`` and Hatchling
ignores a root-level ``include`` list when it does. The consequences reached
the published artifacts:

* ``pip install agent-budget-semantics`` then ``import budget_accumulator``
  raised ModuleNotFoundError -- the contextvars accumulator is the mechanism
  the project's headline claim rests on.
* ``import synthesis_detector`` likewise failed.
* Both ``[project.scripts]`` console entry points are declared as ``cli:main``,
  and ``cli.py`` was absent, so ``agent-budget-semantics`` and ``abs-compare``
  crashed on invocation.

Nothing caught it because the whole test suite imports from the repo root,
where the modules obviously exist. These tests assert against the *packaging
configuration* instead, so a regression fails in CI rather than on a user's
machine after a release.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Modules a consumer must be able to import from the installed package. Each is
# either load-bearing for a public claim or referenced by an entry point.
REQUIRED_MODULES = [
    "budget_accumulator.py",   # contextvars accumulator; sampling-survivability claim
    "synthesis_detector.py",   # strict + advisory modes; cited in OTel #425 and NIST PR #17
    "cost_divergence.py",
    "cost_source_divergence.py",
    "cli.py",                  # target of both [project.scripts] entry points
    "harness.py",
    "otel_comparison.py",
    "otel_span_capture.py",
    "report_generator.py",
]

REQUIRED_PACKAGES = ["runners", "mock-llm", "scenarios"]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def wheel_target(pyproject: dict) -> dict:
    return pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]


def test_wheel_does_not_combine_packages_with_include(wheel_target: dict) -> None:
    """The exact misconfiguration that broke v0.5.0.

    With ``packages`` set, Hatchling drops a root-level ``include`` list without
    warning. Use ``only-include`` (or ``force-include``) instead.
    """
    assert not ("packages" in wheel_target and "include" in wheel_target), (
        "wheel target sets both `packages` and `include`. Hatchling silently "
        "ignores `include` in that combination, which is how v0.5.0 shipped "
        "without any root-level module. Use `only-include` instead."
    )


@pytest.mark.parametrize("module", REQUIRED_MODULES)
def test_required_module_is_selected_for_the_wheel(
    wheel_target: dict, module: str
) -> None:
    selected = wheel_target.get("only-include") or wheel_target.get("include") or []
    forced = list(wheel_target.get("force-include", {}).keys())
    assert module in selected or module in forced, (
        f"{module} is not selected for the wheel. It would be missing from "
        f"`pip install`, exactly as in v0.5.0."
    )


@pytest.mark.parametrize("pkg", REQUIRED_PACKAGES)
def test_required_package_is_selected_for_the_wheel(
    wheel_target: dict, pkg: str
) -> None:
    selected = wheel_target.get("only-include") or wheel_target.get("packages") or []
    normalised = {entry.rstrip("/") for entry in selected}
    assert pkg in normalised, f"package {pkg!r} is not selected for the wheel"


@pytest.mark.parametrize("module", REQUIRED_MODULES)
def test_required_module_is_selected_for_the_sdist(
    pyproject: dict, module: str
) -> None:
    sdist = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]
    selected = sdist.get("only-include") or sdist.get("include") or []
    assert module in selected, f"{module} is missing from the sdist include list"


def test_every_console_script_target_module_ships(pyproject: dict, wheel_target: dict) -> None:
    """A declared entry point whose module is not packaged crashes on first run."""
    scripts = pyproject.get("project", {}).get("scripts", {})
    assert scripts, "expected at least one console script to be declared"

    selected = set(wheel_target.get("only-include") or wheel_target.get("include") or [])
    selected |= set(wheel_target.get("force-include", {}).keys())

    for name, target in scripts.items():
        module = target.split(":", 1)[0]
        # only root-level single-module targets are checked here; a dotted path
        # resolves through a package, covered by the package tests above.
        if "." in module:
            continue
        assert f"{module}.py" in selected, (
            f"console script {name!r} points at {target!r} but {module}.py is "
            f"not packaged into the wheel, so the script cannot run."
        )


def test_every_required_module_exists_on_disk() -> None:
    """Guards against a stale include list naming a file that has since moved."""
    missing = [m for m in REQUIRED_MODULES if not (REPO_ROOT / m).is_file()]
    assert not missing, (
        f"include list names modules that do not exist at the repo root: {missing}. "
        f"Either restore them or drop them from pyproject."
    )
