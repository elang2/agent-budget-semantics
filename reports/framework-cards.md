# Framework Budget Semantics Cards

## autogen

| Property | Value |
|----------|-------|
| Budget Param | max_turns |
| Iteration Definition | Each message (LLM response OR tool result) in the group chat |
| What Counts | assistant_message + tool_result_message |
| Parallel Tools | Each tool result is a separate message = separate turn |
| Final Answer | Counts as a turn |
| Token Budget | Not natively enforced (callback-based) |

## openai_agents

| Property | Value |
|----------|-------|
| Budget Param | max_turns |
| Iteration Definition | Each full LLM invocation |
| What Counts | LLM API calls only (tool execution is transparent) |
| Parallel Tools | Multiple parallel tool calls = 1 turn (1 LLM response) |
| Final Answer | Counts as a turn |
| Token Budget | Not enforced |

## langchain

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each tool-use cycle (action + observation) |
| What Counts | Tool invocations only; final answer is FREE |
| Parallel Tools | Batch of parallel tools = 1 iteration |
| Final Answer | Does NOT count (free extra call) |
| Token Budget | Not natively enforced (per-call max_tokens only) |

## langgraph

| Property | Value |
|----------|-------|
| Budget Param | recursion_limit |
| Iteration Definition | Each graph node execution |
| What Counts | Node visits (agent node + tool node = 2 per iteration) |
| Parallel Tools | Tool node processes all parallel calls as 1 visit |
| Final Answer | Counts as a node visit |
| Token Budget | Not enforced |

## crewai

| Property | Value |
|----------|-------|
| Budget Param | max_iter |
| Iteration Definition | Each tool-use cycle |
| What Counts | Tool-use cycles; retries are FREE |
| Parallel Tools | N/A (CrewAI doesn't support parallel tool calls) |
| Final Answer | Gets one forced extra call to produce final_answer |
| Token Budget | Not enforced (max_rpm is rate limit, not budget) |

## adk

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each full agent loop (plan + act + observe) |
| What Counts | Complete agent loops |
| Parallel Tools | Multiple tools in one loop = 1 iteration |
| Final Answer | Part of the last iteration |
| Token Budget | Configurable via callbacks |

## semantic_kernel

| Property | Value |
|----------|-------|
| Budget Param | maximum_auto_invoke_attempts |
| Iteration Definition | Each auto-invoke round |
| What Counts | Rounds where tools were auto-invoked (not the LLM calls themselves) |
| Parallel Tools | N parallel tools = 1 attempt (batch is atomic) |
| Final Answer | Not counted (only tool-invoking rounds count) |
| Token Budget | max_tokens per call only (not cumulative) |

## anthropic

| Property | Value |
|----------|-------|
| Budget Param | NONE (client-side only) |
| Iteration Definition | Client-defined (no server concept) |
| What Counts | Whatever the client library decides |
| Parallel Tools | Client decides |
| Final Answer | Client decides |
| Token Budget | max_tokens per response (not cumulative, not enforced across loop) |

## swarm

| Property | Value |
|----------|-------|
| Budget Param | max_turns |
| Iteration Definition | Messages added to history since start |
| What Counts | ALL messages: assistant + tool_result + user (tool call = 2 messages) |
| Parallel Tools | Each tool result is a separate message in history |
| Final Answer | Counts as a message |
| Token Budget | Not enforced |

## llamaindex

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each ReAct step (Thought + Action + Observation) |
| What Counts | Complete reasoning steps; partial steps don't count |
| Parallel Tools | Counted individually via max_function_calls (separate budget!) |
| Final Answer | Gets one extra call via early_stopping_method='generate' |
| Token Budget | Not enforced natively |

## agno

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each tool-use cycle |
| What Counts | Tool-use cycles at agent level; TEAM has separate shared pool |
| Parallel Tools | Batch = 1 iteration |
| Final Answer | Part of normal flow |
| Token Budget | Cumulative output token budget (unique feature) |
