# OTel Semantic Convention Recommendations

Based on differential testing across 11 frameworks.

## Problem Statement

The proposed `gen_ai.agent.iteration_budget.consumed` attribute
produces 4+ different values for the same execution depending on
which framework is instrumented. Without a mandatory counting
semantics enum, the attribute is not comparable across implementations.

## Recommendation 1: Mandatory counting_method enum

```
gen_ai.agent.iteration_budget.counting_method
  Values:
    - llm_calls          (OpenAI Agents, Anthropic)
    - tool_cycles        (LangChain, CrewAI, ADK, SK, LlamaIndex, Agno)
    - graph_nodes        (LangGraph)
    - messages           (AutoGen, Swarm)
```

## Recommendation 2: Parallel tool batch semantics

```
gen_ai.agent.parallel_tool_counting
  Values:
    - batch_as_one       (LangChain, OpenAI, ADK, SK, Agno)
    - individual         (AutoGen, Swarm)
```

## Recommendation 3: Error/retry policy

```
gen_ai.agent.retry_budget_policy
  Values:
    - retry_consumes     (AutoGen, LangGraph, SK)
    - retry_free         (CrewAI)
    - configurable       (LangChain)
```

## Recommendation 4: Token budget scope

```
gen_ai.agent.token_budget.scope
  Values:
    - llm_output_only    (Agno)
    - llm_total          (most)
    - including_tools    (configurable in AutoGen, ADK)
    - per_call_only      (SK, Swarm)
```

## Evidence

Without these enums, `gen_ai.agent.iteration_budget.consumed` is:
- **Not comparable** across frameworks
- **Misleading** in multi-framework dashboards
- **Incorrect** for cost attribution
- **Unstable** for SLO/alert thresholds

Full differential testing data: https://github.com/elang2/agent-budget-semantics