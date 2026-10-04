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
| Uncorrectable copy | the v0.5.0 **software** deposit description, DOI [10.5281/zenodo.22605741](https://doi.org/10.5281/zenodo.22605741) — **corrected 2026-10-04**, see the note below |
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

**A second, smaller discrepancy found while tracing it.** The cost model's reference split is
stated two ways in the repository, both totalling 478: `cost_divergence.py:205-206` codes
`input_tokens=350` and `output_tokens=128`, while the module docstring at `:14` and E1 above
both give "300 input / 178 output". Every published cost figure is computed from the coded
values, so no cost number is affected, but the prose and the code disagree about the split.

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
