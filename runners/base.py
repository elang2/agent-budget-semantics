"""Base class and shared utilities for framework runners."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RunResult:
    framework: str
    scenario: str
    budget_param: str
    budget_value: int | float
    actual_llm_calls: int
    actual_tool_calls: int
    stopped_by: str
    framework_token_count: Optional[int] = None
    framework_iteration_count: Optional[int] = None
    error: Optional[str] = None
    raw_output: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


TOOL_RESPONSES = {
    "get_weather": '{"temperature": 72, "condition": "sunny", "note": "Check nearby cities too"}',
    "calculate": '{"result": 42}',
}


def default_tool_handler(tool_name: str, arguments: str) -> str:
    """Return a canned response for known tools."""
    return TOOL_RESPONSES.get(tool_name, '{"status": "ok"}')
