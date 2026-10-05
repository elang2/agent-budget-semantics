# Pre-registration — S2 re-run under two `tool_choice` policies

**Written and committed before the run.** Everything below is a prediction. Anything that disagrees
with it after execution is a finding, not a description, and is recorded as such.

Authored 2026-10-04. Triggered by a third-party audit of commit `aa5a5db`, which observed that
Agno 1.2.5 sends `tool_choice="none"` after hitting its limit while the mock never reads it.

---

## 1. What the mock actually does today, measured

Read directly from `mock-llm/server.py` before writing this file, because the audit's hypothesis
about it was wrong in a way that changes the expectations.

The request handler parses **`model` and `stream` and nothing else**. It never reads `tools` and
never reads `tool_choice`; a grep for either across every `.py` in the repo returns nothing. Turn
selection is `get_next_response()`, a pure script-index advance whose only early-exit is script
exhaustion.

**So the mock branches on nothing.** The audit suggested it "already branches on something, probably
the absence of a `tools` array". It does not. That matters for what follows.

## 2. The consequence nobody had stated, and the reason this re-run is worth doing

`scenarios/S2-budget-exhaustion.yaml` entry 4 is `finish_reason: tool_calls` with a tool call and
no content. Semantic Kernel and CrewAI each made **four** model calls and ended with a text answer.

Since the mock cannot have offered them text on call 4, and did offer them a tool call, **they
received a tool call past their limit and declined to execute it.** That is client-side refusal.

Agno, given the same non-compliant mock, asked the provider to stop via `tool_choice="none"` and
then executed whatever came back.

That contrast is the R6 distinction measured inside one run, against one deliberately
non-compliant counterparty:

| | mechanism | behaviour when the provider ignores the limit |
|---|---|---|
| Semantic Kernel, CrewAI | client-side refusal | stops anyway |
| Agno 1.2.5 | cooperative request only | keeps going |

The mock's non-compliance is the **stressor**, not a confound. A conformant provider would hide the
difference, which is why the original run found it and why both modes must be kept.

## 3. Design

`--tool-choice-policy ignore|honour`, **default `ignore`**, so no existing result changes and the
2026-08-23 behaviour stays reachable and reproducible.

- `ignore` — today's behaviour, byte-identical.
- `honour` — when `tool_choice == "none"`, or `tools` is absent or empty, return the script's text
  turn with `finish_reason: stop` instead of the next scripted tool call.

Every ledger entry additionally records `tool_choice` as received, whether `tools` was present, and
the policy in force. Today the ledger cannot show the instruction was ever sent.

## 4. Predictions

| Framework | mode | `actual_llm_calls` | `actual_tool_calls` | limit held |
|---|---|---|---|---|
| **agno 1.2.5** | `ignore` | **10** | **9** | no |
| **agno 1.2.5** | `honour` | **4** | **3** | yes |
| openai-agents 0.22.0 | `ignore` | 3 | 3 | yes |
| openai-agents 0.22.0 | `honour` | 3 | 3 | yes |
| semantic-kernel 1.44.1 | `ignore` | 4 | 3 | yes |
| semantic-kernel 1.44.1 | `honour` | 4 | 3 | yes |

**Controls.** openai-agents must be identical under both modes. It never sends `tool_choice: none`,
so a mode that changes its numbers is a mode that does something it should not, and the run is void.

**Semantic Kernel is the interesting control.** It already refuses client-side, so `honour` should
change nothing for it. If it does change, the client-side-refusal reading in §2 is wrong.

**What each outcome means.**

- Agno at 4/3 under `honour` confirms cooperative enforcement. The finding becomes "a limit that
  depends on the counterparty's cooperation, with no client-side refusal", which is a better R6
  sentence than the one in the drafts and is true under both modes.
- Agno at anything other than 4 under `honour` is a **new and larger finding**: the limit fails even
  against a conformant provider.
- Agno not reproducing 10/9 under `ignore` means the 2026-08-23 run is not reproducible at the
  pinned version, which supersedes everything else here.

## 5. Environment, and what cannot be run

Measured against `PINS.md`: **5 of 11 pinned packages are not at the pinned version.**

At pin, so runnable: `agno 1.2.5`, `crewai 1.15.16`, `langgraph 1.2.11`, `llama-index-core 0.14.24`,
`openai-agents 0.22.0`, `semantic-kernel 1.44.1`.

Drifted or absent, so **not runnable at pin**: `anthropic` (0.39.0 → 1.4.0), `autogen-agentchat`
(0.4.7 → 0.7.5), `google-adk` (1.2.1 → 2.7.1), `langchain` (0.3.14 → **1.3.16**, a major version),
`openai-swarm` (absent).

**LangChain therefore cannot serve as a control in this run.** It was requested as one; it is at a
major version above the pin, and a result from it would not be comparable to 2026-08-23. The
substitute control is openai-agents, which is at pin. This is recorded here rather than discovered
afterwards.

## 5a. What attests the ordering, and what does not

**The ordering is evidenced by commit metadata only. No third party timestamps it.** Stated here
rather than left for a reader to find, because anyone who knows git will find it.

What is true: this file was added in `803c3e8` as the only change in that commit — one file, 114
insertions, no code and no results — and the `--tool-choice-policy` flag and every result file
arrived 18 minutes later in `68838b7`. `git merge-base --is-ancestor 803c3e8 68838b7` passes, so
the DAG order is fixed and cannot be rewritten without rewriting both commits.

What is **not** true is that anything outside this repository corroborates the 18 minutes. Both
commits reached GitHub inside a single bulk push, verified against the events API: 22 push events
are retained back to 2026-09-07 and **neither commit appears individually in any of them**, and the
retained payloads carry no commit lists at all. So GitHub holds a timestamp for when the push
arrived and nothing for when either commit was made. Commit dates are author-settable. A reader who
assumes only that git is honest gets the DAG ordering; a reader who wants an independent clock does
not get one here.

**What that does and does not weaken.** The predictions in §4 were fixed before the mechanism to
test them existed — the `honour` branch is in `68838b7`, so §4 cannot have been written against
results the code could not yet produce. That argument rests on content, not on timestamps, and it
survives. What does not survive is any claim of third-party attestation, and no such claim should be
made.

**Fixed for next time.** Push the pre-registration on its own, before executing, so the push event's
`created_at` timestamps it server-side. That costs one extra push and converts this from an
author-attested ordering into an externally attested one. It was not done here, and this run cannot
be retrofitted.

## 6. Output discipline

`results/S2-executed.json` is **not edited.** The re-run writes a new file carrying its own
`executed_at`, the mock policy, the ledger paths, and the resolved version of every framework it
ran. The harness emits every field the file carries.

`counter_at_budget_stop` is **not** reproduced under that name. No runner reads any framework's
counter; all seven values in the existing file equal the counting formula applied to the observed
counts. The new file names it `counter_modelled_at_stop` or omits it.

The existing file receives an **appended** amendment entry pointing at the new file, plus a
tombstone on its `verification` block, whose `enforcement_effective: False` and
`alternative_hypothesis_ruled_out` text rule out the wrong alternative — it never tested whether the
mock was the non-compliant party.
