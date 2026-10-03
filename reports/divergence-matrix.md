# Divergence Matrix

**Ground truth:** 4 LLM calls, 3 tool calls, 478 tokens
**Comparison budget limit:** 3 (utilization denominator for every row)

| Framework | Budget Param | budget | consumed | utilization | Provenance | Counting Method |
|-----------|-------------|--------|----------|-------------|------------|-----------------|
| autogen | `MaxMessageTermination(max_messages=N)` | 3 | 5 **EXCEEDED** | 167% | executed | Composite messages (1 user + N agent turns) |
| openai_agents | `Runner.run(max_turns=N)` | 3 | 4 **EXCEEDED** | 133% | executed | Each full LLM invocation |
| langchain | `AgentExecutor(max_iterations=N)` | 3 | 3 | 100% | executed | Each tool-use cycle (action + observation) |
| langgraph | `config={"recursion_limit": N}` | 6 | 8 **EXCEEDED** | 267% | executed | Graph node visits including __start__ (2 nodes per |
| crewai | `Agent(max_iter=N)` | 3 | 3 | 100% | executed | Each tool-use cycle |
| adk | `max_iterations` | 3 | 3 | 100% | modeled | Each full agent loop (plan + act + observe) |
| semantic_kernel | `FunctionChoiceBehavior.Auto(maximum_auto_invoke_attempts=N)` | 3 | 3 | 100% | executed | Each auto-invoke round |
| anthropic | `NONE (client-side only)` | 3 | 4 **EXCEEDED** | 133% | modeled | Client-defined (no server concept) |
| swarm | `max_turns` | 3 | 10 **EXCEEDED** | 333% | modeled | Messages added to history since start |
| llamaindex | `agent.run(max_iterations=N)` | 3 | 4 **EXCEEDED** | 133% | executed | Each LLM response (parse_agent_output calls) |
| agno | `Agent(tool_call_limit=N)` | 3 | n/a **NOT ENFORCED** | n/a | executed | Each tool-use cycle (unvalidated: no unit observed) |

**Unique consumed values:** `[3, 4, 5, 8, 10]`
**Disagreement factor:** 5 different answers for same execution
**Executed rows only:** `[3, 4, 5, 8]` (4 different answers)

## Reading this table

- **Provenance** `executed` means the row is a reading taken from a run against the mock LLM. `modeled` means it is a prediction derived from reading the framework's source, and has not been run.
- **consumed** is normalised to the shared ground-truth workload above, so rows are comparable even where the executed run configured a different budget. **budget** is the limit that run actually configured; **utilization** uses the single comparison limit so the column is commensurable, which means utilization is not consumed/budget where the two differ. LangGraph is the one such row: it ran at recursion_limit=6, and its utilization is reported against 3.
- **agno** reports no consumed value at all. The budget parameter exists, propagates, and its enforcement code runs, but the outer agent loop ignores it, so no counter is emitted and the agent runs unbounded. This is a measurement, not a gap: scored as `n/a`, excluded from the disagreement count, and never replaced by the prediction model's number. The Counting Method shown for such a row is the unvalidated source-code model, since no unit was observed to validate it against.
