> **SUPERSEDED, same day, before it was ever pushed. Read
> `MEASUREMENT-S2-tool-choice-four-frameworks-2026-10-13.md` instead.**
>
> This file is retained because it is the record that predictions were fixed before anything ran,
> which is the one thing about it that held. It must not be read as a description of what happened,
> and six of its claims are wrong:
>
> 1. **§3's "the whitelist and the distribution map, and nothing else" is false.** The driver
>    hardcoded the budget at the call site and never read `budget_configs`, so langgraph at 6 was
>    unreachable — this file predicted a value its own tooling could not express. Four more change
>    points were needed; they are enumerated in §4 of the measurement report.
> 2. **§4 named no interpreter, and there are two.** The repo's `.venv/` holds autogen and langchain
>    at pin, so "two of the four cannot be run at pin in the working environment" is true of the
>    Homebrew interpreter and false of the other. The real constraint is stronger: no single
>    environment can hold all eight at pin.
> 3. **§5's columns do not exist in the artefact.** It predicted `actual_llm_calls` /
>    `actual_tool_calls`; the output carries `ledger_*` and `framework_reported_*`, which diverge.
> 4. **§5's langgraph `stopped_by` silently normalised its own baseline.** The 2026-08-23 artefact
>    records `"natural (graceful at limit)"`, a string no code path emits — the defect ERRATA E5
>    already tombstones for crewai — and this file predicted `"natural"` while claiming to reproduce it.
> 5. **§5's "weak prediction" reasoning was wrong.** The pathway it called unobserved is recorded on
>    every ledger entry under both policies, so it is measured in the run's own first arm.
> 6. **§7 was written in the completed tense for an act never performed.** Nothing was pushed, and
>    the branch had diverged from `origin/main`, so the server-side timestamp it claimed as its
>    attestation did not exist.
>
> Found by auditing the apparatus against the plan rather than by running it. A pre-registration that
> names values its own tooling cannot express is not a commitment; it is a guess with a timestamp.

# Pre-registration — S2 two-arm run extended to autogen, langchain, langgraph, llamaindex

**Written and committed before the run.** Everything below is a prediction. Anything that disagrees
with it after execution is a finding, not a description, and is recorded as such.

Authored 2026-10-13. Requested on
[issue #1](https://github.com/elang2/agent-budget-semantics/issues/1#issuecomment-6139670075): run
the remaining four frameworks against both counterparty arms, so that vectors built on this data do
not rest on the 2026-08-23 run, whose counterparty behaviour was never declared.

Companion to `PREREGISTRATION-S2-tool-choice-2026-10-04.md`, which covers agno, crewai,
openai-agents and semantic-kernel. That file's design, mock semantics and output discipline apply
here unchanged and are not restated.

---

## 1. What is already measured, and what is missing

`results/S2-toolchoice-2026-10-04.json` carries eight cells over four frameworks:
`agno`, `crewai`, `openai_agents`, `semantic_kernel`, each under `ignore` and `honour`.

`results/S2-executed.json` (2026-08-23) carries all eight frameworks under one arm. Its mock never
read `tool_choice`, so it measured the `ignore` behaviour without declaring it. The four frameworks
missing a two-arm reading are therefore **autogen, langchain, langgraph, llamaindex**, which is
eight new cells.

## 2. Why the runner source cannot be used to predict the arm difference

This is the methodological point of this run, and it is stated first because it is the thing most
likely to be got wrong by anyone extending this work.

A grep for `tool_choice` across all 14 files in `runners/` returns **zero occurrences**,
including in `runner_agno.py` — and agno demonstrably sends `tool_choice: none` seven times under
`ignore`. The instruction is emitted by the framework, not written by the runner. **Runner source is
therefore non-predictive of wire behaviour, and no prediction below rests on it.**

The measured cells also show that `tool_choice: none` is not the only pathway. The `honour` branch
fires when `tool_choice == "none"` **or** when `tools` is absent or empty. Both semantic-kernel and
crewai send zero `tool_choice: none` and still register `honoured_via_tools_absent: 1`, and crewai's
`stopped_by` moves from `error` under `ignore` to `natural` under `honour`. So "this framework never
sends `tool_choice`, therefore its arms are identical" is false, and the openai-agents control in the
companion file holds for a narrower reason than it first appears: it sends no `tool_choice` *and*
never issues a request with absent tools.

**Consequence for this run.** The `ignore` arm is predicted from the 2026-08-23 measurements. The
`honour` arm is predicted equal to it, and that prediction is weak by construction, because the
pathway that would break it is wire behaviour this repository has not yet observed for these four.
`honoured_via_tools_absent > 0` in any new cell is a measured finding, not a deviation.

## 3. Design

No change to `mock-llm/server.py`, to `scenarios/S2-budget-exhaustion.yaml`, or to any runner.

`experiments/S2_toolchoice_rerun.py` currently whitelists four names in `ALL_FRAMEWORKS` and maps
four in `DIST`. Dispatch is already name-generic — `__import__(f"runners.runner_{fw}")` — so the
change is the whitelist and the distribution map, and nothing else:

```
ALL_FRAMEWORKS += ("autogen", "langchain", "langgraph", "llamaindex")
DIST["autogen"]    = "autogen-agentchat"
DIST["langchain"]  = "langchain"
DIST["langgraph"]  = "langgraph"
DIST["llamaindex"] = "llama-index-core"
```

Budget values follow the 2026-08-23 run: **3 for autogen, langchain and llamaindex, 6 for
langgraph**, because `recursion_limit` counts graph nodes rather than model calls and 6 is the
value that admits roughly three model-call pairs. Running langgraph at 3 would be a different
experiment and is not what this file predicts.

Two runs per cell, as `results/replication/` already does for the existing eight.

## 4. Environment, measured today, and the part that is not a clean comparison

Measured against `PINS.md` on 2026-10-13, in the environment that will run this:

| Package | Pinned | Installed | |
|---|---|---|---|
| `langgraph` | 1.2.11 | 1.2.11 | at pin |
| `llama-index-core` | 0.14.24 | 0.14.24 | at pin |
| `autogen-agentchat` | 0.4.7 | 0.7.5 | **drifted** |
| `autogen-ext` | 0.4.7 | 0.7.5 | **drifted** |
| `langchain` | 0.3.14 | 1.3.16 | **drifted, major version** |
| `langchain-openai` | 0.3.2 | 1.6.0 | **drifted, major version** |

So **two of the four cannot be run at pin in the working environment**, which is the same reading
the companion file recorded on 2026-10-04 and it has not improved. `langchain` at 1.3.16 against a
pin of 0.3.14 is a major-version gap, and the companion file already ruled it out as a control for
exactly this reason.

**What this run does about it.** autogen and langchain run in an isolated virtual environment with
the pinned versions installed, so that all eight cells are at pin and comparable to 2026-08-23. Both
pin sets were confirmed resolvable on Python 3.13.7 by a `pip install --dry-run` before this file was
written; neither was installed at that point.

**The declared limitation.** Those two cells come from a different interpreter process than the other
two, with a different dependency closure around them. That is recorded per cell as an environment
field rather than left for a reader to infer, and it is a weaker comparison than the four cells in
the companion file, which shared one environment. A reader comparing autogen or langchain against
agno is comparing across environments.

**Void condition.** If the isolated environment cannot reproduce the 2026-08-23 `ignore` numbers for
a framework, that cell is reported as not reproducible at pin rather than as a new value, and no
vector is built on it.

## 5. Predictions

`ignore` arm, predicted to reproduce 2026-08-23:

| Framework | version | budget | `actual_llm_calls` | `actual_tool_calls` | `stopped_by` |
|---|---|---|---|---|---|
| autogen | 0.4.7 | 3 | **2** | **2** | budget |
| langchain | 0.3.14 | 3 | **3** | **3** | budget |
| langgraph | 1.2.11 | 6 | **3** | **2** | natural |
| llamaindex | 0.14.24 | 3 | **3** | **2** | budget_exceeded |

`honour` arm, predicted identical to the `ignore` row for all four, on counts and on `stopped_by`.

**This is the weak prediction and it is labelled as such.** Eight of eight `honour` predictions
being right would mean none of the four issues a request with absent or empty tools, which is a
property of their wire behaviour that nothing here has measured. One or more moving is the expected
shape of a useful result.

**What each outcome means.**

- All four identical across arms: the arm variable does not reach these frameworks, and the R6
  distinction stays confined to agno's cooperative request plus the two tools-absent cases already
  measured. The corpus can use either arm for these four.
- Any cell where `honoured_via_tools_absent > 0`: the tools-absent pathway is broader than the two
  frameworks that currently show it, and a vector that only exercises a request carrying tools
  cannot distinguish these cells. This is the finding worth having.
- Any cell where `requests_sending_tool_choice_none > 0`: a second cooperative enforcer alongside
  agno, which changes the R6 count and is the largest result available here.
- An `ignore` arm disagreeing with 2026-08-23: either the pin is not reproducing or the mock's
  `ignore` branch is not byte-identical to the 2026-08-23 behaviour. That supersedes the arm
  comparison for that framework and is investigated before anything else in this file is reported.

## 6. Output discipline

Neither existing results file is edited. This run writes
`results/S2-toolchoice-four-frameworks-2026-10-13.json` carrying its own `executed_at`, the mock
policy per cell, ledger paths, the resolved version of every framework, and the environment
identifier for each cell. Replication runs go to `results/replication/`.

`results/S2-toolchoice-2026-10-04.json` receives an **appended** amendment entry pointing at the new
file. Its eight existing cells are not recomputed and not touched.

## 7. What attests the ordering

The companion file's §5a recorded that its ordering rests on commit metadata alone, and closed with:
"**Fixed for next time.** Push the pre-registration on its own, before executing, so the push event's
`created_at` timestamps it server-side."

That is done here. This file is pushed as the only change in its commit, before the driver change and
before any result exists, so the push event carries a server-side timestamp from GitHub that no
author can set. The commit that adds the four framework names to the driver, and every result file,
arrive in a later push.
