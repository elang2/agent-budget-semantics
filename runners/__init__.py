"""
Framework runners. Each module exports a run() coroutine with signature:

    async def run(
        scenario: dict,
        mock_url: str,
        budget_config: dict,
    ) -> RunResult

RunResult is a dict with:
    - framework: str
    - budget_param: str
    - budget_value: int/float
    - actual_llm_calls: int (from framework's perspective)
    - actual_tool_calls: int (from framework's perspective)
    - stopped_by: str ("budget" | "natural" | "error")
    - framework_token_count: int | None (what framework reports)
    - error: str | None
"""
