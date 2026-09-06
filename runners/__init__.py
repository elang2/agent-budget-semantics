"""
Framework runners. Each module exports a run() coroutine with signature:

    async def run(
        scenario: dict,
        mock_url: str,
        budget_config: dict,
    ) -> RunResult

RunResult is a dict with:
    - framework: str
    - budget_param: str (framework-native config knob, e.g. max_iter, recursion_limit)
    - budget_value: int/float (framework-native config value)
    - actual_llm_calls: int (from framework's perspective)
    - actual_tool_calls: int (from framework's perspective)
    - stopped_by: str ("budget" | "natural" | "error")
    - iteration_budget_limit: int | None (spec attr gen_ai.agent.iteration_budget.limit)
    - iteration_budget_consumed: int | None (spec attr gen_ai.agent.iteration_budget.consumed)
    - token_budget_limit: int | None (spec attr gen_ai.agent.token_budget.limit)
    - token_budget_consumed: int | None (spec attr gen_ai.agent.token_budget.consumed)
    - error: str | None

The four *_budget_limit / *_budget_consumed fields are the spec-vocabulary
projection of each framework's native counters onto the attribute names
proposed in open-telemetry/semantic-conventions-genai#425. `None` means the
framework does not expose that quantity (e.g. no native cumulative token
budget for LangChain / LangGraph / OpenAI Agents / etc — see
expectations/expected_shape.yaml for the coverage matrix).
"""
