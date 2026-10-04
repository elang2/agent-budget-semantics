# agent-budget-semantics

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22119569.svg)](https://doi.org/10.5281/zenodo.22119569)
[![PyPI version](https://img.shields.io/pypi/v/agent-budget-semantics)](https://pypi.org/project/agent-budget-semantics/)
[![PyPI downloads](https://img.shields.io/pypi/dm/agent-budget-semantics)](https://pypistats.org/packages/agent-budget-semantics)
[![CI](https://github.com/elang2/agent-budget-semantics/actions/workflows/ci.yml/badge.svg)](https://github.com/elang2/agent-budget-semantics/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/elang2/agent-budget-semantics)](https://github.com/elang2/agent-budget-semantics/stargazers)
[![License](https://img.shields.io/pypi/l/agent-budget-semantics)](https://github.com/elang2/agent-budget-semantics/blob/main/LICENSE)

Differential testing of budget enforcement semantics across 11 AI agent frameworks.

Related project: [elang2/mcp-audit-gateway](https://github.com/elang2/mcp-audit-gateway) — companion cross-emitter differential-testing harness on the canonicalization (JCS) substrate, ten language SDKs producing byte-identical signed audit records.

## The Problem

```
gen_ai.agent.iteration_budget.consumed = [3, 4, 5, 8]
```

Same work. Same LLM calls. Same tokens consumed. Four different telemetry values across production frameworks. Setting `budget=3` means something fundamentally different depending on which framework is instrumented.

Adding the three rows that were not executed (Google ADK and Anthropic modelled, OpenAI Swarm archived) widens the spread to `[3, 4, 5, 8, 10]`. Those three values are model output, not observations, so the five-value set is not a set of answers to identical execution. The executed set is the four values above.

## The Evidence

Counting logic derived from source code analysis at pinned versions (see [PINS.md](PINS.md)).
Rows upgrade to "executed" as the differential harness validates each prediction.

| Framework | Version | `budget=3` means † | Parallel 3 tools ‡ | Error retry ‡ | Final answer ‡ | Tier |
|-----------|---------|-----------------|------------------|-------------|--------------|------|
| AutoGen | 0.4.7 | 2 agent turns (user msg eats 1) | 3 budget units | Counts | Counts | executed |
| OpenAI Agents | 0.22.0 | 3 LLM invocations | 1 budget unit | Counts | Counts | executed |
| LangChain | 0.3.14 | 3 tool-call cycles | 1 budget unit | Configurable | Free | executed |
| LangGraph | 1.2.11 | ~1 full iteration (recursion=3) | 1 budget unit | Counts | Counts | executed |
| CrewAI | 1.15.16 | 3 tool-use cycles | N/A | Free | Free extra call | executed |
| Google ADK | 1.2.1 | 3 full agent loops | 1 budget unit | Counts | Part of last | modeled |
| Semantic Kernel | 1.44.1 | 3 auto-invoke attempts | 1 budget unit | Free | Not counted | executed |
| Anthropic | 0.39.0 | Client-defined | Client decides | Client decides | Client decides | modeled |
| Swarm | 0.1.0 | Messages in history | 2N budget units | Counts | Counts | archived |
| LlamaIndex | 0.14.24 | 3 LLM responses | 1 budget unit | Counts | Counts | executed |
| Agno | 1.2.5 | NOT ENFORCED | N/A | N/A | N/A | executed |

Tier legend: **modeled** = counting logic derived from source code analysis at pinned version.
**executed** = the harness ran this framework against the mock LLM. It is a statement about whether the run happened and carries no claim that the observed value matched the prediction; see `matched` for that, which held for 4 of the 7 informative rows. Agno ran and is `executed`, and emitted no counter, so it is `status: uninformative` and outside that denominator.
**archived** = framework is experimental/not production (OpenAI Swarm).

† The "`budget=3` means" column is validated by execution for rows marked `executed` (scenario S2). ‡ "Parallel 3 tools," "Error retry," and "Final answer" columns are derived from source-code analysis for all frameworks (scenarios S4/S5 not yet executed). These will upgrade to executed once the harness validates them.

## Install

```bash
pip install agent-budget-semantics
```

Or with Docker (no dependencies):

```bash
docker run --rm ghcr.io/elang2/agent-budget-semantics compare
docker run --rm ghcr.io/elang2/agent-budget-semantics cost
docker run --rm ghcr.io/elang2/agent-budget-semantics cost-source
docker run --rm ghcr.io/elang2/agent-budget-semantics spans
docker run --rm ghcr.io/elang2/agent-budget-semantics dimensions
```

**What the container can and cannot do.** The image installs the `dev` extra
and no agent framework, which is a deliberate boundary rather than an
oversight. The five commands above are the derived analyses; they read
committed inputs and need no framework, so they run anywhere with no API key
and no network. What the container cannot do is execute a framework: `run`
has no framework to drive, and the `executed` rows in the tables above cannot
be regenerated inside it. That work needs the pinned environment in
[PINS.md](PINS.md), because a result is only meaningful at the version it was
observed at, and installing one of eleven frameworks at whatever version
currently resolves would produce neither a differential result nor a pinned
one.

## Quick Start

```bash
# Show the iteration divergence matrix
agent-budget-semantics compare

# Show cost divergence ($97K/year spread at scale)
agent-budget-semantics cost --daily-runs 1000

# Show OTel telemetry divergence (what your dashboard would show)
agent-budget-semantics spans

# Generate full report suite (markdown + JSON)
agent-budget-semantics report --output reports/

# Run differential tests against a specific framework
pip install "agent-budget-semantics[autogen]"
agent-budget-semantics run --scenario scenarios/S2-budget-exhaustion.yaml --frameworks autogen

# Run all frameworks
pip install "agent-budget-semantics[all]"
agent-budget-semantics run --all
```

## What It Produces

### Iteration divergence (the headline finding)

```
Framework          consumed   utilization   Counting method
--------------------------------------------------------------------------------
langchain          3          100%          Each tool-use cycle
openai_agents      4          133%          Each full LLM invocation
llamaindex         4          133%          Each LLM response
autogen            5          167%          Composite messages (1 user + N agent turns)
langgraph          8          267%          Graph node visits including __start__
swarm              10         333%          Messages added to history
```

### Cost divergence (makes it tangible)

```
Monthly Cost Projection (1000 runs/day)
----------------------------------------------------------------------
langchain        $5,850/mo     baseline
openai_agents    $6,750/mo     +$900 (+15%)
autogen          $10,350/mo    +$4,500 (+77%)
swarm            $13,950/mo    +$8,100 (+138%)

Annual spread: $97,200 — from iteration counting alone.
```

### OTel span structure (what your dashboard shows)

```
Framework        Spans   consumed   util%    Structure
------------------------------------------------------------------------------------------
autogen          8       5          167%     root → 4 llm → 3 tool
langchain        6       3          100%     root → 4 llm → 1 batch
swarm            8       10         333%     root → 4 llm → 3 tool
```

### Cost-source divergence (empirical companion to OTel PR #443)

Six real-world cost-recording emitters, five distinct attribute schemas for the same LLM call. Backend enrichment produces a different value than request-time emission because its pricing has drifted.

```
Emitter                                Layer              Attrs                                        cost.source
Pydantic AI + Logfire (genai-prices)   client_library     operation.cost                               local
OpenRouter (cost headers)              gateway            gen_ai.usage.input_cost,output_cost,total    provider
LiteLLM proxy                          gateway            gen_ai.usage.cost, gen_ai.cost.amount        local
Direct provider SDK                    client_library     (none)                                       out-of-scope
Provider-returned cost (hypothetical)  provider_response  (none)                                       provider
Backend enrichment (stale pricing)     backend            gen_ai.usage.cost.amount                     out-of-scope

Distinct attribute schemas: 5
```

Under [PR #443's](https://github.com/open-telemetry/semantic-conventions-genai/pull/443) proposed v0.1 shape, in-scope emitters converge to `gen_ai.usage.cost.amount` + `.currency` + `.source` with the enum `provider | local`. Backend enrichment stays out of scope because its pricing may have drifted since the call, so it cannot claim the same request-time reliability the enum promises.

```bash
agent-budget-semantics cost-source
agent-budget-semantics cost-source --model claude-sonnet-4 --provider-cost 0.008
```

Full API + test coverage in `cost_source_divergence.py` and `tests/test_cost_source_divergence.py` (29 tests).

## 12 Scenarios, 24 Dimensions

| Scenario | Tests | Dimensions |
|----------|-------|-----------|
| S1: Simple tool loop | Baseline behavior | D1-D4 |
| S2: Budget exhaustion | Enforcement boundaries | D1-D4 |
| S3: Multi-agent delegation | Budget sharing | D5-D6 |
| S4: Parallel tools | Batch counting | D7-D8 |
| S5: Error/retry | Retry budget impact | D9-D10 |
| S6: Token budget | Cumulative token tracking | D11-D12 |
| S7: Streaming | Chunk counting | D13-D14 |
| S8: Tool output explosion | Large response attribution | D15-D16 |
| S9: System prompt | Repeated prompt tokens | D17-D18 |
| S10: Nested delegation | 3-level inheritance | D19-D20 |
| S11: Timeout/cancellation | Failed call budget impact | D21-D22 |
| S12: Dynamic budget | Mid-run modification | D23-D24 |

See [DIMENSIONS.md](DIMENSIONS.md) for the full taxonomy with per-framework behavior.

## Full Conformance Results

### S2: Budget Exhaustion (budget=3, 4 LLM calls, 3 tool calls, 800 tokens)

Pinned versions in [PINS.md](PINS.md). Expectations in `expectations/S2-budget-exhaustion.yaml`.

| Framework | budget param | consumed | utilization | exceeded? | counting method | tier |
|-----------|-------------|----------|-------------|-----------|-----------------|------|
| AutoGen 0.4.7 | `max_messages` | **5** | 167% | YES | TextMessage + ToolCallSummaryMessage | executed |
| OpenAI Agents 0.22.0 | `max_turns` | **4** | 133% | YES | LLM invocations | executed |
| LangChain 0.3.14 | `max_iterations` | 3 | 100% | no | tool-use cycles | executed |
| LangGraph 1.2.11 | `recursion_limit` | **8** | 267% | YES | graph node visits (incl. __start__) | executed |
| CrewAI 1.15.16 | `max_iter` | 3 | 100% | no | tool-use cycles | executed |
| Google ADK 1.2.1 | `max_iterations` | 3 | 100% | no | full agent loops | modeled |
| Semantic Kernel 1.44.1 | `max_auto_invoke` | 3 | 100% | no | auto-invoke rounds | executed |
| Anthropic 0.39.0 | *(client-side)* | **4** | 133% | YES | client-defined | modeled |
| Swarm 0.1.0 | `max_turns` | **10** | 333% | YES | all messages in history | archived |
| LlamaIndex 0.14.24 | `max_iterations` | **4** | 133% | YES | LLM responses | executed |
| Agno 1.2.5 | `tool_call_limit` | N/A | N/A | N/A | NOT ENFORCED | executed |

**Unique `consumed` values: `[3, 4, 5, 8, 10]`** across all eleven rows, of which `[3, 4, 5, 8]` is the executed set. The 10 comes from OpenAI Swarm, which is archived and was never run, so it is a modelled value and the five-value set is not five answers to identical execution.
Executed results in `results/S2-executed.json`.

### S4: Parallel Tools (3 tools requested in one LLM response) — executed

*Outside the per-cell validity contract; see the `schema.status` note in `results/S2-executed.json`. The Status column below is a run outcome, not a validity verdict.*

How many budget units does one parallel batch of 3 tools cost? Executed with 4 frameworks.

| Framework | Batch cost | Status | Why |
|-----------|-----------|--------|-----|
| LangChain | 3† | executed | Budget stopped at 3 (unexpected - predicted 1) |
| LangGraph | 1 | executed | Tool node runs once, batch = 1 unit |
| Semantic Kernel | 4† | executed | Completed with 4 calls (free final answer) |
| AutoGen | 2 | executed | Stopped at budget=2 (predicted 3) |
| OpenAI Agents | 1 | modeled | Batch = 1 turn (not executed) |
| ADK | 1 | modeled | One agent loop (not executed) |
| LlamaIndex | 1 | modeled | One ReAct step (not executed) |
| Agno | 1 | modeled | One cycle (not executed) |
| CrewAI | N/A | error | Parallel calls validation error |

†Unexpected results requiring investigation. Executed results in `results/S4-executed.json`.
| Swarm | 6 | Each tool = request + result messages (archived) |

Spread among production frameworks: **1 to 3 (3x)**. Including archived Swarm: 1 to 6 (6x).

### S5: Error/Retry (budget=2, 1 failed + 1 retry) — executed

*Outside the per-cell validity contract; see the `schema.status` note in `results/S2-executed.json`. The Status column below is a run outcome, not a validity verdict.*

Executed with 4 frameworks showing whether retries count against budget.

| Framework | Retry counts? | consumed | Status |
|-----------|--------------|----------|--------|
| AutoGen | Yes | 3 | executed - Stopped at budget after retry |
| Semantic Kernel | No | 4 | executed - Completed (retry free) |
| LangGraph | Unclear | 1 | executed - Unexpected single call |
| LangChain | Error | 0 | executed - Scenario error |
| CrewAI | No | 1 | modeled - Full budget for useful work |

Executed results in `results/S5-executed.json`.

### OTel Telemetry Impact

One workload, different dashboard. The span counts and structures below are
**simulated** by `otel_span_capture.py` from each framework's run result, not
captured from a live OTel exporter, so they are a projection of what each
framework's instrumentation would emit rather than a recording of what it did:

| Framework | Spans emitted | Structure | Alert at consumed>3? |
|-----------|--------------|-----------|----------------------|
| LangChain | 6 | root → 4 llm → 1 batch | NO (consumed=3) |
| OpenAI Agents | 8 | root → 4 llm → 3 tool | YES (consumed=4) |
| AutoGen | 8 | root → 4 llm → 3 tool | YES (consumed=5) |
| LangGraph | 8 | root → 4 llm → 3 tool | YES (consumed=8) |
| Swarm | 8 | root → 4 llm → 3 tool | YES (consumed=10) |

An alert threshold of `consumed > 3` fires for 6 of the 11 rows and not for 4, while 1 (Agno) emits no counter at all and so can neither fire nor stay silent. Same work, same tokens. Monitoring is framework-dependent, and a framework that reports nothing is invisible to the threshold rather than compliant with it. These counts are derived from `reports/report.json` and asserted by `tests/test_report_generation.py`.

## Use in CI

Drop into `.github/workflows/budget-conformance.yml`:

```yaml
name: Budget Semantics Check
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install
        run: pip install agent-budget-semantics

      - name: Run comparison
        run: |
          agent-budget-semantics compare
          agent-budget-semantics cost
          agent-budget-semantics report --output budget-report/

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: budget-divergence-report
          path: budget-report/
```

Or with Docker (no Python setup needed):

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/elang2/agent-budget-semantics:latest
    steps:
      - run: agent-budget-semantics compare
      - run: agent-budget-semantics cost --daily-runs 500
```

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Scenario   │────▶│  Mock LLM    │◀────│  Framework    │
│  (YAML)     │     │  (ledger)    │     │  Runner       │
└─────────────┘     └──────┬───────┘     └───────────────┘
                           │
                           ▼
                    Ground Truth
                    (actual calls,
                     actual tokens)
```

A deterministic mock LLM with a request ledger serves as ground truth. Scripted scenarios force tool-calling loops of known depth. Each framework runner executes the same scenario against the same mock. The harness compares what each framework reports vs. what actually happened.

No real LLM API keys are needed, and no request leaves the machine. The derived tables regenerate deterministically from committed inputs with one command, `python report_generator.py`, and CI fails if the committed output no longer matches the generator.

Per-framework execution is weaker than that, and the distinction matters when reading the tables. Reproducing an `executed` row requires the pinned environment in [PINS.md](PINS.md), assembled by hand; each recorded value is a single run rather than a repeated measurement, so run-to-run stability is asserted nowhere; and no row has been independently replicated. Repeat execution is tracked in [ROADMAP.md](ROADMAP.md) and is not done.

## Three Architectural Models

Testing revealed three fundamentally different approaches to budget enforcement:

1. **Client-side only** (Anthropic) — No server-side budget concept. The client library decides when to stop. The API has no awareness of iteration limits.

2. **Framework-enforced** (9 frameworks) — The framework wraps the LLM API and applies its own budget logic. Each framework counts differently, producing the 4-value divergence.

3. **Server-side opaque** (AWS Bedrock) — The server enforces budget internally. The client cannot observe or control the counting mechanism.

## Relevance to OTel GenAI Conventions

This project provides empirical evidence for the budget governance discussion in the OpenTelemetry semantic conventions. The finding is a negative one, and it is the result rather than a setback: a cross-framework `gen_ai.agent.iteration_budget.consumed` should not be named at all, because the counts frameworks report for one execution are not measurements of the same quantity.

An earlier revision of this section proposed a mandatory `counting_method` enum — `llm_calls | tool_cycles | graph_nodes | messages` — as the fix. That proposal does not survive its own evidence, and the project no longer holds it. Spec PR #439 carried the attribute set and was withdrawn on 2026-08-27 after maintainer review concluded the values are not comparable across implementations whether or not a unit travels with them. Tagging a count with the unit that produced it makes the unit legible; it does not make two differently-counted numbers addable, comparable in a dashboard, or safe as an alert threshold, which were the use cases the attribute existed to serve.

Two directions remain consistent with that closure, and neither is a shared `consumed` attribute. Framework-specific names such as `openai.agent.max_turns` or `langchain.agent.max_iterations` fix the counting semantics by definition, which is the direction the review converged toward. Alternatively, `iteration_budget.limit` may be recorded verbatim, as the framework was configured, with no cross-framework normalization attempted.

Related PRs/Issues:
- open-telemetry/semantic-conventions-genai #425 (parent issue — budget governance attributes for invoke_agent)
- open-telemetry/semantic-conventions-genai #439 (spec PR carrying the four attributes; closed 2026-08-27 after maintainer review concluded that divergent counting semantics across frameworks make a single shared attribute difficult to define; continuation of #426)
- open-telemetry/semantic-conventions-genai #451 (turn count)
- open-telemetry/semantic-conventions-genai #447 (agent delegation)
- open-telemetry/semantic-conventions-genai #476 (retry counting — transferred from semantic-conventions#4025)

The harness measures each of the four points raised on issue #425 by
Mandark-droid (issuecomment-5547801633, 2026-09-04). Note that #439,
which attempted to codify a shared attribute for these, was closed on
2026-08-27 after maintainer review; the measurements below were part
of the discussion leading to that closure:

1. **Accumulate, don't sum from children.** `budget_accumulator.py` plus
   `tests/test_sampling_survivability.py` show that a naive
   sum-from-child-spans implementation reports zero consumption under
   100% child-span sampling, whereas the contextvars accumulator reports
   the correct total on the same trace.
2. **Nested-agent direct vs subtree.** `tests/test_nested_delegation_split.py`
   shows a supervisor + two sub-agents where the same trace produces
   iterations=1 direct vs iterations=4 subtree, and tokens=150 direct vs
   tokens=825 subtree. Same trace, 4x and 5.5x divergence.
3. **The MUST NOT is doing real work.** `expectations/expected_shape.yaml`
   shows that 10 of the 11 tracked frameworks expose no aggregate token
   cap at all — emitting only `iteration_budget.*` is the expected outcome
   for most frameworks, and `synthesis_detector.py` (wired into CI) fails
   the build if any runner starts emitting a token budget that looks like
   iteration_limit × per_call_max_tokens.
4. **`iteration_budget.utilization` covers what `token_budget.utilization`
   cannot.** The utilization column in the headline chart is now emitted
   under the correctly-named `gen_ai.invoke_agent.iteration_budget.utilization`
   attribute; `token_budget.utilization` is emitted only where a real
   token cap exists (1 of 11).

## Project Structure

```
cli.py                 CLI entry point
harness.py             Test orchestrator
otel_comparison.py     Iteration divergence analysis
otel_span_capture.py   OTel telemetry simulation
cost_divergence.py     Cost impact calculator
report_generator.py    Markdown/JSON report suite
DIMENSIONS.md          24-dimension taxonomy

mock-llm/              Deterministic mock LLM server
  server.py            OpenAI-compatible API with request ledger

runners/               Per-framework adapters (11 frameworks)
  runner_autogen.py
  runner_openai_agents.py
  runner_langchain.py
  runner_langgraph.py
  runner_crewai.py
  runner_adk.py
  runner_semantic_kernel.py
  runner_anthropic.py
  runner_swarm.py
  runner_llamaindex.py
  runner_agno.py

scenarios/             YAML-defined test scenarios (12 scenarios)
  S1-S12               Covering 24 divergence dimensions

tests/                 Unit tests
reports/               Generated report artifacts
```

## License

MIT
