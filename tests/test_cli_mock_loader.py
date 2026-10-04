"""Tests for cli._load_mock_server.

The `mock` subcommand was broken in every install for its whole life and
nothing noticed, because the import is lazy: `--help` worked, and no test
called the loader. The original code imported `mock_llm_pkg.server`, a package
name created nowhere, so the command raised ModuleNotFoundError in the source
tree, the wheel and the container alike. The directory is `mock-llm`, which is
not a legal identifier and therefore can never be a package however it is
installed, so the by-path loader is the only approach that can work.

These tests exercise the loader itself rather than the subcommand, so they do
not need to bind a port.
"""
import pathlib
import pytest

import cli


def test_loader_returns_a_module_with_the_server_api():
    mod = cli._load_mock_server()
    for name in ("run", "load_script", "reset", "Handler", "LedgerEntry"):
        assert hasattr(mod, name), f"loaded mock server has no {name!r}"


def test_loader_module_is_the_file_on_disk():
    mod = cli._load_mock_server()
    expected = (pathlib.Path(cli.__file__).parent / "mock-llm" / "server.py").resolve()
    assert pathlib.Path(mod.__file__).resolve() == expected


def test_tool_choice_policy_default_is_the_recorded_behaviour():
    """Default must stay `ignore`, which is the 2026-08-23 provider.

    If this flips to `honour`, every previously recorded S2 result silently
    describes a different counterparty than the one that produced it.
    """
    mod = cli._load_mock_server()
    assert mod.TOOL_CHOICE_POLICY == "ignore"


def test_run_rejects_an_unknown_tool_choice_policy():
    mod = cli._load_mock_server()
    with pytest.raises(SystemExit):
        mod.run(port=0, tool_choice_policy="honor")  # US spelling is not the flag


def test_loader_reports_the_path_when_the_server_is_missing(monkeypatch, tmp_path):
    """A missing server must name the path it looked for.

    The failure this replaced was a bare ModuleNotFoundError naming a package
    that never existed, which told the reader nothing about where to look.
    """
    fake_cli = tmp_path / "cli.py"
    fake_cli.write_text("")
    monkeypatch.setattr(cli, "__file__", str(fake_cli))
    with pytest.raises(SystemExit) as exc:
        cli._load_mock_server()
    assert "mock-llm" in str(exc.value) and str(tmp_path) in str(exc.value)
