"""Base class and shared utilities for framework runners."""

from dataclasses import dataclass, field, asdict
from typing import Optional


# Per-framework iteration-consumed derivation. Each framework counts its own
# budget differently against the same underlying execution (LLM calls / tool
# calls). The formulas encode each framework's counting semantics as observed
# in source-code analysis and validated against the mock LLM (see
# otel_comparison.FRAMEWORK_BUDGET_SEMANTICS and _calculate_consumed for the
# provenance).
#
# The spec-vocabulary iteration_budget_consumed field on RunResult is what
# a framework's OWN OpenTelemetry instrumentation would emit for
# `gen_ai.agent.iteration_budget.consumed` (issue #425). Runners that
# directly observe the framework's own counter can set this explicitly;
# otherwise __post_init__ derives it from raw counts using this table.

_ITERATION_CONSUMED_FORMULAS = {
    "autogen": lambda llm, tool: 1 + llm,
    "openai_agents": lambda llm, tool: llm,
    "langchain": lambda llm, tool: tool,
    "langgraph": lambda llm, tool: 1 + llm + tool,
    "crewai": lambda llm, tool: tool,
    "adk": lambda llm, tool: tool,
    "semantic_kernel": lambda llm, tool: tool,
    "anthropic": lambda llm, tool: llm,
    "swarm": lambda llm, tool: llm + (tool * 2),
    "llamaindex": lambda llm, tool: llm,
    "agno": lambda llm, tool: tool,
}


def iteration_budget_consumed_for(framework: str, llm_calls: int, tool_calls: int) -> int:
    """Return iterations consumed as the named framework would count them.

    Central table used by RunResult.__post_init__ and by otel_comparison's
    prediction model, so a single source of truth governs both.
    """
    formula = _ITERATION_CONSUMED_FORMULAS.get(framework)
    if formula is None:
        return llm_calls
    return formula(llm_calls, tool_calls)


@dataclass
class RunResult:
    framework: str
    scenario: str
    budget_param: str
    budget_value: int | float
    actual_llm_calls: int
    actual_tool_calls: int
    stopped_by: str
    iteration_budget_limit: Optional[int] = None
    iteration_budget_consumed: Optional[int] = None
    token_budget_limit: Optional[int] = None
    token_budget_consumed: Optional[int] = None
    # Subtree readings for supervisor runners delegating to sub-agents.
    # Left None on non-delegating runs; when populated, they fold in every
    # descendant agent's consumption. See tests/test_nested_delegation_split.py
    # for the direct-vs-subtree divergence this pair is here to make visible.
    iteration_budget_consumed_subtree: Optional[int] = None
    token_budget_consumed_subtree: Optional[int] = None
    error: Optional[str] = None
    raw_output: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        # Spec-vocabulary iteration_budget fields (issue #425). Every framework
        # tested here uses an iteration cap, so `limit` defaults to budget_value.
        # `consumed` defaults to the framework's own counting formula applied
        # to observed llm/tool counts. Runners can override either explicitly.
        if self.iteration_budget_limit is None and self.budget_value is not None:
            try:
                self.iteration_budget_limit = int(self.budget_value)
            except (TypeError, ValueError):
                pass
        if self.iteration_budget_consumed is None and self.stopped_by != "error":
            self.iteration_budget_consumed = iteration_budget_consumed_for(
                self.framework,
                self.actual_llm_calls,
                self.actual_tool_calls,
            )

    def to_dict(self) -> dict:
        return asdict(self)


TOOL_RESPONSES = {
    "get_weather": '{"temperature": 72, "condition": "sunny", "note": "Check nearby cities too"}',
    "calculate": '{"result": 42}',
}


def default_tool_handler(tool_name: str, arguments: str) -> str:
    """Return a canned response for known tools."""
    return TOOL_RESPONSES.get(tool_name, '{"status": "ok"}')
