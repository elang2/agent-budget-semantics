# S2 two-arm measurement — autogen, langchain, langgraph, llamaindex

**This is a measurement report, not a pre-registration, and the distinction is the first thing it
has to say.** An earlier version of this file was written as a pre-registration and committed on
2026-10-13 before any run. It could not be executed as written, for a reason found by auditing the
apparatus rather than by running it: the driver could not express the budget values the predictions
named. By the time the driver was correct, a feasibility probe had already produced the cell values.
So the ordering that makes a pre-registration worth anything is not available for this run, and no
claim of it is made. What is pre-registerable from here is recorded in §7.

Requested on [issue #1](https://github.com/elang2/agent-budget-semantics/issues/1#issuecomment-6139670075):
run the remaining four frameworks against both counterparty arms, so that vectors built on this data
do not rest on the 2026-08-23 run, whose counterparty behaviour was never declared.

---

## 1. The headline result

**For all four frameworks, the counterparty arm is unreachable — at every budget the scenario
declares.** Measured, both arms, every cell: `requests_sending_tool_choice_none: 0`,
`requests_with_tools_absent_or_empty: 0`, `honoured_total: 0`.

This is not "the arms happen to agree". It is structural, and the mechanism is worth stating because
it sharpens the R6 distinction rather than adding a null to it.

`mock-llm/server.py` honours a stop only when the scripted turn carries tool calls **and** the
request either sets `tool_choice: none` or omits `tools`. `scenarios/S2-budget-exhaustion.yaml` is
nine tool turns followed by one text turn at turn 10. All four of these frameworks are hard-stoppers:
they halt *at* the budget and never issue a final summarising request. So they never produce a
toolless request, and the arm cannot act on them.

Raising the budget does not fix it. At the scenario's second declared value the counts move and the
zeros do not:

| framework | budget 3 / 6 | budget 5 / 10 | `tool_choice: none` | toolless requests |
|---|---|---|---|---|
| autogen | 2 llm / 2 tool | 4 / 4 | 0 at both | 0 at both |
| langchain **(at pin)** | 3 / 3 | 5 / 5 | 0 at both | 0 at both |
| langgraph | 3 / 3 | 5 / 5 | 0 at both | 0 at both |
| llamaindex | 3 / 3 | no second value declared | 0 | 0 |

**Provenance of this table. Every reading in it is now committed; it was not when this file was
first written.** The budget 3 / 6 column is `results/S2-toolchoice-four-frameworks-2026-10-13.json`,
whose eight cells are all at the first declared budget. The budget 5 / 10 column and both langchain
rows are `results/second-budget-2026-10-14/`, three driver outputs copied verbatim and verified
byte-identical to what the driver wrote. langchain's figures are from a pinned environment in both
columns, because in the main environment every langchain cell is `0 / 0 / error` — see §2.

**Tombstone, corrected 2026-10-14.** This paragraph previously read "two of its columns are not
committed… the budget 5 / 10 column is not committed anywhere… both were run to scratch paths".
That was accurate when written and became a liability immediately: the scratch outputs did not
survive, so a search of the authoring machine found **no** artefact carrying a `budget_value` of 5
or 10 for any framework, and the three figures in the paragraph above it were a recollection rather
than a reading. They were re-run and committed instead of being reworded, and they reproduced
exactly, including langchain at pin. This is the failure mode the project tombstones repeatedly —
prose outliving the artefact it describes — reached here by writing down a number whose evidence was
in `/tmp`. **Write a cell to a committed path or do not cite it.**

Reaching the text turn needs a budget above nine, at which point the budget is no longer the thing
under test. **So the counterparty arm and a hard stop shorter than the script are in tension**: the
arm only reaches a framework that continues past its limit (agno) or that takes a free final turn
(crewai, semantic-kernel, which is where their `honoured_via_tools_absent: 1` comes from).

**Consequence for a conformance corpus.** These four need one arm, not two. A budget-enforcement
vector built on them cannot distinguish `ignore` from `honour`, so the eight cells carry four cells
of information. The arm dimension is load-bearing only for the three frameworks that already have it.

## 2. Cells

Main environment (Homebrew CPython 3.13.7, `openai 3.8.0`):

| cell | budget | ledger llm/tool | framework llm/tool | `stopped_by` | mechanism |
|---|---|---|---|---|---|
| autogen/ignore · honour | 3 | 2 / 2 | 2 / 2 | `budget` | `local_stop` |
| langgraph/ignore · honour | 6 | 3 / 3 | 3 / 2 | `natural` | **withheld** |
| llamaindex/ignore · honour | 3 | 3 / 3 | 3 / 2 | `budget_exceeded` | **withheld** |
| langchain/ignore · honour | 3 | 0 / 0 | 0 / 0 | `error` | `unclassifiable_run_errored` |

Isolated environment at pinned versions (`openai 1.109.1`, `langchain 0.3.14`, `langchain-openai
0.3.2`, `autogen-agentchat 0.4.7`, `autogen-ext 0.4.7`):

| cell | budget | ledger llm/tool | framework llm/tool | `stopped_by` | mechanism |
|---|---|---|---|---|---|
| autogen/ignore · honour | 3 | 2 / 2 | 2 / 2 | `budget` | `local_stop` |
| langchain/ignore · honour **(at pin only)** | 3 | 3 / 3 | 3 / 3 | `budget` | `local_stop` |

**langchain is void in the main environment and valid only at pin.** `langchain 1.3.16` removed
`AgentExecutor` from `langchain.agents`, so the runner's import fails and the cell records
`0 / 0 / error`. The captured error string says so verbatim, which is new — see §4.

**Three of four reproduce 2026-08-23 exactly** on both counts: autogen 2/2, langgraph 3/2,
llamaindex 3/2. langchain reproduces 3/3 at pin. No cell contradicts the baseline.

**autogen was measured in both environments and gave the same answer**, 2/2/`budget`. That is the
cross-environment control this run needed and did not originally plan: the two-interpreter split is
the design's largest declared weakness, and on the one framework that can be run on both sides of it
the split moves nothing. One framework is not a general result, but it is the only such evidence
available and it points the right way.

## 3. Two labels withheld rather than published wrong

`classify_mechanism` derives `declined = ledger_tool_calls - framework_reported_tool_calls` and reads
any positive difference as `client_side_refusal`. For langgraph and llamaindex that difference is 1,
and neither declined anything. The gap is where in the cycle the counter fires —
`runners/runner_llamaindex.py` states it in its own docstring: *"The counter fires BEFORE tool
dispatch, so on the Nth iteration tools are never executed."*

Publishing `client_side_refusal` for them would certify a mechanism they do not have, in the one
field the R6 claim rests on and the one a corpus builder would consume. Both are withheld, with the
reason carried in the cell. Distinguishing a refusal from a pre-dispatch stop needs a signal this
design does not collect — whether the framework issued any request *after* the one whose tool call
went unexecuted — and that is a design change, not a relabelling.

**The classifier's logic for the original four is untouched.** Verified by re-running them: all four
published labels are byte-identical (`cooperative_request`, `unclassifiable_run_errored`,
`local_stop`, `client_side_refusal`). No published label moves.

## 4. Driver defects found and fixed, with what each would have produced

Found by auditing the apparatus against the plan. Each would have written a plausible-looking wrong
number rather than failing.

Seven rows below against "five driver defects" in the commit title: the last two are missing
metadata and a `.gitignore` line rather than defects that would have corrupted a cell.

| # | Defect | What it would have produced |
|---|---|---|
| 1 | Budget hardcoded `3` at the call site; the driver never read `budget_configs`, which only `harness.py` did | langgraph at 3 instead of 6, returning 2/1 — read as a failed replication of 2026-08-23, diagnosed as "the pin is not reproducing", when the cause was the driver |
| 2 | `DEFAULT_OUT` guard compared against `ALL_FRAMEWORKS` | extending that tuple inverted it: an eight-framework run would default straight over the committed four-cell artefact and its eight ledgers |
| 3 | `ledger_path` built from the module constant, not `args.ledger_dir` | every new cell pointing at a file that is not there |
| 4 | The runner's own `error` was dropped; only the driver-caught exception was kept | llamaindex's `WorkflowRuntimeError: Max iterations of 3 reached!` — the evidence the limit fired — recorded as `error: null` |
| 5 | `_within_declared_range` read `md.requires(DIST[fw])`, and all four frameworks declare no openai dependency | `null` for all eight new cells, in the field that exists to flag an out-of-range SDK. After the fallthrough to the sibling adapter, **six of the eight carry a value and two do not**: it reports `False` for llamaindex, which is a real violation (`openai 3.8.0` against `llama-index-llms-openai`'s `<3`), and `True` for langchain and langgraph, but autogen's two cells are **still `null`**, because `autogen-ext` declares `openai` only under its `openai` extra and the function deliberately skips a markered requirement. The field is therefore repaired for three of the four frameworks, not all four. Measured in the committed JSON; an earlier wording here implied the fix cleared every null |
| 6 | No interpreter, platform or wire-layer version in any artefact, baseline included | a reader could not tell that cells came from different environments |
| 7 | `.gitignore:14` `results/*.json` | the declared output file silently untracked |

One fix created a defect, which is worth recording because it is the pattern this repository keeps
hitting. Capturing the runner error (#4) routed llamaindex into `classify_mechanism`'s first branch,
`stopped_by == "error" or error`, and relabelled a working budget stop `unclassifiable_run_errored`.
Narrowed so an error string counts as a crash only when the stop was not a budget stop, after
verifying against the committed four that none of them carries an error string at all and so no
published label could move.

One test was rewritten rather than satisfied. `test_a_partial_run_cannot_overwrite_the_committed_artefact`
asserted `parse_args(ALL_FRAMEWORKS).out == DEFAULT_OUT`, commented "a full run still writes the
artefact". True while `ALL_FRAMEWORKS` was the four that artefact holds; with eight it demanded
exactly the overwrite the test is named after. It now asserts the invariant, that set and only that
set may default there, and that a superset is refused.

**Suite: 314 passed over 314 of the 321 collected tests.** The 7 not run are
`tests/test_mock_llm.py`, which hardcodes port 9222 and errors on this machine because
Chrome's remote-debugging port is listening there. That is pre-existing and unrelated to
this work, but it is a subset and the figure should not be read as the whole suite. An
independent run on Linux aarch64 reported 320 passed, 1 skipped and **0 failed** over the
full 321, the skip being openai-agents absent, which reconciles exactly. It reported the
same at both `17c11c608` and `3077a86`, so the 7 do not reproduce on a machine without the
port collision, which is the evidence that the cause is the environment and not the suite.
If you see 7 errors in `tests/test_mock_llm.py`, check what already holds port 9222.

## 5. Environment, measured and named

The earlier draft said two of the four could not be run at pin "in the working environment" and did
not name the interpreter. There are two, and the claim is true of one:

- **Homebrew CPython 3.13.7** — langgraph 1.2.11 and llama-index-core 0.14.24 at pin;
  autogen-agentchat 0.7.5 and langchain 1.3.16 drifted, the latter a major version.
- **the repo's `.venv/`** — autogen-agentchat 0.4.7, autogen-ext 0.4.7, langchain 0.3.14,
  langchain-openai 0.3.2, but no llama-index-core and no openai-agents, and agno 3.0.5
  rather than 1.2.5. **Corrected 2026-10-14: "all at pin" was true of the versions listed and
  false about what it implied, because langchain cannot run there.** That venv also holds
  `langchain-core 1.6.0`, while `langchain 0.3.14` declares `langchain-core>=0.3.29,<0.4.0`, so the
  constraint is unsatisfied and the import fails on `No module named 'langchain_core.memory'` —
  a different symptom from the main environment's missing `AgentExecutor`, the same cause. Measured:
  run in that venv as-is, langchain returns `0 / 0` with `stopped_by: error` at both budgets. The
  committed pinned cells therefore come from a venv built for them
  (`langchain-core 0.3.63`, `openai 1.109.1`); see `results/second-budget-2026-10-14/README.md`.
  Listing a package version is not evidence its dependency closure resolves. **The repository's
  own recipe is not at fault, which was measured rather than assumed**: `PINS.md` line 32,
  `pip install langchain==0.3.14 langchain-openai==0.3.2`, resolves `langchain-core 0.3.63` and
  `openai 1.109.1` in an empty venv and the runner imports. The constraint is only violated when
  those two go in alongside something that pulls a 1.x core, which `langgraph 1.2.11` and
  `langchain-openai 1.x` both do, and which is how this `.venv` reached 1.6.0.

**No single environment can hold all eight frameworks at pin.** `openai-agents` declares
`openai>=3,<4`, `crewai` `>=2.30,<3`, and `langchain-openai 0.3.2` `>=1.58.1,<2` — three mutually
exclusive ranges. This is a property of the dependency graph, not of this run, and `PINS.md` already
says as much: *"a single environment holding all eleven is not the environment any recorded result
was produced in."* Every cell now carries its own interpreter, platform and wire-layer versions.

An apparatus note, because it changed a conclusion. `python3 -I` reports `openai 2.54.0` and plain
`python3` reports `3.8.0`, because isolated mode excludes user site-packages. The experiment runs
under the latter. A range check performed with `-I` therefore described an interpreter the experiment
does not use, and got three frameworks' in-range status backwards.

## 6. Output discipline

Neither existing results file is edited. This run wrote
`results/S2-toolchoice-four-frameworks-2026-10-13.json` and
`results/ledgers/S2-toolchoice-four-frameworks-2026-10-13/`. The pinned-environment cells were
written to `/tmp` and are reported in §2 rather than committed, because committing a cell from an
environment the repository cannot reconstruct would assert a reproducibility this run does not have.

## 7. What is genuinely pre-registerable next, and what is not

Not pre-registerable: anything about these four at the budgets above. The numbers are measured and
this file reports them.

Pre-registerable, and worth doing:

1. **A budget above the script length**, to establish whether a hard-stopping framework that *does*
   reach a final summarising turn then issues a toolless request and becomes arm-sensitive. That is
   the open mechanism question §1 raises and cannot answer.
2. **A longer script**, which is the better form of the same experiment: it separates "stopped at the
   budget" from "ran out of script" without raising the budget past the thing under test.
3. **The post-unexecuted-call signal** that would let `classify_mechanism` tell a refusal from a
   pre-dispatch stop, which would un-withhold the two labels in §3.

For any of those, push the pre-registration alone and before the apparatus change — not merely
before the run. The failure here was not that predictions were written late; they were committed in
`89596c4` before anything ran. It was that they described a driver that did not exist, and auditing
the apparatus is what caught it. A pre-registration that names values its own tooling cannot express
is not a commitment, it is a guess with a timestamp.
