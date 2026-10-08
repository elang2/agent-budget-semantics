"""S2 re-run under both tool_choice policies, with ledgers persisted.

Differs from /tmp/rerun2.py in three ways, each of which exists because the
earlier run could not answer a question that was put to its output:

1. Every ledger is written to disk, so the results file can name a path
   instead of asserting a count. rerun2 held ledgers in memory and discarded
   them, which meant `honoured` could be counted but not explained.
2. The honour trigger is disambiguated per entry. `server.py` honours on
   `tool_choice == "none"` OR on absent/empty `tools`, so an aggregate
   `honoured` count conflates two different mechanisms. semantic_kernel and
   crewai both show honoured > 0 with tool_choice_none_sent == 0, which can
   only be the second trigger, and that distinction changes what the honour
   cell measures.
3. The resolved version of every framework is recorded, so the file does not
   depend on PINS.md still being true when it is read.
"""
import argparse
import asyncio, datetime as dt, json, os, pathlib, subprocess, sys, time, urllib.request
import importlib.metadata as md

# CrewAI exports OpenTelemetry spans to telemetry.crewai.com during the run and
# retries for about a minute when the host is unreachable, which is why its
# cells take longer than the others. In an experiment whose premise is that the
# mock's request ledger is the only ground truth, a framework under test
# shipping traces to a vendor is both a hygiene gap and an undeclared network
# dependency. Measured: setting these does not change any cell -- the committed
# values were produced with the export failing.
#
# Applied in main(), NOT at import. OTEL_SDK_DISABLED is global, so setting it
# at module scope leaked into every process that imported this module and took
# the OTel SDK down with it: it broke two sampling-survivability tests, which
# legitimately build real spans. Same class as the side-effect-on-import
# problem recorded at the bottom of this file. main() still runs before any
# runner is imported, which is the only ordering the frameworks require.
TELEMETRY_OFF = {
    "CREWAI_TELEMETRY_OPT_OUT": "true",
    "OTEL_SDK_DISABLED": "true",
}


def silence_framework_telemetry():
    """Apply TELEMETRY_OFF, returning what was actually set for the record."""
    applied = {}
    for k, v in TELEMETRY_OFF.items():
        applied[k] = os.environ.get(k, v)
        os.environ.setdefault(k, v)
    return applied

from mock_control import MockOwnershipError, assert_owned, free_port
import yaml

LEDGER_DIR = pathlib.Path("results/ledgers/S2-toolchoice-2026-10-04")
DIST = {"agno": "agno", "openai_agents": "openai-agents",
        "semantic_kernel": "semantic-kernel", "crewai": "crewai"}


def start(port, policy, scenario_path):
    """Start a mock and prove the server answering is the one we started.

    The ownership logic lives in mock_control so that harness.py and this
    driver cannot diverge again. They already did once: this file was hardened
    after an orphaned mock served a cell, and harness.py — carrying the
    identical hardcoded-port pattern — was left alone until an audit found it.
    """
    proc = subprocess.Popen([sys.executable, "mock-llm/server.py", f"--port={port}",
                             f"--script={scenario_path}", f"--tool-choice-policy={policy}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    expected_turns = len(yaml.safe_load(pathlib.Path(scenario_path).read_text())["script"])
    for _ in range(40):
        if proc.poll() is not None:
            raise SystemExit(
                f"mock for {policy} exited immediately with code {proc.returncode}; "
                f"port {port} is probably already in use")
        try:
            raw = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=0.4).read()
        except Exception:
            time.sleep(0.2)
            continue
        try:
            assert_owned(json.loads(raw), proc, policy=policy,
                         expected_turns=expected_turns)
        except MockOwnershipError as e:
            proc.kill()
            raise SystemExit(str(e))
        return proc
    proc.kill()
    raise SystemExit(f"mock {port} never came up")


def ledger(port):
    d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/ledger", timeout=5).read())
    return d if isinstance(d, list) else d.get("entries", d.get("ledger", []))


def _require_version(fw):
    """Installed version of `fw`'s distribution, or a usable error.

    md.version() raises PackageNotFoundError (surfacing as StopIteration from
    metadata.distribution on some versions) when a framework is absent. A
    reader reproducing one cell hits that as a raw traceback naming neither the
    framework nor the fix.
    """
    try:
        return md.version(DIST[fw])
    except md.PackageNotFoundError:
        raise SystemExit(
            f"{fw} is selected but its distribution {DIST[fw]!r} is not "
            f"installed. Install it at the pinned version from PINS.md, or "
            f"restrict the run with --frameworks."
        ) from None


def _openai_version():
    try:
        return md.version("openai")
    except Exception:
        return None


def _within_declared_range(fw):
    """Is the installed openai SDK inside this framework's declared range?

    True, False, or None when the framework states no unconditional
    constraint. Read from the framework's own metadata rather than hardcoded,
    so a dependency bump changes the answer instead of silently invalidating
    it.
    """
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version
    except Exception:
        return None
    got = _openai_version()
    if got is None:
        return None
    try:
        _reqs = md.requires(DIST[fw]) or []
    except md.PackageNotFoundError:
        # Unguarded this raised PackageNotFoundError here and StopIteration from
        # inside metadata.distribution on some versions -- either way a raw
        # traceback for the ordinary case of a framework not being installed.
        return None
    for raw in _reqs:
        try:
            req = Requirement(raw)
        except Exception:
            continue
        if req.name.lower() != "openai" or req.marker is not None:
            continue
        if not str(req.specifier):
            continue
        return bool(req.specifier.contains(Version(got), prereleases=True))
    return None


# Where every numeric field in the output comes from. The vocabulary is fixed
# so a reader can query provenance instead of trusting a field name, and so a
# test can forbid the one claim this project keeps making by accident: that a
# harness counter or a declared constant is a framework self-report.
#
#   ledger          read from the mock's per-request ledger
#   harness_counter incremented by this harness, inside the tool bodies
#   framework_api   read from a framework's own public counter
#   declared        a value we configured, echoed back
#   modelled        computed from a source reading, never observed
#   hand_authored   typed by a human into a results file
#
# `framework_api` is deliberately unused here. No runner reads any framework's
# internal counter, so nothing in this file may claim it.
PROVENANCE = {
    "ledger_llm_calls": "ledger",
    "ledger_tool_calls": "ledger",
    "requests_sending_tool_choice_none": "ledger",
    "requests_sending_any_tool_choice": "ledger",
    "requests_with_tools_absent_or_empty": "ledger",
    "honoured_total": "ledger",
    "honoured_via_tool_choice_none": "ledger",
    "honoured_via_tools_absent": "ledger",
    # MISNOMERS, retained because they are cited, corrected here rather than
    # renamed. `actual_tool_calls` is `tool_calls_observed`, a counter this
    # harness increments inside each tool body in all eight runners -- it is a
    # direct count of executions and a better column than any modelled value,
    # but it is NOT a framework self-report. `actual_llm_calls` is len(ledger)
    # for four runners and budget_value for openai-agents.
    "framework_reported_tool_calls": "harness_counter",
    "framework_reported_llm_calls": "per_runner",
    "stopped_by": "framework_api",
    "framework_version": "declared",
    "openai_sdk_version": "declared",
    "budget_limit": "declared",
}

# Which runners derive actual_llm_calls how, read from their source rather than
# asserted, because a grep for `actual_llm_calls=len(` once reported five and
# missed semantic_kernel, which assigns through an intermediate variable.
def _llm_calls_provenance(fw):
    src = pathlib.Path(f"runners/runner_{fw}.py").read_text()
    import re
    if re.search(r"llm_calls\s*=\s*len\(", src):
        return "ledger"
    if re.search(r"llm_calls\s*=\s*budget_value", src):
        return "declared"
    return "framework_api"


def classify_mechanism(cells):
    """Classify each framework's stop mechanism from its own ledgers.

    Derived from listed inputs, not asserted — and the inputs are not all
    ledger reads, which an earlier version of this docstring got wrong. The
    point of R6 is that "declared" versus "enforced" is not a binary: what
    separates these frameworks is how much their limit depends on the
    counterparty cooperating. Each row emits `classified_on`, the tuple it was
    classified on, with the provenance of each element. Three signals:

      - withdraws_tools: did the framework stop advertising `tools`?
      - signals_tool_choice_none: did it ask the provider to stop instead?
      - declined_offered_call: was it handed a tool call it did not execute?

    The third is the one that distinguishes a real refusal from a request,
    and it is only observable against a provider that ignores the first two
    -- which is why the non-compliant mock is the stressor rather than a
    confound.
    """
    out = {}
    for fw in sorted({c["framework"] for c in cells.values()}):
        ig = cells.get(f"{fw}/ignore")
        ho = cells.get(f"{fw}/honour")
        if ig is None:
            continue
        withdraws = ig["requests_with_tools_absent_or_empty"] > 0
        signals = ig["requests_sending_tool_choice_none"] > 0
        offered = ig["ledger_tool_calls"]
        executed = ig["framework_reported_tool_calls"]
        declined = (
            None if executed is None else max(0, offered - executed)
        )

        if ig["stopped_by"] == "error" or ig.get("error"):
            # A framework that crashed did not decide anything. Counting an
            # unexecuted tool call as a refusal would credit a traceback with
            # enforcement, which is the same error as reading a null counter
            # as a zero.
            mechanism = "unclassifiable_run_errored"
            note = (f"run errored under the non-compliant provider "
                    f"(stopped_by={ig['stopped_by']!r}), so the "
                    f"{declined if declined else 0} unexecuted tool call(s) are not "
                    f"evidence of a refusal")
        elif declined:
            mechanism = "client_side_refusal"
            note = (f"declined {declined} of {offered} tool call(s) the "
                    f"non-compliant provider offered")
        elif not withdraws and not signals:
            mechanism = "local_stop"
            note = ("stopped without signalling the provider at all; sent no "
                    "tool_choice and never withdrew tools")
        elif signals:
            mechanism = "cooperative_request"
            note = ("asked the provider to stop via tool_choice=none and "
                    "executed what came back anyway")
        else:
            mechanism = "withdrew_tools_only"
            note = "stopped advertising tools but was not tested by an offered call"

        out[fw] = {
            "mechanism": mechanism,
            # The tuple the label is a function of, emitted so the label is
            # checkable rather than trusted. `stopped_by` and the executed
            # tool count come from the runner, not the ledger, so the earlier
            # docstring claim that all three signals are "read from the ledger"
            # was wrong; listing the inputs makes that visible instead of
            # requiring the reader to take the word "derived" on faith.
            "classified_on": {
                "withdraws_tools": withdraws,
                "signals_tool_choice_none": signals,
                "tool_calls_offered": offered,
                "tool_calls_executed": executed,
                "tool_calls_declined": declined,
                "stopped_by": ig["stopped_by"],
                "input_provenance": {
                    "withdraws_tools": "ledger",
                    "signals_tool_choice_none": "ledger",
                    "tool_calls_offered": "ledger",
                    "tool_calls_executed": "harness_counter",
                    "tool_calls_declined": "modelled (offered minus executed)",
                    "stopped_by": "framework_api",
                },
            },
            "counterparty_dependent": (
                None if mechanism == "unclassifiable_run_errored"
                else mechanism == "cooperative_request"),
            "note": note,
            "withdraws_tools": withdraws,
            "signals_tool_choice_none": signals,
            "tool_calls_offered_under_noncompliant_provider": offered,
            "tool_calls_executed_under_noncompliant_provider": executed,
            "tool_calls_declined": declined,
            "stopped_by_under_noncompliant_provider": ig["stopped_by"],
            "ledger_calls_ignore_vs_honour": [
                ig["ledger_llm_calls"], ho["ledger_llm_calls"] if ho else None],
        }
    return out


def summarise(fw, policy, led, r, err=None):
    # The two honour triggers, separated. An entry is attributed to
    # tool_choice only when `tool_choice_received == "none"`; everything else
    # the mock honoured was honoured because `tools` was absent or empty.
    via_tc = sum(1 for e in led
                 if e.get("tool_choice_honoured") and e.get("tool_choice_received") == "none")
    via_no_tools = sum(1 for e in led
                       if e.get("tool_choice_honoured") and e.get("tool_choice_received") != "none")
    out = dict(
        framework=fw,
        framework_version=_require_version(fw),
        # The openai SDK is a shared transitive dependency that these
        # frameworks constrain INCOMPATIBLY -- openai-agents 0.22.0 wants
        # openai>=3,<4 while crewai 1.15.16 wants >=2.30,<3 -- so no single
        # environment satisfies both, and the resolved version decides which
        # framework is inside its declared support range. Recorded per cell
        # because a result that does not name it cannot be replicated.
        openai_sdk_version=_openai_version(),
        openai_sdk_within_framework_declared_range=_within_declared_range(fw),
        mock_tool_choice_policy=policy,
        ledger_llm_calls=len(led),
        ledger_tool_calls=sum(e.get("tool_calls_requested") or 0 for e in led),
        requests_sending_tool_choice_none=sum(
            1 for e in led if e.get("tool_choice_received") == "none"),
        requests_sending_any_tool_choice=sum(
            1 for e in led if e.get("tool_choice_received") is not None),
        requests_with_tools_absent_or_empty=sum(
            1 for e in led if not e.get("tools_present")),
        honoured_total=sum(1 for e in led if e.get("tool_choice_honoured")),
        honoured_via_tool_choice_none=via_tc,
        honoured_via_tools_absent=via_no_tools,
        # `actual_llm_calls` / `actual_tool_calls` are the attribute names on the
        # runner result object, which is what harness.py reads. An earlier
        # revision of this script asked for `llm_calls` / `tool_calls`, got None
        # for every cell, and would have recorded "the framework reported
        # nothing" when in fact every framework reported a number.
        framework_reported_llm_calls=getattr(r, "actual_llm_calls", None) if r is not None else None,
        framework_reported_tool_calls=getattr(r, "actual_tool_calls", None) if r is not None else None,
        stopped_by=getattr(r, "stopped_by", None) if r is not None else None,
        ledger_path=str(LEDGER_DIR / f"{fw}-{policy}.json"),
    )
    if err:
        out["error"] = err
    return out


ALL_FRAMEWORKS = ("agno", "openai_agents", "semantic_kernel", "crewai")
DEFAULT_OUT = pathlib.Path("results/S2-toolchoice-2026-10-04.json")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="S2 re-run under both tool_choice policies.",
        epilog="To reproduce one cell without touching the committed artefact: "
               "--frameworks crewai --out /tmp/mine.json --ledger-dir /tmp/mine-ledgers",
    )
    ap.add_argument("--frameworks", default=",".join(ALL_FRAMEWORKS),
                    help="comma-separated subset (default: all four)")
    ap.add_argument("--out", type=pathlib.Path, default=None,
                    help=f"results path (default: {DEFAULT_OUT})")
    ap.add_argument("--ledger-dir", type=pathlib.Path, default=None,
                    help=f"ledger directory (default: {LEDGER_DIR})")
    a = ap.parse_args(argv)
    sel = [f.strip() for f in a.frameworks.split(",") if f.strip()]
    unknown = [f for f in sel if f not in ALL_FRAMEWORKS]
    if unknown:
        ap.error(f"unknown framework(s) {unknown}; choose from {list(ALL_FRAMEWORKS)}")
    if not sel:
        ap.error("--frameworks selected nothing")
    # A PARTIAL run must not overwrite a FULL artefact. Writing one cell over an
    # eight-cell file destroys the other seven silently, and the driver used to
    # write the committed path unconditionally with no way to redirect it.
    if a.out is None and set(sel) != set(ALL_FRAMEWORKS):
        ap.error(
            f"refusing to write the committed artefact from a partial run "
            f"({len(sel)} of {len(ALL_FRAMEWORKS)} frameworks). Pass --out "
            f"(and --ledger-dir) to write elsewhere, or run all of them."
        )
    a.frameworks = sel
    a.out = a.out or DEFAULT_OUT
    a.ledger_dir = a.ledger_dir if a.ledger_dir is not None else LEDGER_DIR
    return a


async def main(args=None):
    args = args or parse_args()
    telemetry_env = silence_framework_telemetry()
    ledger_dir = args.ledger_dir
    sp = "scenarios/S2-budget-exhaustion.yaml"
    sc = yaml.safe_load(pathlib.Path(sp).read_text())
    ledger_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for fw in args.frameworks:
        mod = __import__(f"runners.runner_{fw}", fromlist=["run"])
        for policy in ("ignore", "honour"):
            port = free_port()
            proc = start(port, policy, sp)
            r, err = None, None
            try:
                r = await mod.run(sc, f"http://127.0.0.1:{port}", 3)
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:140]}"
            try:
                led = ledger(port)
            except Exception as e:
                led = []
                err = (err or "") + f" | ledger unreadable: {type(e).__name__}"
            (ledger_dir / f"{fw}-{policy}.json").write_text(json.dumps(led, indent=2))
            out[f"{fw}/{policy}"] = summarise(fw, policy, led, r, err)
            proc.kill()
    # Every field below is computed from the run. Nothing is hand-entered, and
    # no field is carried over from results/S2-executed.json — that file is a
    # hand transcription whose `actual_*` namespace collapsed the harness's own
    # framework_reports/ground_truth split, which is the defect this file
    # exists to avoid repeating.
    doc = {
        "scenario": "S2-budget-exhaustion",
        "executed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "preregistration": "PREREGISTRATION-S2-tool-choice-2026-10-04.md",
        "driver": "experiments/S2_toolchoice_rerun.py",
        "mock_server": "mock-llm/server.py with scenarios/S2-budget-exhaustion.yaml "
                       "(10 turns: 9 tool + 1 text), run once per cell",
        "budget_limit": 3,
        "provenance": "executed; every numeric field in `cells` is read from a "
                      "persisted ledger or from the runner result object",
        "schema": {
            "ledger_llm_calls": "len(ledger). Observed: one entry per request the "
                                "mock served. Ground truth.",
            "ledger_tool_calls": "sum of tool_calls_requested across ledger entries. "
                                 "Observed. Ground truth.",
            "framework_reported_llm_calls": "result.actual_llm_calls, the count the "
                                            "framework itself reports. Counted, not observed.",
            "framework_reported_tool_calls": "result.actual_tool_calls. Counted, not "
                                             "observed. May disagree with ledger_tool_calls; "
                                             "that disagreement is the finding, not an error.",
            "stopped_by": "the framework's own description of why it stopped. Counted.",
            "requests_sending_tool_choice_none": "ledger entries whose "
                                                 "tool_choice_received == 'none'. Observed.",
            "requests_with_tools_absent_or_empty": "ledger entries with no tools array. Observed.",
            "honoured_via_tool_choice_none": "entries the mock honoured BECAUSE "
                                             "tool_choice was 'none'. Observed.",
            "honoured_via_tools_absent": "entries the mock honoured because `tools` was "
                                         "absent or empty. Observed. This is a SECOND and "
                                         "independent trigger in server.py; an aggregate "
                                         "`honoured` count conflates the two, and a cell whose "
                                         "honour count comes only from this trigger carries no "
                                         "evidence about tool_choice at all.",
            "ledger_path": "the persisted ledger this row was computed from.",
            "no_modelled_fields": "This file deliberately carries no counter_at_budget_stop, "
                                  "unit_observed or mock_confirmed_calls. No runner reads a "
                                  "framework's internal counter, so a field named for one "
                                  "would be the author's model rather than a reading.",
        },
        "mechanism_schema": {
            "purpose": "R6 states that a declared budget is not an enforced budget. "
                       "These rows say what each framework's limit actually rests on, "
                       "derived from its own ledgers by classify_mechanism() rather "
                       "than assigned by hand. There is no `enforced` boolean here: "
                       "results/S2-executed.json has one and no code produces it.",
            "local_stop": "Stopped without signalling the provider. The limit does not "
                          "depend on the counterparty at all.",
            "client_side_refusal": "Was handed a tool call by the non-compliant provider "
                                   "and did not execute it. The limit holds against a "
                                   "counterparty that ignores it.",
            "cooperative_request": "Asked the provider to stop via tool_choice=none and "
                                   "executed what came back. The limit holds only if the "
                                   "counterparty cooperates.",
            "why_two_policies": "Only the non-compliant provider can distinguish a refusal "
                                "from a request, because a conformant one satisfies both.",
        },
        "field_provenance": {
            "vocabulary": ["ledger", "harness_counter", "framework_api",
                           "declared", "modelled", "hand_authored"],
            "fields": PROVENANCE,
            "framework_reported_llm_calls_by_framework": {
                fw: _llm_calls_provenance(fw) for fw in sorted(DIST)},
            "note": "No field in this file is `hand_authored` or `modelled`. "
                    "`framework_api` applies only to `stopped_by`. Two field "
                    "names are misnomers and are kept because they are cited: "
                    "`framework_reported_tool_calls` is a harness counter, and "
                    "`framework_reported_llm_calls` is ledger-derived or "
                    "declared depending on the runner, never a framework "
                    "counter.",
        },
        "mechanisms": classify_mechanism(out),
        "environment": {
            "framework_telemetry_suppressed": telemetry_env,
            "note": "Set by the driver before any runner is imported. CrewAI "
                    "exports spans to telemetry.crewai.com unless opted out, "
                    "which adds a network dependency and a retry delay to a "
                    "run whose ground truth is the mock's request ledger. "
                    "Cells recorded before 2026-10-08 were produced WITHOUT "
                    "these set, with the export failing; an independent "
                    "replication reproduced them under that condition, so the "
                    "values do not depend on it.",
        },
        "cells": out,
    }
    # /tmp/rr3.json used to be written here too -- a scratch path from the
    # original session, left in a driver the README offers as the reproduction
    # path. Removed rather than parameterised; nothing reads it.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"\nwrote {args.out}")


# Guarded, because importing this module used to RUN the whole experiment --
# which rewrote results/ as a side effect of `import`. Discovered while
# exercising start()'s new ownership check from a test harness.
if __name__ == "__main__":
    asyncio.run(main(parse_args()))
