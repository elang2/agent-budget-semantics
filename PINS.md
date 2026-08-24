# Version Pins

All results in this repository were validated against the specific framework
versions listed below. Budget enforcement semantics can change between releases;
results are only reproducible at these pinned versions.

Last validated: 2026-08-23

| Framework | Package | Pinned Version | API Surface Used |
|-----------|---------|---------------|-----------------|
| AutoGen | autogen-agentchat | 0.4.7 | `MaxMessageTermination(max_messages=N)` on `RoundRobinGroupChat` |
| AutoGen | autogen-ext | 0.4.7 | OpenAIChatCompletionClient |
| OpenAI Agents | openai-agents | 0.22.0 | `Runner.run(max_turns=N)` |
| LangChain | langchain | 0.3.14 | `AgentExecutor(max_iterations=N)` |
| LangChain | langchain-openai | 0.3.2 | ChatOpenAI |
| LangGraph | langgraph | 1.2.11 | `graph.ainvoke(config={"recursion_limit": N})` |
| CrewAI | crewai | 1.15.16 | `Agent(max_iter=N)` |
| Google ADK | google-adk | 1.2.1 | `LoopAgent(max_iterations=N)` |
| Semantic Kernel | semantic-kernel | 1.44.1 | `FunctionChoiceBehavior.Auto(maximum_auto_invoke_attempts=N)` |
| Anthropic | anthropic | 0.39.0 | Client-side loop (no framework budget) |
| Swarm | openai-swarm | 0.1.0 | `client.run(max_turns=N)` |
| LlamaIndex | llama-index-core | 0.14.24 | `agent.run(max_iterations=N)` on FunctionAgent |
| Agno | agno | 1.2.5 | `Agent(tool_call_limit=N)` — NOT ENFORCED |

## How to reproduce at pinned versions

```bash
pip install autogen-agentchat==0.4.7 autogen-ext==0.4.7
pip install openai-agents==0.22.0
pip install langchain==0.3.14 langchain-openai==0.3.2
pip install langgraph==1.2.11
pip install crewai==1.15.16
pip install google-adk==1.2.1
pip install semantic-kernel==1.44.1
pip install anthropic==0.39.0
pip install openai-swarm==0.1.0
pip install llama-index-core==0.14.24 llama-index-llms-openai==0.4.6
pip install agno==1.2.5
```

## Tier labels

Results are categorized by validation method:

- **executed**: Harness ran the framework against the mock LLM, observed actual behavior
- **modeled**: Counting logic derived from source code analysis; predicted by formula, pending execution
- **archived**: Framework is experimental/archived; included for completeness, not production guidance

| Framework | Tier | Notes |
|-----------|------|-------|
| AutoGen | **executed** | Confirmed: max_messages counts TextMessage + ToolCallSummaryMessage. budget=N → N-1 agent turns. |
| OpenAI Agents | **executed** | Confirmed: max_turns counts LLM invocations. budget=N → N LLM calls. |
| LangChain | **executed** | Confirmed: max_iterations counts tool-calling cycles. budget=N → N iterations. |
| LangGraph | **executed** | Confirmed: recursion_limit counts node visits incl. __start__. Each iteration = 2 nodes. |
| CrewAI | **executed** | Confirmed: max_iter counts tool-use cycles. budget=N → N tool iterations + 1 forced final answer. |
| Google ADK | modeled | Google-specific endpoints (genai), not testable with OpenAI-compatible mock. |
| Semantic Kernel | **executed** | Confirmed: maximum_auto_invoke_attempts counts tool-invoking rounds. budget=N → N rounds + 1 free final answer. |
| Anthropic | modeled | Client-side, no framework budget to test |
| Swarm | archived | OpenAI explicitly marked as experimental/educational, not production |
| LlamaIndex | **executed** | Confirmed: max_iterations counts LLM responses (same as OpenAI Agents). budget=N → N LLM calls, N-1 tool executions. |
| Agno | **executed** | FINDING: budget NOT enforced in v1.2.5. tool_call_limit and reasoning_max_steps have no effect. |

Tier upgrades to "executed" when `python harness.py` produces matching results
in `results/` and the framework_version field is populated from `importlib.metadata`.

## Version change impact

When a framework updates its budget enforcement, re-run:

```bash
python harness.py --scenario scenarios/S2-budget-exhaustion.yaml --frameworks <name>
```

Compare against `expectations/S2-budget-exhaustion.yaml`. If results differ,
update both PINS.md and report.json with the new version and new values.
