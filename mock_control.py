"""Starting a mock, and proving the server that answers is the one you started.

This module exists because the same defect was fixed in one caller and not the
other. On 2026-10-04 `experiments/S2_toolchoice_rerun.py` was hardened after an
orphaned mock on 127.0.0.1:9803 served a cell and produced 9 model calls where
the truth was 3. `harness.py` carried the identical pattern — a hardcoded port,
a health poll that returns on the first HTTP 200, and no check that the
subprocess is still alive — and was left alone.

Worse, the `/reset`-installs-a-script change made the harness's version of the
bug QUIETER. Before it, a stranger on the port served its own script and the
turn counts were visibly wrong. After it, `reset_mock(scenario)` installs the
correct script into the wrong process, the turn-count check passes, and the run
proceeds against a server whose `--tool-choice-policy` nobody chose. A fix that
converts a loud failure into a silent one is worse than the bug.

So the logic lives here once, and both callers use it.

Liveness is not identity. `/health` returns the server's pid, its policy, its
loaded script length and its ledger depth; a caller asserts all of them.
"""
import socket


def free_port() -> int:
    """Ask the OS for an unused loopback port.

    Guessing a port is how a measurement ends up attributed to a provider
    behaviour nobody configured.
    """
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


class MockOwnershipError(RuntimeError):
    """The server answering on this port is not the one we started."""


def assert_owned(health: dict, proc, *, policy=None, expected_turns=None,
                 require_empty_ledger=True) -> None:
    """Raise unless `health` describes the process in `proc`.

    `policy` and `expected_turns` are checked only when given, so a caller that
    does not pin them still gets the pid and ledger checks. An older mock that
    does not report `pid` fails rather than passing, because a server that
    cannot identify itself cannot be verified.
    """
    got_pid = health.get("pid")
    if got_pid is None:
        raise MockOwnershipError(
            "the mock on this port did not report a pid in /health, so it "
            "cannot be verified as ours. Upgrade the mock, or run against a "
            "port you have proved is free."
        )
    if proc is not None and got_pid != proc.pid:
        raise MockOwnershipError(
            f"the server on this port reports pid={got_pid} but we started "
            f"pid={proc.pid}. Refusing to measure against a server we do not "
            f"own: it may carry a different script or a different "
            f"--tool-choice-policy, which would silently reattribute every row."
        )
    if policy is not None and health.get("tool_choice_policy") != policy:
        raise MockOwnershipError(
            f"the mock reports policy {health.get('tool_choice_policy')!r}, "
            f"expected {policy!r}"
        )
    if expected_turns is not None and health.get("script_turns") != expected_turns:
        raise MockOwnershipError(
            f"the mock loaded {health.get('script_turns')} script turns, "
            f"expected {expected_turns}"
        )
    if require_empty_ledger and health.get("ledger_entries"):
        raise MockOwnershipError(
            f"the mock already has {health['ledger_entries']} ledger entries "
            f"before this run started"
        )
