# Dimension Evidence Summary

**Frameworks tested:** 11
**Dimensions discovered:** 8 primary + sub-dimensions

## D1: Iteration unit

**Question:** What counts as one iteration?

| Framework | Behavior |
|-----------|----------|
| AutoGen | message (LLM response OR tool result) |
| OpenAI Agents | LLM invocation |
| LangChain | tool-use cycle (action + observation) |
| LangGraph | graph node execution |
| Semantic Kernel | auto-invoke round |
| Swarm | messages added to history |

## D5: Delegation budget

**Question:** How is budget shared across delegated agents?

| Framework | Behavior |
|-----------|----------|
| AutoGen | shared pool across group chat |
| CrewAI | each agent gets independent budget |
| ADK | remaining budget passed to sub-agent |
| Agno | team-level shared pool |

## D7: Parallel tool counting

**Question:** N parallel tools = how many budget units?

| Framework | Behavior |
|-----------|----------|
| OpenAI Agents | 1 (batch = 1 turn) |
| AutoGen | N (each tool result = separate message) |
| LangChain | 1 (batch = 1 iteration) |
| Swarm | 2N (each tool = request + result messages) |

## D9: Error/retry counting

**Question:** Does a failed+retry consume 1 or 2 units?

| Framework | Behavior |
|-----------|----------|
| AutoGen | 2 (retry is new turn) |
| CrewAI | 1 (retries are free) |
| LangGraph | 2 (each is a graph step) |
| Semantic Kernel | 1 (failed invoke doesn't decrement) |

## D11: Token budget enforcement

**Question:** Cumulative token tracking?

| Framework | Behavior |
|-----------|----------|
| AutoGen | via callback (configurable) |
| ADK | configurable cumulative |
| Agno | output tokens only |
| Most others | per-call max_tokens only |

## D15: Tool output tokens

**Question:** Do tool outputs count in budget?

| Framework | Behavior |
|-----------|----------|
| AutoGen | configurable via callbacks |
| LangChain | no (only LLM tokens) |
| Agno | no (output tokens only) |
| ADK | configurable |

## D19: Nested delegation

**Question:** Budget inheritance across 3+ levels?

| Framework | Behavior |
|-----------|----------|
| AutoGen | shared pool total |
| CrewAI | each agent independent |
| ADK | remaining passed down |
| LangGraph | recursion_limit minus consumed |

## D21: Timeout budget impact

**Question:** Does timeout consume budget?

| Framework | Behavior |
|-----------|----------|
| AutoGen | yes (turn consumed) |
| CrewAI | no (free retry policy) |
| Semantic Kernel | yes (attempt consumed) |
| LangGraph | yes (step consumed) |
