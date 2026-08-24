# agent-budget-semantics

Differential testing of budget enforcement semantics across AI agent frameworks.

## The Problem

Six major agent frameworks expose budget primitives that sound equivalent
but count fundamentally different things.

| Framework | Parameter | What "3" Means |
|-----------|-----------|----------------|
| AutoGen | max_turns | 3 messages (LLM + tool results mixed) |
| OpenAI Agents | max_turns | 3 LLM invocations |
| LangChain | max_iterations | 3 tool-call loops (final answer is free) |
| LangGraph | recursion_limit | 3 node executions (~1.5 iterations) |
| CrewAI | max_iter | 3 tool-use cycles |
| Google ADK | max_iterations | 3 full agent loops |

Setting `budget=3` across frameworks produces wildly different execution
depths. An observability system reporting "3 iterations used" means something
different for each framework, making cross-framework budget telemetry
unreliable.

## Approach

A deterministic mock LLM with a request ledger serves as ground truth.
Scripted scenarios force tool-calling loops of known depth. Each framework
runner executes the same scenario against the same mock. The harness
compares what each framework reports vs. what actually happened.

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

## Six Dimensions of Divergence

1. **Iteration unit** -- What constitutes one "iteration"?
2. **Token accounting** -- Which tokens count against budget?
3. **Enforcement point** -- When does the check fire?
4. **Exhaustion behavior** -- What happens at the limit?
5. **Engine vs. derived** -- Are counts from the API or framework logic?
6. **Runtime readability** -- Can an observer reconstruct budget state?

## Quick Start

```bash
pip install -e ".[dev]"

# Run mock LLM tests
pytest tests/test_mock_llm.py -v

# Run differential test with a specific framework
pip install -e ".[autogen]"
python harness.py --scenario scenarios/s2_budget_exhaustion.yaml --frameworks autogen

# Run all frameworks
pip install -e ".[all]"
python harness.py --all
```

## Project Structure

```
mock-llm/          Deterministic mock LLM with request ledger
scenarios/         YAML-defined scripted conversations
  s1_*             Baseline: natural completion within budget
  s2_*             Budget exhaustion: 10-turn loop vs budget=3
runners/           Per-framework adapters
  runner_autogen.py
  runner_openai_agents.py
  runner_langchain.py
  runner_langgraph.py
  runner_crewai.py
  runner_adk.py
expectations/      Predicted outcomes per scenario per framework
results/           Raw JSON output from harness runs
tests/             Unit tests for mock LLM and harness
harness.py         Orchestrator: start mock, run frameworks, compare
```

## Outputs

After running, the harness produces a divergence matrix showing how each
framework's budget enforcement compares against the mock LLM's ground truth
ledger. Results are written to `results/latest.json`.

## Relevance to OTel GenAI Conventions

This project directly addresses the collection story gap identified in
open-telemetry/semantic-conventions-genai#443. The OTel cost/budget
conventions cannot be standardized until the community agrees on what
"iteration" and "budget" mean across frameworks. This harness provides
the empirical evidence needed to ground that discussion.

## License

Apache-2.0
