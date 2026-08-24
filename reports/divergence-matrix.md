# Divergence Matrix

**Ground truth:** 4 LLM calls, 3 tool calls, 478 tokens
**Budget limit:** 3

| Framework | Budget Param | consumed | utilization | Counting Method |
|-----------|-------------|----------|-------------|-----------------|
| autogen | `max_turns` | 7 **EXCEEDED** | 233% | Each message (LLM response OR tool result) in the  |
| openai_agents | `max_turns` | 4 **EXCEEDED** | 133% | Each full LLM invocation |
| langchain | `max_iterations` | 3 | 100% | Each tool-use cycle (action + observation) |
| langgraph | `recursion_limit` | 7 **EXCEEDED** | 233% | Each graph node execution |
| crewai | `max_iter` | 3 | 100% | Each tool-use cycle |
| adk | `max_iterations` | 3 | 100% | Each full agent loop (plan + act + observe) |
| semantic_kernel | `maximum_auto_invoke_attempts` | 3 | 100% | Each auto-invoke round |
| anthropic | `NONE (client-side only)` | 4 **EXCEEDED** | 133% | Client-defined (no server concept) |
| swarm | `max_turns` | 10 **EXCEEDED** | 333% | Messages added to history since start |
| llamaindex | `max_iterations` | 3 | 100% | Each ReAct step (Thought + Action + Observation) |
| agno | `max_iterations` | 3 | 100% | Each tool-use cycle |

**Unique consumed values:** `[3, 4, 7, 10]`
**Disagreement factor:** 4 different answers for same execution
