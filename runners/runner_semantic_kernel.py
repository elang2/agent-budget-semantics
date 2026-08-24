"""
Semantic Kernel budget enforcement runner.

Budget primitive: FunctionChoiceBehavior.Auto(maximum_auto_invoke_attempts=N)
What it counts: Each round of auto-invocation (parallel tool calls = 1 round)
Unique: No native token budget on the loop. max_tokens caps output per call only.
"""

import json
from typing import Any

from .base import RunResult, default_tool_handler


async def run(scenario: dict, mock_url: str, budget_value: int) -> RunResult:
    """Run scenario through Semantic Kernel with maximum_auto_invoke_attempts."""
    try:
        from semantic_kernel import Kernel
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
        from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
        from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_chat_prompt_execution_settings import OpenAIChatPromptExecutionSettings
        from semantic_kernel.contents.chat_history import ChatHistory
        from semantic_kernel.functions import kernel_function
    except ImportError as e:
        return RunResult(
            framework="semantic_kernel",
            scenario=scenario["name"],
            budget_param="maximum_auto_invoke_attempts",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=0,
            stopped_by="error",
            error=f"Import failed: {e}",
        )

    tool_calls_observed = 0

    kernel = Kernel()
    service = OpenAIChatCompletion(
        service_id="mock",
        ai_model_id="mock-budget-llm",
        base_url=mock_url + "/v1",
        api_key="mock-key",
    )
    kernel.add_service(service)

    class WeatherPlugin:
        @kernel_function(name="get_weather", description="Get weather for a city")
        def get_weather(self, city: str) -> str:
            nonlocal tool_calls_observed
            tool_calls_observed += 1
            return default_tool_handler("get_weather", json.dumps({"city": city}))

        @kernel_function(name="calculate", description="Perform arithmetic")
        def calculate(self, expression: str) -> str:
            nonlocal tool_calls_observed
            tool_calls_observed += 1
            return default_tool_handler("calculate", json.dumps({"expression": expression}))

    kernel.add_plugin(WeatherPlugin(), plugin_name="tools")

    settings = OpenAIChatPromptExecutionSettings(
        service_id="mock",
        function_choice_behavior=FunctionChoiceBehavior.Auto(
            maximum_auto_invoke_attempts=budget_value
        ),
    )

    history = ChatHistory()
    history.add_system_message("You are a helpful assistant. Use tools when needed.")
    history.add_user_message("Perform the requested task.")

    try:
        chat_service = kernel.get_service("mock")
        result = await chat_service.get_chat_message_contents(
            chat_history=history,
            settings=settings,
            kernel=kernel,
        )

        import httpx
        ledger = httpx.get(f"{mock_url}/ledger").json()
        ledger_entries = ledger.get("entries", ledger) if isinstance(ledger, dict) else ledger
        llm_calls = len(ledger_entries)

        return RunResult(
            framework="semantic_kernel",
            scenario=scenario["name"],
            budget_param="maximum_auto_invoke_attempts",
            budget_value=budget_value,
            actual_llm_calls=llm_calls,
            actual_tool_calls=tool_calls_observed,
            stopped_by="completed" if result else "empty",
            framework_token_count=None,
            metadata={
                "note": "SK counts auto-invoke rounds, not individual tool calls. "
                       "3 parallel tool calls in one response = 1 attempt consumed.",
            },
        )

    except Exception as e:
        return RunResult(
            framework="semantic_kernel",
            scenario=scenario["name"],
            budget_param="maximum_auto_invoke_attempts",
            budget_value=budget_value,
            actual_llm_calls=0,
            actual_tool_calls=tool_calls_observed,
            stopped_by="error",
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )
