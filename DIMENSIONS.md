# Budget Semantics Divergence Dimensions

24 dimensions of divergence discovered across 11 AI agent frameworks.

## Core Iteration Semantics (D1-D4)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D1 | Iteration unit | What counts as one iteration? | S1, S2 |
| D2 | Token accounting | Which tokens are counted? | S2, S6 |
| D3 | Enforcement point | Pre-call or post-call budget check? | S2 |
| D4 | Exhaustion behavior | What happens when budget runs out? | S2 |

## Multi-Agent (D5-D6)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D5 | Budget delegation | How is budget shared with sub-agents? | S3, S10 |
| D6 | Delegation cost | Does delegating itself consume budget? | S3, S10 |

## Parallel Execution (D7-D8)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D7 | Parallel tool counting | N parallel tools = how many units? | S4 |
| D8 | Partial batch execution | If budget=2 and batch=3, run 2 or 0? | S4 |

## Error Handling (D9-D10)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D9 | Error/retry counting | Failed + retry = 1 or 2 units? | S5 |
| D10 | Error propagation | How is the error communicated to LLM? | S5 |

## Token Budget (D11-D12)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D11 | Token budget enforcement | Cumulative token tracking? | S6 |
| D12 | Token counting method | Total, completion-only, or prompt-only? | S6 |

## Streaming (D13-D14)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D13 | Streaming chunk counting | Streamed response = 1 or N budget units? | S7 |
| D14 | Streaming token attribution | Single usage record or incremental? | S7 |

## Context Growth (D15-D16)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D15 | Tool output token counting | Large tool output counts in budget? | S8 |
| D16 | Context growth attribution | Growing prompt attributed to which span? | S8 |

## System Prompt (D17-D18)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D17 | System prompt attribution | Counted once, every turn, or never? | S9 |
| D18 | System prompt telemetry | How represented in OTel spans? | S9 |

## Deep Delegation (D19-D20)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D19 | Nested inheritance | Budget across 3+ delegation levels? | S10 |
| D20 | Delegation cost visibility | Parent see child's consumption? | S10 |

## Fault Tolerance (D21-D22)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D21 | Timeout budget impact | Timed-out call consumes budget? | S11 |
| D22 | Timeout token attribution | Tokens from failed request counted? | S11 |

## Dynamic Budget (D23-D24)

| Dim | Name | Question | Scenarios |
|-----|------|----------|-----------|
| D23 | Dynamic budget support | Can budget change mid-execution? | S12 |
| D24 | Budget modification telemetry | How to represent changes in OTel? | S12 |

## Framework Coverage Matrix

| Framework | D1 | D5 | D7 | D9 | D11 | D13 | D15 | D17 | D19 | D21 | D23 |
|-----------|----|----|----|----|-----|-----|-----|-----|-----|-----|-----|
| AutoGen | msg | shared | N | counts | callback | transparent | configurable | every-turn | shared-pool | counts | callback |
| OpenAI Agents | llm | shared | 1 | counts | none | transparent | no | every-turn | shared | counts | no |
| LangChain | cycle | n/a | 1 | configurable | none | transparent | no | every-turn | n/a | configurable | no |
| LangGraph | node | subtract | 1 | counts | none | transparent | indirect | every-turn | subtract | counts | no |
| CrewAI | cycle | independent | n/a | free | none | n/a | no | every-turn | independent | free | no |
| ADK | loop | remaining | 1 | counts | configurable | transparent | configurable | once | remaining | counts | no |
| Semantic Kernel | invoke | n/a | 1 | free | none | transparent | no | every-turn | n/a | counts | mutable |
| Anthropic | client | n/a | client | client | per-call | transparent | indirect | per-call | n/a | client | n/a |
| Swarm | msg | shared | 2N | counts | none | transparent | no | every-turn | shared | counts | mutable |
| LlamaIndex | step | n/a | separate | counts | none | transparent | no | every-turn | n/a | counts | no |
| Agno | cycle | team-pool | 1 | counts | output-only | transparent | no | every-turn | team-pool | counts | no |

## Key Finding

For `gen_ai.agent.iteration_budget.consumed` with the SAME execution
(4 LLM calls, 3 tool calls):

```
consumed = [3, 4, 7, 10]
```

depending on which framework. 4 different values. Not edge cases or
implementation bugs. Fundamental design disagreements about what "one iteration"
means.

## Impact on OTel Semantic Conventions

Without mandatory counting semantics metadata, the budget attributes in
PR #439 are:

1. Not comparable across frameworks (the primary use case for OTel)
2. Meaningless for multi-framework dashboards
3. Incorrect for cost attribution and chargeback
4. Unstable for alert thresholds (same execution, different consumed values)
5. Misleading for capacity planning

Proposed fix: mandatory `gen_ai.agent.iteration_budget.counting_method` enum
that classifies the framework's counting approach.
