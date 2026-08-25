# agent-budget-semantics

[![PyPI version](https://img.shields.io/pypi/v/agent-budget-semantics)](https://pypi.org/project/agent-budget-semantics/)
[![PyPI downloads](https://img.shields.io/pypi/dm/agent-budget-semantics)](https://pypistats.org/packages/agent-budget-semantics)
[![CI](https://github.com/elang2/agent-budget-semantics/actions/workflows/ci.yml/badge.svg)](https://github.com/elang2/agent-budget-semantics/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/elang2/agent-budget-semantics)](https://github.com/elang2/agent-budget-semantics/stargazers)
[![License](https://img.shields.io/pypi/l/agent-budget-semantics)](https://github.com/elang2/agent-budget-semantics/blob/main/LICENSE)

Differential testing of budget enforcement semantics across 11 AI agent frameworks.

## The Problem

```
gen_ai.agent.iteration_budget.consumed = [3, 4, 5, 8]
```

Same work. Same LLM calls. Same tokens consumed. Four different telemetry values across production frameworks. Setting `budget=3` means something fundamentally different depending on which framework is instrumented.

Including archived/experimental frameworks (OpenAI Swarm), the spread widens to `[3, 4, 5, 8, 10]` with 5 unique values for identical execution.

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
**executed** = harness ran against mock LLM, observed values match model.
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
docker run --rm ghcr.io/elang2/agent-budget-semantics spans
```

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
autogen          8       7          233%     root → 4 llm → 3 tool
langchain        6       3          100%     root → 4 llm → 1 batch
swarm            8       10         333%     root → 4 llm → 3 tool
```

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

### S2: Budget Exhaustion (budget=3, 4 LLM calls, 3 tool calls, 478 tokens)

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

**Unique `consumed` values: `[3, 4, 5, 8, 10]`** — 5 different answers for identical execution.
Executed results in `results/S2-executed.json`.

### S4: Parallel Tools (3 tools requested in one LLM response)

How many budget units does one parallel batch of 3 tools cost?

| Framework | Batch cost | Why |
|-----------|-----------|-----|
| OpenAI Agents | 1 | Batch = 1 turn |
| LangChain | 1 | Batch = 1 iteration |
| LangGraph | 1 | Tool node runs once |
| ADK | 1 | One agent loop |
| Semantic Kernel | 1 | One auto-invoke round |
| LlamaIndex | 1 | One ReAct step |
| Agno | 1 | One cycle |
| AutoGen | 3 | Each tool result = separate message |
| CrewAI | N/A | Parallel calls not supported |
| Swarm | 6 | Each tool = request + result messages (archived) |

Spread among production frameworks: **1 to 3 (3x)**. Including archived Swarm: 1 to 6 (6x).

### S5: Error/Retry (budget=2, 1 failed + 1 retry)

| Framework | Retry counts? | consumed |
|-----------|--------------|----------|
| AutoGen | Yes | 2 (no budget left for useful work) |
| LangGraph | Yes | 2 |
| CrewAI | No | 1 (full budget for useful work) |
| Semantic Kernel | No | 1 |

### OTel Telemetry Impact

Same execution, different dashboard:

| Framework | Spans emitted | Structure | Alert at consumed>3? |
|-----------|--------------|-----------|----------------------|
| LangChain | 6 | root → 4 llm → 1 batch | NO (consumed=3) |
| OpenAI Agents | 8 | root → 4 llm → 3 tool | YES (consumed=4) |
| AutoGen | 8 | root → 4 llm → 3 tool | YES (consumed=5) |
| LangGraph | 8 | root → 4 llm → 3 tool | YES (consumed=8) |
| Swarm | 8 | root → 4 llm → 3 tool | YES (consumed=10) |

An alert threshold of `consumed > 3` fires for 5/11 frameworks but not 6/11. Same work. Same tokens. Your monitoring is framework-dependent.

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

No real LLM API keys needed. No flaky network calls. Fully reproducible.

## Three Architectural Models

Testing revealed three fundamentally different approaches to budget enforcement:

1. **Client-side only** (Anthropic) — No server-side budget concept. The client library decides when to stop. The API has no awareness of iteration limits.

2. **Framework-enforced** (9 frameworks) — The framework wraps the LLM API and applies its own budget logic. Each framework counts differently, producing the 4-value divergence.

3. **Server-side opaque** (AWS Bedrock) — The server enforces budget internally. The client cannot observe or control the counting mechanism.

## Relevance to OTel GenAI Conventions

This project provides empirical evidence for the budget governance discussion in the OpenTelemetry semantic conventions. Without mandatory counting semantics metadata, `gen_ai.agent.iteration_budget.consumed` is not comparable across frameworks.

Proposed fix: mandatory `counting_method` enum that classifies the framework's approach:

```
gen_ai.agent.iteration_budget.counting_method
  Values: llm_calls | tool_cycles | graph_nodes | messages
```

Related PRs/Issues:
- open-telemetry/semantic-conventions #439 (budget governance attributes)
- open-telemetry/semantic-conventions #451 (turn count)
- open-telemetry/semantic-conventions #447 (agent delegation)
- open-telemetry/semantic-conventions #4025 (retry counting)

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

Apache-2.0
