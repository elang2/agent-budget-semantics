# Roadmap

## Strategic position

This project is the only execution-based instrument for measuring what agent budget limits actually do. Papers compare from documentation. Operators guess from error messages. Frameworks ship enforcement code that doesn't enforce. We run the same work through every framework and report what the counter says.

Three constituencies route through this:
1. **Academic papers** cite it because it's the only executed comparison (our own source-code-derived predictions were wrong half the time)
2. **Frameworks** run it because it catches their regressions before users do
3. **Operators and regulators** quote it because it answers "does the limit actually work?"

Every roadmap item must serve at least one of these. Anything that serves none is scope creep.

---

## P0: Correctness of the artifact the OTel thread links to

### 0a. Per-column provenance in the headline table

The README's headline table marks rows as `executed` based on S2, but carries columns ("Parallel 3 tools," "Error retry," "Final answer") whose values could not have come from S2 (a sequential budget-exhaustion scenario). Those cells are modeled. Fix: add per-column footnotes distinguishing `executed (S2)` cells from `modeled` cells, or split the table.

### 0b. Pin matched-definition in schema

The 50% prediction accuracy (4/8) holds under both `@ground_truth` and `@budget_stop` comparands, but the set of correct predictions differs. Pin `prediction_matched_at_ground_truth` as the canonical definition. Add a `matched_definition` key to the schema. Note in the artifact that the aggregate is definition-stable while the membership isn't.

### 0c. Regenerate reports from S2-executed.json

`reports/` may carry values from the model era. Regenerate from current execution data or delete until they can be.

---

## P1: Execution that fills the claims

### 1a. Execute S4 (parallel tools) with 3x repetition

Three tools requested in one LLM response, budget=2. Does that consume 1 budget unit or 3? Run 3 times per framework; assert byte-identical results. This is the second headline finding and the strongest test of the "fully reproducible" claim.

### 1b. Execute S5 (error/retry) with 3x repetition

Failed tool call plus retry. Is that 1 unit or 2? Safety-critical for production agents that retry on transient errors.

### 1c. Promote headline table cells

After S4/S5 execution, the "Parallel 3 tools" and "Error retry" columns earn their `executed` label for real.

---

## P2: Category-defining artifact

### 2a. S6: Enforcement verification suite

The question regulators ask: "does the limit actually stop the agent?" Two executed findings already in hand:
- Agno: enforcement fires, loop ignores it (9 calls past limit of 3)
- Semantic Kernel: counter=3 at budget=3, but 4 LLM calls executed (undocumented free final-answer call)

One modeled finding (from source-code analysis, not yet executed):
- Swarm: 333% exceedance before termination

Generalize into: every limit type (iterations, tokens, time, cost) x does-it-actually-stop x can-it-be-evaded. The procurement language already exists in military governance literature: "verify budget enforcement cannot be bypassed."

### 2b. S7: Delegation conservation

Does delegated budget respect parent constraints? Agent A has budget=5, delegates to Agent B. Can B spend 10? Tests whether `budget(parent) >= sum(budget(children))` holds. Formally framed by Agent Contracts (arXiv 2601.08815) as conservation laws; empirically unvalidated.

### 2c. S8: Reset/continuation semantics

Do counters carry across resume, or reset invisibly? An agent paused at iteration 3 of 5, then resumed. Does it have 2 remaining, or 5 fresh? Demand-specified in the QASkills guide.

---

## P3: Moat (automation and external adoption)

### 3a. Drift-watch CI

Scheduled workflow that detects new releases of pinned frameworks, re-executes, and opens an issue if behavior changes. The moat is not the data (which stales monthly) but the instrument.

Priority target: **Microsoft Agent Framework** (AutoGen + Semantic Kernel merger). Two executed rows will be invalidated by a single release. Be there on day one with measured comparison of child vs parent semantics.

### 3b. Framework CI integration

One framework running our scenario in their CI is worth more than five new dimensions. Target: offer AutoGen or CrewAI a GitHub Action that runs S2 against their HEAD and fails on semantic drift.

### 3c. Warning-semantics column

hermes-agent #414 is designing budget-pressure warnings. "Does the framework warn before the limit fires?" is a cheap new column with active demand.

---

## P4: Academic engagement

### 4a. Agent Contracts (arXiv 2601.08815)

Their Table 1 compares governance features across 8 frameworks from documentation. Our tool shows that even source-code analysis (a more rigorous method than documentation) is wrong 50% of the time — documentation-only analysis is presumably at least as fragile. Offer executed validation of their table. Opens citation channel into formal-methods community.

### 4b. "When Agents Do Not Stop" (arXiv 2607.01641)

Studies infinite agentic loops across 6,549 repos. Our Agno finding (enforcement fires but agent continues) is a live instance of exactly what they detect statically. Our S6 enforcement suite is the runtime complement to their static IAL-Scan.

### 4c. Own paper

Data for the budget-semantics paper is 100% complete for S2. Multi-scenario execution (S4, S5, S6) makes it multi-dimensional. Target venue: ICSE SEIP or ESEC/FSE industry track.

---

## P5: Hygiene (after public-facing correctness is clean)

- pytest suite covering the harness pipeline end-to-end
- Type annotations on public API
- CLI --json flag for machine-readable output
- CITATION.cff + Zenodo DOI badge
- CONTRIBUTING.md ("how to add a framework")

---

## Anti-goals

- **No 1.0.** Schema changed twice in 72 hours. 0.x costs nothing with this audience (they pin commits). Stability promise comes after first external adoption.
- **No website / registry play** until first external citation or CI adoption exists.
- **No version matrix** (defer to drift-watch CI, don't hand-roll a bounded version).
- **No operator-facing page** until the instrument is trusted by at least one framework maintainer.

## Kill criterion

If no external CI adoption, citation, or framework-maintainer engagement within 4 months of first publication: freeze features, maintain drift-watch only, redirect effort to venues with traction.

---

## Related work

| Source | What it holds | What it needs from us |
|--------|---------------|----------------------|
| Agent Contracts (2601.08815) | Formal conservation laws for delegation | Executed validation of their docs-based table |
| When Agents Do Not Stop (2607.01641) | Static detection of infinite loops in 6549 repos | Runtime enforcement measurement (our S6) |
| hermes-agent #414 | Budget-pressure warning design | What max_iterations means (our matrix) |
| hermes-agent #75097 | "Iteration budget semantics diverge" | Our entire project is the proof |
| DSPy #10064 | Nested track_usage under-counts | Same aggregation problem we measure |
| Pydantic AI #7133 | cost_limit non-deterministic when partial pricing | consumed_at_ground_truth vs counter_at_budget_stop |
| OTel GenAI #439 | Budget governance span attributes | Our data is the empirical basis |
| OTel GenAI #443 | Per-operation cost conventions | 5-unit divergence motivates cost.source |
| MCP SEP-3004 | Audit record canonicalization | Cross-SDK divergence data |
