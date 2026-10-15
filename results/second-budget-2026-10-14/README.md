# Second declared budget — committed cells, 2026-10-14

`MEASUREMENT-S2-tool-choice-four-frameworks-2026-10-13.md` §1 reported the second-budget
readings in prose and said they were run to scratch paths and committed nowhere. They were
then unverifiable: a search of this machine found no artefact carrying a `budget_value` of 5
or 10 for any of the three frameworks. This directory is those cells, re-run and committed,
so the claim rests on data rather than on a recollection.

**Nothing here was merged, edited or hand-authored.** Each JSON is the driver's own output
for one invocation, written straight to this directory by the driver with `--out` and
`--ledger-dir`, so every `ledger_path` field is a repo-relative path that resolves. Three
invocations means three files rather than one, because combining them would require a
transformation step whose correctness nobody could check against the driver.

An earlier staging of these files copied them from scratch paths instead, which left every
`ledger_path` pointing at a `/tmp` directory that is not in the repo — a dangling reference
inside committed data, which is the same defect in miniature as the one this directory
exists to fix. Re-run into the final location rather than patched, so the paths are the
driver's own and not a rewrite. All eight cells reproduced identically across the two runs.

| File | Cells | Framework | Budget | Interpreter |
|---|---|---|---|---|
| `autogen-langgraph-budget1.json` | 4 | autogen, langgraph | 5 (`max_turns`), 10 (`recursion_limit`) | Homebrew CPython 3.13.7, `openai 3.8.0` |
| `langchain-at-pin-budget0.json` | 2 | langchain | 3 (`max_iterations`) | separate pinned venv, `openai 1.109.1` |
| `langchain-at-pin-budget1.json` | 2 | langchain | 5 (`max_iterations`) | same pinned venv |

Ledgers for every cell are under `ledgers/<file-stem>/`.

## Results

| Framework | Budget | ledger llm/tool | framework llm/tool | `stopped_by` | arm counters | mechanism |
|---|---|---|---|---|---|---|
| autogen 0.7.5 | 5 | 4 / 4 | 4 / 4 | `budget` | 0 / 0 / 0 both arms | `local_stop` |
| langgraph 1.2.11 | 10 | 5 / 5 | 5 / 4 | `natural` | 0 / 0 / 0 both arms | **withheld** |
| langchain 0.3.14 **at pin** | 3 | 3 / 3 | 3 / 3 | `budget` | 0 / 0 / 0 both arms | `local_stop` |
| langchain 0.3.14 **at pin** | 5 | 5 / 5 | 5 / 5 | `budget` | 0 / 0 / 0 both arms | `local_stop` |

"Arm counters" is `requests_sending_tool_choice_none`, `requests_with_tools_absent_or_empty`
and `honoured_total`. All three are 0 in all eight cells here, under both
`--tool-choice-policy ignore` and `honour`. That is the headline of §1 holding at the larger
budget: the counts move and the zeros do not.

langgraph's `mechanism` is withheld at budget 10 for the same reason as at budget 6 — one of
five offered tool calls goes unexecuted because its counter fires before dispatch, which is a
counting artefact and not a declined call.

## langchain needed a venv built for it, and the reason is a correction

§5 of the report lists the repo's `.venv/` as holding `langchain 0.3.14` and
`langchain-openai 0.3.2` "all at pin". Both figures are right and the conclusion a reader
draws from them is not: **langchain cannot run in that venv.** It also holds
`langchain-core 1.6.0`, while `langchain 0.3.14` declares `langchain-core>=0.3.29,<0.4.0`, so
the constraint is unsatisfied and the import fails on `No module named
'langchain_core.memory'` — a different failure from the main environment's missing
`AgentExecutor`, same cause. This is a property of that one local environment and not of the
repository's instructions, which is why it is recorded here as a caution rather than as a bug:
the committed recipe is fine, and installing it into a non-empty environment is not.

So the pinned venv for these cells was built fresh. **`PINS.md`'s own recipe is sufficient and
was verified, so these cells are reproducible from the repository rather than only from the
machine that measured them.** Measured in an empty venv, `pip install langchain==0.3.14
langchain-openai==0.3.2` — exactly line 32 of `PINS.md`, pinning neither `langchain-core` nor
`openai` — resolves `langchain-core 0.3.63` and `openai 1.109.1`, and
`runners/runner_langchain.py` imports. `openai_sdk_within_framework_declared_range` then reads
`True`, where every langchain cell in the main environment reads it against an out-of-range SDK.

**The empty part matters and is the whole of the caveat.** `langchain 0.3.14` requires
`langchain-core<0.4`, so the recipe only resolves correctly into a clean environment. Installed
alongside anything that pulls a 1.x core — `langgraph 1.2.11` and `langchain-openai 1.x` both do —
the core is upgraded in place, the constraint is left unsatisfied, and the failure surfaces as a
broken import rather than as a dependency error. That is what happened to the repo's `.venv`.

A measurement worth keeping from the attempt that failed: run in the repo `.venv` as-is,
langchain returns `0/0` with `stopped_by: error` at both budgets — the arm counters are still
0, but for the trivial reason that nothing ran, which is not evidence about the arm.

## Independent replication

Every figure above was produced on a third machine before it was produced here — Linux
aarch64, CPython 3.13.15, `openai 3.30.0` for autogen and langgraph, and a separate pinned
venv at `openai 1.109.1` for langchain. All twelve cells agree with this directory on counts,
`stopped_by`, mechanism and all three arm counters. The cross-environment statement in the
report's §2 is therefore stronger than when it was written: it held for autogen on two
environments, and now holds for autogen, langgraph and langchain on three.
