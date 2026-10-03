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
| Uncorrectable copy | the v0.5.0 Zenodo deposit description, DOI [10.5281/zenodo.22119569](https://doi.org/10.5281/zenodo.22119569) |
| Corrected in repo | `cost_divergence.py` module docstring; `.zenodo.json` description, which applies to the next version only |

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
