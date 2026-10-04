# Framework Budget Semantics Cards

Each card's first rows are the source-reading model. `Provenance` and
`Enforcement observed` come from the executed run where there is one;
where the two disagree about a parameter name, the run governs.

## autogen

| Property | Value |
|----------|-------|
| Budget Param | max_messages |
| Iteration Definition | Composite messages (1 user + N agent turns) |
| What Counts | TextMessage + ToolCallSummaryMessage (not individual events) |
| Parallel Tools | Each tool result is a separate message = separate turn |
| Final Answer | Counts as a turn |
| Token Budget | Not natively enforced (callback-based) |
| Provenance | executed |
| Budget Param As Run | `MaxMessageTermination(max_messages=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## openai_agents

| Property | Value |
|----------|-------|
| Budget Param | max_turns |
| Iteration Definition | Each full LLM invocation |
| What Counts | LLM API calls only (tool execution is transparent) |
| Parallel Tools | Multiple parallel tool calls = 1 turn (1 LLM response) |
| Final Answer | Counts as a turn |
| Token Budget | Not enforced |
| Provenance | executed |
| Budget Param As Run | `Runner.run(max_turns=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## langchain

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each tool-use cycle (action + observation) |
| What Counts | Tool invocations only; final answer is FREE |
| Parallel Tools | Batch of parallel tools = 1 iteration |
| Final Answer | Does NOT count (free extra call) |
| Token Budget | Not natively enforced (per-call max_tokens only) |
| Provenance | executed |
| Budget Param As Run | `AgentExecutor(max_iterations=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## langgraph

| Property | Value |
|----------|-------|
| Budget Param | recursion_limit |
| Iteration Definition | Graph node visits including __start__ (2 nodes per iteration) |
| What Counts | __start__(1) + agent_node(1) + tool_node(1) per iteration |
| Parallel Tools | Tool node processes all parallel calls as 1 visit |
| Final Answer | Counts as a node visit |
| Token Budget | Not enforced |
| Provenance | executed |
| Budget Param As Run | `config={"recursion_limit": N}` |
| Enforcement (author classification) | limit held in the recorded run |

## crewai

| Property | Value |
|----------|-------|
| Budget Param | max_iter |
| Iteration Definition | Each tool-use cycle |
| What Counts | Tool-use cycles; retries are FREE |
| Parallel Tools | N/A (CrewAI doesn't support parallel tool calls) |
| Final Answer | Gets one forced extra call to produce final_answer |
| Token Budget | Not enforced (max_rpm is rate limit, not budget) |
| Provenance | executed |
| Budget Param As Run | `Agent(max_iter=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## adk

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each full agent loop (plan + act + observe) |
| What Counts | Complete agent loops |
| Parallel Tools | Multiple tools in one loop = 1 iteration |
| Final Answer | Part of the last iteration |
| Token Budget | Configurable via callbacks |
| Provenance | modeled — not run, so no enforcement observation |

## semantic_kernel

| Property | Value |
|----------|-------|
| Budget Param | maximum_auto_invoke_attempts |
| Iteration Definition | Each auto-invoke round |
| What Counts | Rounds where tools were auto-invoked (not the LLM calls themselves) |
| Parallel Tools | N parallel tools = 1 attempt (batch is atomic) |
| Final Answer | Not counted (only tool-invoking rounds count) |
| Token Budget | max_tokens per call only (not cumulative) |
| Provenance | executed |
| Budget Param As Run | `FunctionChoiceBehavior.Auto(maximum_auto_invoke_attempts=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## anthropic

| Property | Value |
|----------|-------|
| Budget Param | NONE (client-side only) |
| Iteration Definition | Client-defined (no server concept) |
| What Counts | Whatever the client library decides |
| Parallel Tools | Client decides |
| Final Answer | Client decides |
| Token Budget | max_tokens per response (not cumulative, not enforced across loop) |
| Provenance | modeled — not run, so no enforcement observation |

## swarm

| Property | Value |
|----------|-------|
| Budget Param | max_turns |
| Iteration Definition | Messages added to history since start |
| What Counts | ALL messages: assistant + tool_result + user (tool call = 2 messages) |
| Parallel Tools | Each tool result is a separate message in history |
| Final Answer | Counts as a message |
| Token Budget | Not enforced |
| Provenance | modeled — not run, so no enforcement observation |

## llamaindex

| Property | Value |
|----------|-------|
| Budget Param | max_iterations |
| Iteration Definition | Each LLM response (parse_agent_output calls) |
| What Counts | Every LLM response increments counter (tool-calling and final alike) |
| Parallel Tools | Batch = 1 iteration (one LLM response) |
| Final Answer | Counts as an iteration |
| Token Budget | Not enforced natively |
| Provenance | executed |
| Budget Param As Run | `agent.run(max_iterations=N)` |
| Enforcement (author classification) | limit held in the recorded run |

## agno

| Property | Value |
|----------|-------|
| Budget Param | tool_call_limit |
| Iteration Definition | Each tool-use cycle |
| What Counts | Tool-use cycles at agent level; TEAM has separate shared pool |
| Parallel Tools | Batch = 1 iteration |
| Final Answer | Part of normal flow |
| Token Budget | Cumulative output token budget (unique feature) |
| Provenance | executed |
| Budget Param As Run | `Agent(tool_call_limit=N)` |
| Enforcement (author classification) | limit did not hold in the recorded run — mechanism measured in results/S2-toolchoice-2026-10-04.json |
