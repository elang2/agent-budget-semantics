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
import asyncio, datetime as dt, json, pathlib, subprocess, sys, time, urllib.request
import importlib.metadata as md
import yaml

LEDGER_DIR = pathlib.Path("results/ledgers/S2-toolchoice-2026-10-04")
DIST = {"agno": "agno", "openai_agents": "openai-agents",
        "semantic_kernel": "semantic-kernel", "crewai": "crewai"}


def start(port, policy, scenario_path):
    p = subprocess.Popen([sys.executable, "mock-llm/server.py", f"--port={port}",
                          f"--script={scenario_path}", f"--tool-choice-policy={policy}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4)
            return p
        except Exception:
            time.sleep(0.2)
    p.kill()
    raise SystemExit(f"mock {port} never came up")


def ledger(port):
    d = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/ledger", timeout=5).read())
    return d if isinstance(d, list) else d.get("entries", d.get("ledger", []))


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
        framework_version=md.version(DIST[fw]),
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


async def main():
    sp = "scenarios/S2-budget-exhaustion.yaml"
    sc = yaml.safe_load(pathlib.Path(sp).read_text())
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    out, port = {}, 9800
    for fw in ("agno", "openai_agents", "semantic_kernel", "crewai"):
        mod = __import__(f"runners.runner_{fw}", fromlist=["run"])
        for policy in ("ignore", "honour"):
            port += 1
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
            (LEDGER_DIR / f"{fw}-{policy}.json").write_text(json.dumps(led, indent=2))
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
        "cells": out,
    }
    pathlib.Path("results/S2-toolchoice-2026-10-04.json").write_text(
        json.dumps(doc, indent=2) + "\n")
    pathlib.Path("/tmp/rr3.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print("\nwrote results/S2-toolchoice-2026-10-04.json")


asyncio.run(main())
