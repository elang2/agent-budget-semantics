# Errata

Corrections to figures in published, immutable artefacts. A Zenodo deposit's
description and files cannot be edited after minting, so a figure that was
wrong at deposit time stays wrong at that DOI forever. This file is the
correction of record, and it is the reason it exists rather than a quiet edit
to the repository.

Each entry names the superseded figure, the figure that replaces it, the test
that pins the replacement, and where the uncorrectable copy still sits.

---

## E1. Chargeback divergence stated as 2.3x; the measured spread is 2.6363x

| | |
|---|---|
| Superseded figure | `2.3x` max/min chargeback divergence |
| Correct figure | **`2.6363x`** (0.33834 for swarm against 0.12834 for agno) |
| Pinned by | `tests/test_cost_divergence.py::TestCalculateCostPerFramework::test_chargeback_divergence_paper_workload` |
| Minted copy | the v0.5.0 **software** deposit description, DOI [10.5281/zenodo.22605741](https://doi.org/10.5281/zenodo.22605741). **Repairable in place** — Zenodo permits metadata edits on a published record under the same DOI, so this is a figure that *was minted with* the error, not one that cannot be corrected. Two corrections to this row on 2026-10-04: the DOI (see below) and the editability. |
| Corrected in repo | `cost_divergence.py` module docstring; `.zenodo.json` description, which applies to the next version only |

**Correction, 2026-10-04 — this entry named the wrong record.** The DOI given above was
`10.5281/zenodo.22119569`, which is the **preprint** ("Budget Enforcement Semantics Diverge Across
AI Agent Frameworks: An Empirical Study", resource type Preprint). Fetched from the Zenodo API: its
description contains neither `2.3x` nor `2.6363`, so it was never the uncorrectable copy. The
record that does carry `2.3x` is `10.5281/zenodo.22605741`, the v0.5.0 **software** deposit
(`agent-budget-semantics`, resource type Software, version v0.5.0). An errata entry that points at
the wrong artefact sends a reader to check a claim against a record that does not contain it, which
is worse than the original error because it looks like diligence. Both records were fetched and
their descriptions searched before this correction was written.

**Computation basis, disclosed rather than buried.** The 2.6363x figure is computed over the
modelled iteration-count vector in `cost_divergence.py`, in which the non-enforcing framework is
scored at its tool-call count. That framework emitted no counter at runtime, so the value standing
in for it there is a model output and not a measurement. This is the same substitution that
`results/S2-executed.json` now refuses, where that cell reads `status: uninformative`. The figure is
therefore a point descriptor of one synthetic per-iteration chargeback model over an eleven-row
vector, not a measured spread over informative rows, and it is not provider-billed. Recomputing it
over informative rows only would change a test-pinned constant and is tracked as follow-up work
rather than done here.

**What went wrong.** Two different numbers were conflated. The module
docstring carried an illustrative example — one framework reporting 3 budget
units against another reporting 7, at $0.03 per unit — whose ratio is 7/3, or
2.33x. That worked example was reported as though it were the measured spread.
The measured spread comes from `calculate_cost_per_framework` on the reference
workload (4 LLM calls, 3 tool calls, 300 input and 178 output tokens, the
`enterprise-chargeback` pricing model) and is 2.6363x across the 11
frameworks. The two are now stated separately and the illustrative pair is
labelled as an illustration.

**Why it survived to publication.** The assertion that should have caught it
read `assert costs`, which is true for any non-empty result and computed no
ratio at all, so the docstring figure was never checked against the code it
described. The test now pins the endpoints and the ratio exactly, so a pricing
table or iteration-count edit fails loudly instead of drifting.

**Scope of the correction.** The direction and the cause of the finding are
unchanged: a per-iteration chargeback rate applied uniformly across
framework-reported counts diverges substantially, and the divergence traces to
iteration-count disagreement rather than to token pricing. Only the magnitude
was misstated, and the corrected magnitude is larger than the published one.

**The figure is synthetic.** `enterprise-chargeback` is a constructed pricing
model, not any vendor's published rate card, and the divergence it produces is
a property of the counting disagreement rather than a bill anyone has
received. The word carries weight in both the deposit description and here;
the figure should not be cited as an observed cost.

---

## E2 — ground-truth token total given as 478 where the measured value is 800

**Status.** Corrected in the repository on 2026-10-04. The v0.5.0 Zenodo deposit description
is minted and still reads "four LLM calls, three tool calls, 478 tokens"; a minted description
cannot be edited, so this entry is the correction of record, on the same precedent as E1.

**What the figure should be.** The S2 scenario's per-turn token sums are derivable from
`scenarios/S2-budget-exhaustion.yaml`: turns one to four are 125, 175, 225 and 275, so the
four-call ground-truth workload is **800 tokens**. Three turns give 525 and all ten give 3505.
Running `harness.py` against S2 reads 800 from the mock's request ledger for that workload.
478 appears nowhere in the scenario.

**Where 478 came from.** It is the total of the cost model's reference workload, which is a
different workload used for the chargeback comparison, not the budget-exhaustion run. It
reached `ground_truth.total_tokens` in `results/S2-executed.json` and propagated from there
into the README scenario heading, the divergence-matrix header, `reports/report.json`, four
call sites that pass it as an argument, the CI gate, and the deposit description.

**Scope of the correction.** No finding moves. Regenerating the full report suite under 478
and under 800 and diffing the output gives four differing lines, every one of them the figure
itself: the divergence-matrix header and the `report.json` ground-truth block. Nothing that
computes a consumed value, a utilization or a cost reads it. The amendment log in
`results/S2-executed.json` records the change as entry 3 with the derivation.

**Why it survived to publication.** It was pinned by a test named `test_tokens_is_478`, which
asserted the stored value equalled the literal in its own name. That is a tautology: the test
could only fail if someone changed the field, and it carried no derivation from the scenario
the field describes. It is now `test_tokens_is_800_the_measured_ledger_total` and states where
800 comes from. A constant pinned against itself is not a check.

**A second discrepancy found while tracing it — and the claim first made about it was wrong.**
The cost model's reference split is stated two ways in the repository, both totalling 478:
`cost_divergence.py:205-206` codes `input_tokens=350` and `output_tokens=128`, while E1 above
gives "300 input / 178 output". An earlier revision of this paragraph said "every published cost
figure is computed from the coded values, so no cost number is affected". **That is false, and the
one figure it exempted is the only one affected.** Measured by executing
`calculate_cost_per_framework` under both splits with the `enterprise-chargeback` model:

| reference split | cheapest | dearest | ratio | per-run spread |
|---|---|---|---|---|
| 300 in / 178 out | 0.12834 | 0.33834 | **2.6363x** | 0.21000 |
| 350 in / 128 out | 0.12734 | 0.33734 | **2.6491x** | 0.21000 |

**The published ratio, 2.6363x, is computed on the 300/178 split**, which is also what
`tests/test_cost_divergence.py:124` and `:144` pin. The README's printed cost table uses the coded
350/128 basis, so a reader dividing `$0.3373` by `$0.1273` gets 2.6491x and finds a figure this
file does not state — exactly the issue E1 exists to pre-empt. A second test,
`tests/test_report_generation.py:601`, pins the other split, so two passing tests currently rest on
two different reference workloads.

**Resolution: 300/178 governs the ratio, because it is the basis already minted**, and the
divergence is disclosed here rather than silently moved. The 2.6491x figure is correct for the
printed table and is recorded above so nobody has to re-derive it and wonder which is wrong. The
docstring at `:14` was changed from 300/178 to 350/128 on 2026-10-04 to match the code, which was
the right fix for the docstring and does not change which basis the published ratio uses.

**What is genuinely unaffected, verified under both splits:** the per-run spread is `0.21000`
either way, so the `$6,300` monthly and `$75,600` annual figures in the README and in the CLI
output are identical on both bases and need no correction.

**Addendum, 2026-10-04 — the disclosure above named only Agno, and the model is wider than that.**
`cost_divergence.FRAMEWORK_ITERATION_COUNTS` is the source-reading model for every row, not just
the one row E1 discusses, and at least two of its entries disagree with what execution showed.
LlamaIndex is counted at tool cycles, where amendment 1 in `results/S2-executed.json` records
`max_iterations` counting LLM responses. Agno is counted at tool cycles, where it emitted no
counter at all and ran to ten LLM calls under a declared limit of three. `autogen` and `langgraph`
are counted at `llm + tools`, which is the pre-correction prediction for both.

The 2.6363x ratio is unchanged by this, and so is the direction of the finding: the ratio is
between the model's own endpoints and is a property of the declared counting rules. What was
incomplete is the disclosure. The minimum, 0.12834, is shared by six rows rather than being one
framework's figure, and the comparison should be read as what these eleven counting rules would
bill for one workload, never as what eleven runs did cost. The README cost block now says so, and
the figures there are the ones the CLI prints.

**Also corrected, 2026-10-04.** The README cost block had been stale for long enough to disagree
with the code in every figure: it listed four frameworks against the eleven the CLI prints, and an
annual spread of $97,200 against the $75,600 the code computes. A test now derives the spread from
`cost_divergence` and asserts the README states it, so the block cannot drift again.

---

## E3 — the append-only amendment log was edited in place

**Status.** Recorded here on 2026-10-04. Not reversible: the edit is in the published history and
the correct remedy is disclosure, not a rewrite.

**What happened.** `results/S2-executed.json`'s amendment log declares its own invariant, quoting
the `mutations.jsonl` stream of arXiv:2605.12131: "Entries here are never edited or removed; a
correction is a new entry with a higher sequence." Between commits `3621bf2` and `2b52abd` the
sequence-1 entry was edited in place. Its `created_at` changed from `2026-08-23` to `2026-10-03`
and a `note` key was added.

**The edit was itself a correction, which is what makes it worth recording.** `2026-08-23` was the
date of the run the amendment describes, not the date the amendment was written, and backdating an
append-only entry to the event it documents defeats the point of the log. So the content became
more accurate while the method contradicted the rule stated three lines above it. A new entry with
a higher sequence would have achieved the same accuracy and left the original legible.

**What has changed since.** Amendments 2 and 3, added 2026-10-04, were appended. Amendment 2
deliberately leaves the wrong `verification` block verbatim and corrects it from a sibling
`verification_tombstone`, for exactly this reason. Amendment 3 carries its own derivation. Both
were written by a script that reads the whole file, appends, and then verifies that no pre-existing
leaf changed value before writing — 219 leaves checked on amendment 2, and the write refuses
outright if any differ. A test now also asserts the log's sequences are 1..N with no gaps or
repeats, so a renumber or a silent rewrite fails the suite.

**The general lesson, which this repository has now hit twice.** A document that declares its own
construction rule is bound by that rule while it is being written, not only when it is being read.
The other instance is the test that asserted a stored constant equalled the literal in its own
name; see E2.

---

## E4 — the published preprint carries both retracted claims in its body

**Status.** Recorded 2026-10-04. The preprint PDF is minted under
[10.5281/zenodo.22119569](https://doi.org/10.5281/zenodo.22119569) (`agent-budget-paper-v1.pdf`,
74,564 bytes) and the file cannot be edited in place. This entry is the correction of record.
Downloaded and text-extracted in full (42,345 characters) rather than reasoned about from the
record description, which is a separate artefact and separately wrong.

**Four passages locate the failure inside Agno's own control flow.** Quoted verbatim:

1. "the enforcement code fires but the outer loop does not observe its signal, producing a runtime
   path that terminates only when an external factor intervenes" — Section 2, on *When Agents Do
   Not Stop*.
2. "Agno produces no counter value because its enforcement path fires but the outer loop ignores
   it" — Section 5 results.
3. "The field exists, propagates to the model, and the enforcement code fires, setting
   tool_choice='none' after the limit is reached. The outer agent loop does not respect the
   tool_choice change and continues calling the language model with tools regardless."
4. "fires the enforcement hook (tool_choice='none' after the limit is reached), and then keeps
   calling the language model with tools regardless because the outer loop does not check."

All four are wrong in the same way, and the pre-registered two-provider re-run of 2026-10-04
establishes why: the mock parsed only `model` and `stream` and never read `tool_choice`, so the
non-compliant party was the **provider**, not Agno's loop. Against a provider that honours
`tool_choice` the limit holds at 4 model calls and 3 tool calls. Agno's enforcement is a
cooperative request with no client-side refusal, which is a narrower claim and a better one — a
limit that depends on the counterparty is a declared limit. See
`results/S2-toolchoice-2026-10-04.json`, its eight per-request ledgers, and
`frameworks.agno.verification_tombstone` in `results/S2-executed.json`.

**A fifth passage carries the 478-token figure** as the ground truth: "the underlying work is
fixed at four language-model calls, three tool calls, and 478 tokens across the whole
conversation. That fixed cost is the ground truth against which each framework's reported figure
is compared." The S2 scenario sums to **800** over four turns. See E2.

**What the preprint got right, and the repository did not.** Its Section 5 already cited the
upstream record — `agno-agi/agno#8304`, `#9385`, and the closed-unmerged fix PR `#6993` — where
this README until today asserted that no upstream issue existed. That assertion was false and has
been corrected. The preprint's framing of those issues as "the upstream bug" is itself too strong:
#9385 is `agno==2.8.7` and reports the opposite failure, in which Agno skips tool execution but
keeps relaying a user-supplied forced `tool_choice`. Three versions, three distinct failures of
one parameter; none of the upstream reports is the 1.2.5 mechanism, and none was filed by this
author.

**Why this matters more than the other entries here.** E1 through E3 concern a figure or a log. This
one concerns the paper's central causal claim about its headline framework, stated four times, in
the artefact a reader is most likely to cite. Any revision deposited under the concept DOI must
correct all five passages, and no draft, comment or section text may restate them.

---

## E5 — the `honour` mock returned a null final answer, and CrewAI was briefly misread because of it

**Status.** Found and fixed 2026-10-04, before any public claim rested on it. Nothing was
published carrying the wrong reading. Recorded because the wrong reading survived two rounds of
external review, and because the mechanism is worth knowing.

**The defect.** `--tool-choice-policy honour` suppressed a scripted tool call by setting
`tool_calls = None` and `finish_reason = "stop"`, then fell through to the single response-building
line, `message["content"] = scripted.get("content", "")`. Every tool-call entry in
`scenarios/S2-budget-exhaustion.yaml` carries `content: None` explicitly, so `.get` returned
`None` rather than the `""` default. The mock therefore answered a request with
`finish_reason: stop` and a **null content** — not a conformant provider, a malformed one.

**What it did to the measurement.** CrewAI 1.15.16 read the empty final answer as an unfinished
task and retried. Its ledger under `honour` shows three identical cycles of exactly three tool
calls each followed by a no-tools request: 10 requests, 7 tool calls. That was briefly recorded as
CrewAI exceeding a declared limit of 3 against a *conformant* provider, which would have been a
larger finding than the Agno result and would have falsified the general claim that the
declared-versus-enforced gap only appears against a counterparty that declines to cooperate.

It was none of those things. `max_iter=3` enforced correctly in every cycle — the three-tool-call
period in the ledger is the limit working. The repetition was this bug.

**Measured before and after**, same pinned versions, same scenario, only the mock changed:

| cell | before | after |
|---|---|---|
| `crewai/honour` | 10 LLM / 7 tool, `stopped_by: natural` | **4 LLM / 3 tool, `stopped_by: natural`** |
| every other cell | unchanged | unchanged |

`agno/ignore` 10/9, `agno/honour` 4/3, `openai_agents` 3/3 under both, `semantic_kernel/ignore`
4/4 and `/honour` 4/3 are all byte-identical across the fix, so **the Agno finding and the
three-mechanism taxonomy are unaffected**. The fix substitutes a non-empty final answer, and the
`ignore` path is untouched by construction.

**Two things this says about the method, which matter more than the row.**

A non-compliant counterparty was deliberately built as the stressor, and the risk of that design
is building one that is non-compliant in a way nobody intended. A null content was exactly that:
no framework asks for it, no provider emits it, and one of four frameworks changed behaviour
because of it. When a result appears only in the arm you modified, suspect the modification.

And the tell was in the data the whole time. A ledger showing 3 tool calls, a text turn, then 3
more and a text turn, then more, is a loop restarting — not a limit failing. A limit that fails
produces one long run, which is precisely what `agno/ignore` shows. The periodicity was visible in
the first ledger dump and was read past, twice, because the aggregate counts were read before the
per-request sequence.

**Credit where it is due.** The contradiction was flagged in review rather than by any gate: a
conformant provider should make a cooperative framework stop sooner, not later, and the executed
row for the same framework from 2026-08-23 says 4 model calls and 3 tool calls. No test in this
repository would have caught it, because every assertion was about agreement between artefacts and
this was two artefacts agreeing on a number the apparatus had produced.

**Separately, and found while tracing it:** `stopped_by: "budget_then_finalize"` in
`results/S2-executed.json`'s crewai row is emitted by no code path. `runners/runner_crewai.py` can
return only `natural`, `budget` or `error`. It is a fifth hand-authored value alongside
`counter_at_budget_stop`, `unit_observed`, `mock_confirmed_calls` and `enforced`, and the string
appears nowhere else in the repository. Today's runs give `error` under `ignore` and `natural`
under `honour` for that cell, so the recorded stop reason is neither reproducible nor producible.
