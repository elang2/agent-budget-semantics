"""
Report Generator — produces shareable markdown and structured JSON reports
from differential testing results.

Outputs:
  1. Divergence matrix (markdown table)
  2. Per-dimension evidence summary
  3. Framework comparison card
  4. OTel attribute recommendations
  5. JSON structured report for CI consumption
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from otel_comparison import FRAMEWORK_BUDGET_SEMANTICS, _calculate_consumed


def generate_divergence_matrix(llm_calls: int, tool_calls: int,
                                total_tokens: int, budget_limit: int,
                                scenario: str = "S2-budget-exhaustion",
                                harness_results: Optional[dict] = None) -> str:
    """Generate markdown divergence matrix.

    Prefers executed readings over the prediction model, per framework, and says
    which is which in a Provenance column. Before this, the matrix was generated
    entirely from _calculate_consumed() even for frameworks that had been run,
    so it reported the prediction model back as though it were measurement -- and
    kept reporting the PRE-CORRECTION model, which is why the published figures
    went stale against the data they were supposed to summarise.
    """
    if harness_results is None:
        harness_results = _load_harness_results(scenario)

    lines = []
    lines.append("# Divergence Matrix")
    lines.append("")
    lines.append(f"**Ground truth:** {llm_calls} LLM calls, {tool_calls} tool calls, {total_tokens} tokens")
    lines.append(f"**Comparison budget limit:** {budget_limit} (utilization denominator for every row)")
    lines.append("")
    lines.append("| Framework | Budget Param | budget | consumed | utilization | Provenance | Counting Method |")
    lines.append("|-----------|-------------|--------|----------|-------------|------------|-----------------|")

    consumed_values = set()
    uninformative = []
    executed_values = set()
    for fw, semantics in FRAMEWORK_BUDGET_SEMANTICS.items():
        hr = harness_results.get(fw)
        if hr is not None:
            consumed = hr["consumed_at_ground_truth"]
            provenance = "executed"
            budget_param = hr.get("budget_param") or semantics["budget_param"]
            budget_shown = hr.get("budget_value")
            budget_shown = budget_limit if budget_shown is None else budget_shown
        else:
            consumed = _calculate_consumed(fw, llm_calls, tool_calls)
            provenance = "modeled"
            budget_param = semantics["budget_param"]
            budget_shown = budget_limit

        method = semantics["iteration_definition"][:50]

        if consumed is None:
            # No counter was emitted. Printing the model's number here is exactly
            # the substitution this report used to make, and it erased the finding.
            uninformative.append(fw)
            consumed_cell = "n/a **NOT ENFORCED\\***"
            util_cell = "n/a"
            method = f"{method} (unvalidated: no unit observed)"
        else:
            consumed_values.add(consumed)
            if provenance == "executed":
                executed_values.add(consumed)
            util = consumed / budget_limit if budget_limit > 0 else 0
            exceeded = " **EXCEEDED**" if consumed > budget_limit else ""
            consumed_cell = f"{consumed}{exceeded}"
            util_cell = f"{util:.0%}"

        lines.append(
            f"| {fw} | `{budget_param}` | {budget_shown} | {consumed_cell} | "
            f"{util_cell} | {provenance} | {method} |"
        )

    lines.append("")
    lines.append(f"**Unique consumed values:** `{sorted(consumed_values)}`")
    # Not "N answers for same execution". Only the executed rows ran, so the
    # all-rows set mixes readings with predictions and cannot be described as
    # answers to one execution. The executed subset is the comparable one.
    lines.append(f"**Spread across all {len(FRAMEWORK_BUDGET_SEMANTICS)} rows:** "
                 f"`{sorted(consumed_values)}` — {len(consumed_values)} distinct values, "
                 f"mixing rows that were run with rows predicted from source.")
    lines.append(f"**Executed rows only:** `{sorted(executed_values)}` "
                 f"({len(executed_values)} distinct values). This is the only subset in "
                 f"which every value is a reading of the same workload.")
    lines.append("")
    lines.append("## Reading this table")
    lines.append("")
    lines.append("- **Provenance** `executed` means the row is a reading taken from a run "
                 "against the mock LLM. `modeled` means it is a prediction derived from "
                 "reading the framework's source, and has not been run.")
    lines.append("- **consumed** is normalised to the shared ground-truth workload above, "
                 "so rows are comparable even where the executed run configured a "
                 "different budget. **budget** is the limit that run actually configured; "
                 "**utilization** uses the single comparison limit so the column is "
                 f"commensurable, which means utilization is not consumed/budget where "
                 f"the two differ. LangGraph is the one such row: it ran at "
                 f"recursion_limit=6, and its utilization is reported against {budget_limit}.")
    if uninformative:
        lines.append(
            "- **" + ", ".join(uninformative) + "** "
            + ("reports" if len(uninformative) == 1 else "report")
            + " no consumed value at all. The budget parameter exists, propagates, and "
              "its enforcement code runs, but enforcement is cooperative: on reaching "
              "the limit the framework asks the provider to stop calling tools and has "
              "no client-side refusal if the provider calls one anyway. Against a "
              "provider that ignored the request it continued past the declared limit "
              "and emitted no counter. Against one that honoured it the limit held. "
              "Both conditions are recorded in results/S2-toolchoice-2026-10-04.json. "
              "This is a measurement, "
              "not a gap: scored as `n/a`, excluded from the disagreement count, and "
              "never replaced by the prediction model's number. The Counting Method "
              "shown for such a row is the unvalidated source-code model, since no "
              "unit was observed to validate it against.")
    lines.append("")

    return "\n".join(lines)


def generate_dimension_evidence(scenarios_results: Optional[list] = None) -> str:
    """Generate per-dimension evidence summary."""
    dimensions = {
        "D1": ("Iteration unit", "What counts as one iteration?", [
            ("AutoGen", "message (LLM response OR tool result)"),
            ("OpenAI Agents", "LLM invocation"),
            ("LangChain", "tool-use cycle (action + observation)"),
            ("LangGraph", "graph node execution"),
            ("Semantic Kernel", "auto-invoke round"),
            ("Swarm", "messages added to history"),
        ]),
        "D5": ("Delegation budget", "How is budget shared across delegated agents?", [
            ("AutoGen", "shared pool across group chat"),
            ("CrewAI", "each agent gets independent budget"),
            ("ADK", "remaining budget passed to sub-agent"),
            ("Agno", "team-level shared pool"),
        ]),
        "D7": ("Parallel tool counting", "N parallel tools = how many budget units?", [
            ("OpenAI Agents", "1 (batch = 1 turn)"),
            ("AutoGen", "N (each tool result = separate message)"),
            ("LangChain", "1 (batch = 1 iteration)"),
            ("Swarm", "2N (each tool = request + result messages)"),
        ]),
        "D9": ("Error/retry counting", "Does a failed+retry consume 1 or 2 units?", [
            ("AutoGen", "2 (retry is new turn)"),
            ("CrewAI", "1 (retries are free)"),
            ("LangGraph", "2 (each is a graph step)"),
            ("Semantic Kernel", "1 (failed invoke doesn't decrement)"),
        ]),
        "D11": ("Token budget enforcement", "Cumulative token tracking?", [
            ("AutoGen", "via callback (configurable)"),
            ("ADK", "configurable cumulative"),
            ("Agno", "output tokens only"),
            ("Most others", "per-call max_tokens only"),
        ]),
        "D15": ("Tool output tokens", "Do tool outputs count in budget?", [
            ("AutoGen", "configurable via callbacks"),
            ("LangChain", "no (only LLM tokens)"),
            ("Agno", "no (output tokens only)"),
            ("ADK", "configurable"),
        ]),
        "D19": ("Nested delegation", "Budget inheritance across 3+ levels?", [
            ("AutoGen", "shared pool total"),
            ("CrewAI", "each agent independent"),
            ("ADK", "remaining passed down"),
            ("LangGraph", "recursion_limit minus consumed"),
        ]),
        "D21": ("Timeout budget impact", "Does timeout consume budget?", [
            ("AutoGen", "yes (turn consumed)"),
            ("CrewAI", "no (free retry policy)"),
            ("Semantic Kernel", "yes (attempt consumed)"),
            ("LangGraph", "yes (step consumed)"),
        ]),
    }

    lines = []
    lines.append("# Dimension Evidence Summary")
    lines.append("")
    lines.append(f"**Frameworks tested:** {len(FRAMEWORK_BUDGET_SEMANTICS)}")
    lines.append(f"**Dimensions discovered:** {len(dimensions)} primary + sub-dimensions")
    lines.append("")

    for dim_id, (name, question, evidence) in dimensions.items():
        lines.append(f"## {dim_id}: {name}")
        lines.append("")
        lines.append(f"**Question:** {question}")
        lines.append("")
        lines.append("| Framework | Behavior |")
        lines.append("|-----------|----------|")
        for fw, behavior in evidence:
            lines.append(f"| {fw} | {behavior} |")
        lines.append("")

    return "\n".join(lines)


def generate_framework_cards(scenario: str = "S2-budget-exhaustion") -> str:
    """Generate per-framework comparison cards.

    The cards used to render FRAMEWORK_BUDGET_SEMANTICS alone, which is the
    source-reading model and knows nothing about what happened when the
    framework ran. So the Agno card said `max_iterations` with no enforcement
    status while the divergence matrix, which prefers the executed reading,
    said `Agent(tool_call_limit=N)` and `NOT ENFORCED` -- two generated
    artefacts in the same directory disagreeing about the headline finding.
    Each card now carries the executed row's provenance and enforcement
    status, so it cannot drift from the matrix.
    """
    executed = _load_harness_results(scenario)
    lines = []
    lines.append("# Framework Budget Semantics Cards")
    lines.append("")
    lines.append("Each card's first rows are the source-reading model. `Provenance` and")
    lines.append("`Enforcement observed` come from the executed run where there is one;")
    lines.append("where the two disagree about a parameter name, the run governs.")
    lines.append("")

    for fw, semantics in FRAMEWORK_BUDGET_SEMANTICS.items():
        lines.append(f"## {fw}")
        lines.append("")
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        for key, value in semantics.items():
            lines.append(f"| {key.replace('_', ' ').title()} | {value} |")
        row = executed.get(fw)
        if row is None:
            lines.append("| Provenance | modeled — not run, so no enforcement observation |")
        else:
            lines.append("| Provenance | executed |")
            observed_param = row.get("budget_param")
            if observed_param and observed_param != semantics.get("budget_param"):
                lines.append(f"| Budget Param As Run | `{observed_param}` |")
            # `enforced` is NOT an observation. No code in runners/ or
            # harness.py produces it -- grep returns nothing -- so it is the
            # author's classification of the row, exactly like
            # counter_at_budget_stop and unit_observed. Labelling it
            # "Enforcement observed" would make a judgement look like a
            # reading, which is the defect this whole report suite exists to
            # avoid. The measured mechanism lives in
            # results/S2-toolchoice-2026-10-04.json under `mechanisms`, which
            # is derived from per-request ledgers.
            enforced = row.get("enforced")
            if enforced is False:
                lines.append("| Enforcement (author classification) | limit did not hold "
                             "in the recorded run — mechanism measured in "
                             "results/S2-toolchoice-2026-10-04.json |")
            elif enforced is True:
                lines.append("| Enforcement (author classification) | limit held in the "
                             "recorded run |")
            else:
                lines.append("| Enforcement (author classification) | not classified |")
        lines.append("")

    return "\n".join(lines)


def generate_otel_recommendations(disagreement_factor: Optional[int] = None,
                                   executed_count: Optional[int] = None,
                                   modeled_count: Optional[int] = None) -> str:
    """Generate OTel attribute specification recommendations.

    The framework and divergence counts are passed in rather than written into
    the text. Hardcoded, they went stale: this report said "4+ different values"
    and "across 11 frameworks" while the data said five values across eight
    executed frameworks and three modeled ones.
    """
    total = len(FRAMEWORK_BUDGET_SEMANTICS)
    lines = []
    lines.append("# OTel Semantic Convention Recommendations")
    lines.append("")
    if executed_count is not None and modeled_count is not None:
        lines.append(f"Based on {total} frameworks: {executed_count} executed against the")
        lines.append(f"mock LLM, {modeled_count} modeled from source and not run. Only the")
        lines.append("executed rows are differential testing; the modeled rows are predictions.")
    else:
        lines.append(f"Based on differential testing across {total} frameworks.")
    lines.append("")

    lines.append("## Problem Statement")
    lines.append("")
    lines.append("The proposed `gen_ai.agent.iteration_budget.consumed` attribute")
    if disagreement_factor is not None:
        lines.append(f"takes {disagreement_factor} distinct values across the instrumented")
        lines.append("frameworks, and one framework emits no value at all. Of those values,")
        lines.append("only the ones from executed rows are readings of the same workload; the")
        lines.append("rest are predictions from source. Either way the attribute is not")
        lines.append("comparable across implementations without a declared counting unit.")
    else:
        lines.append("takes multiple distinct values depending on")
        lines.append("which framework is instrumented. A declared unit would make each")
        lines.append("counter legible without making counters comparable, which is why the")
        lines.append("upstream proposal was withdrawn rather than amended.")
    lines.append("")

    lines.append("## Recommendation 1: do not name a cross-framework consumed count")
    lines.append("")
    lines.append("An earlier revision of this report recommended a mandatory")
    lines.append("`gen_ai.agent.iteration_budget.counting_method` enum. That recommendation")
    lines.append("does not survive its own evidence and is retired. A declared unit makes a")
    lines.append("counter legible; it does not make two counters comparable, because the")
    lines.append("quantities being counted differ. The upstream proposal carrying these")
    lines.append("attributes was closed on 2026-08-27 after maintainer review concluded the")
    lines.append("values are not comparable across implementations with or without a unit.")
    lines.append("")
    lines.append("The units observed are recorded below as measurement, not as a proposed")
    lines.append("enum, since the measurement is the contribution:")
    lines.append("")
    lines.append("```")
    lines.append("  llm_calls          (OpenAI Agents, LlamaIndex, Anthropic)")
    lines.append("  tool_cycles        (LangChain, CrewAI, ADK, SK)")
    lines.append("  graph_nodes        (LangGraph)")
    lines.append("  messages           (AutoGen, Swarm)")
    lines.append("  not_emitted        (Agno)")
    lines.append("```")
    lines.append("")
    lines.append("LlamaIndex sits under `llm_calls`, not `tool_cycles`: execution showed")
    lines.append("`max_iterations` counting LLM responses. Agno gets no counting method")
    lines.append("because it emitted no counter -- its budget parameter exists and")
    lines.append("propagates, but enforcement is cooperative, so against a provider that")
    lines.append("ignored the request it ran past the limit with no unit to classify.")
    lines.append("A spec enum needs a value for that case, or every")
    lines.append("non-enforcing implementation will be recorded under a method it does")
    lines.append("not implement. See results/S2-executed.json and")
    lines.append("results/S2-toolchoice-2026-10-04.json for both provider conditions.")
    lines.append("")

    lines.append("## Recommendation 2: Parallel tool batch semantics")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.parallel_tool_counting")
    lines.append("  Values:")
    lines.append("    - batch_as_one       (LangChain, OpenAI, ADK, SK, Agno)")
    lines.append("    - individual         (AutoGen, Swarm)")
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation 3: Error/retry policy")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.retry_budget_policy")
    lines.append("  Values:")
    # Semantic Kernel was listed under retry_consumes against this project's
    # own S5 data, whose note for that row reads "Retries appear to be free
    # (not counted)" after 4 LLM calls with stopped_by=completed. LangGraph's
    # S5 row is also not evidence for retry_consumes: it completed with 1 LLM
    # call where the scenario scripts 3, and its own note calls that
    # unexpected, so it is unclassified rather than classified.
    lines.append("    - retry_consumes     (AutoGen — S5 reading: stopped at budget "
                 "after 3 calls)")
    lines.append("    - retry_free         (Semantic Kernel — S5 reading: 4 calls, "
                 "retries not counted; CrewAI — source reading, not run on S5)")
    lines.append("    - configurable       (LangChain — source reading; its S5 run "
                 "errored at 0 calls)")
    lines.append("    - unclassified       (LangGraph — S5 run completed in 1 call "
                 "against a 3-call scenario; not evidence either way)")
    lines.append("")
    lines.append("  Only four frameworks were run on S5, and that file sits outside the")
    lines.append("  per-cell validity contract, so every entry above is marked with")
    lines.append("  whether it is a reading or a source reading.")
    lines.append("```")
    lines.append("")

    lines.append("## Recommendation 4: Token budget scope")
    lines.append("")
    lines.append("```")
    lines.append("gen_ai.agent.token_budget.scope")
    lines.append("  Values:")
    lines.append("    - llm_output_only    (Agno)")
    lines.append("    - llm_total          (most)")
    lines.append("    - including_tools    (configurable in AutoGen, ADK)")
    lines.append("    - per_call_only      (SK, Swarm)")
    lines.append("```")
    lines.append("")

    lines.append("## Evidence")
    lines.append("")
    lines.append("Without these enums, `gen_ai.agent.iteration_budget.consumed` is:")
    lines.append("- **Not comparable** across frameworks")
    lines.append("- **Misleading** in multi-framework dashboards")
    lines.append("- **Incorrect** for cost attribution")
    lines.append("- **Unstable** for SLO/alert thresholds")
    lines.append("")
    lines.append("Full differential testing data: https://github.com/elang2/agent-budget-semantics")

    return "\n".join(lines)


FRAMEWORK_VERSIONS = {
    "autogen": {"package": "autogen-agentchat", "version": "0.4.7", "tier": "modeled"},
    "openai_agents": {"package": "openai-agents", "version": "0.1.1", "tier": "modeled"},
    "langchain": {"package": "langchain", "version": "0.3.14", "tier": "modeled"},
    "langgraph": {"package": "langgraph", "version": "0.3.21", "tier": "modeled"},
    "crewai": {"package": "crewai", "version": "0.108.0", "tier": "modeled"},
    "adk": {"package": "google-adk", "version": "1.2.1", "tier": "modeled"},
    "semantic_kernel": {"package": "semantic-kernel", "version": "1.17.1", "tier": "modeled"},
    "anthropic": {"package": "anthropic", "version": "0.39.0", "tier": "modeled"},
    "swarm": {"package": "openai-swarm", "version": "0.1.0", "tier": "archived"},
    "llamaindex": {"package": "llama-index-core", "version": "0.11.23", "tier": "modeled"},
    "agno": {"package": "agno", "version": "1.2.5", "tier": "modeled"},
}


def _scenario_key(name) -> str:
    """Normalise a scenario identifier for comparison.

    "S2 - Budget Exhaustion" (what harness.py writes, from the scenario YAML's
    `name`) and "S2-budget-exhaustion" (the slug every caller passes) are the
    same scenario, and comparing them with `==` silently matched nothing.
    """
    if not name:
        return ""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _load_harness_results(scenario: str) -> dict:
    """Load executed harness results. Returns {framework: result_dict}.

    Refuses to return silently empty. `Path("results").glob("*.json")` on an
    absent directory yields nothing and raises nothing, so a run from a clean
    install or from the wrong working directory produced zero executed rows,
    every row fell back to the prediction model, and the report showed Agno at
    the modelled 3 labelled "modeled" where the reading is 10. A report that
    substitutes the model for the measurement and says nothing is the one
    output this project must not produce, so the absence is now an error with
    the remedy in it rather than a quiet downgrade.

    Set ABS_ALLOW_MODELLED_ONLY=1 to override, which is for generating a
    report deliberately without readings and is not a supported citation path.
    """
    # Two candidates, in this order. The working directory comes first so a
    # developer's freshly-run results override the shipped ones; the directory
    # beside this module comes second so an installed copy works at all.
    # Shipping results/ in the wheel was necessary but not sufficient -- the
    # lookup was CWD-only, so the packaged data sat unread in site-packages
    # while the report fell back to the model.
    candidates = [Path("results"), Path(__file__).resolve().parent / "results"]
    results_dir = next(
        (c for c in candidates if c.is_dir() and any(c.glob("*.json"))),
        None,
    )
    if results_dir is None:
        if os.environ.get("ABS_ALLOW_MODELLED_ONLY"):
            return {}
        looked = "\n".join(f"  {c.resolve()}" for c in candidates)
        raise SystemExit(
            "no executed results found. Looked in:\n" + looked + "\n\n"
            "Every row would fall back to the prediction model and be labelled\n"
            "'modeled', which silently replaces the executed readings -- Agno would\n"
            "read 3 instead of the observed 10. That substitution is the one thing\n"
            "the validity contract exists to refuse, so this is an error rather than\n"
            "a quiet downgrade.\n\n"
            "Run from the project root, or reinstall: results/ ships in the wheel and\n"
            "the container as of 0.5.1.\n"
            "To generate a model-only report anyway, set ABS_ALLOW_MODELLED_ONLY=1."
        )
    # harness.py writes the scenario's YAML `name` ("S2 - Budget Exhaustion")
    # while every caller here passes the slug ("S2-budget-exhaustion"), so an
    # equality test never matched and `report` after a `run` silently produced
    # an all-modelled report. Compare on a normalised form instead: lowercase,
    # non-alphanumerics collapsed. The guard below then refuses a zero-row
    # match, which the previous no-directory-only guard could not see.
    want = _scenario_key(scenario)
    files_seen = 0
    executed = {}
    # Deterministic precedence, and the curated evidence wins. Making the
    # scenario comparison work meant scratch `harness.py --output` files in
    # results/ now match too, and glob order is filesystem-dependent, so a
    # throwaway run could silently have overridden a curated reading in a
    # published report. Curated `*-executed.json` files are read LAST so later
    # assignment makes them authoritative, and both groups are sorted so two
    # machines produce the same report from the same directory.
    paths = sorted(results_dir.glob("*.json"))
    ordered = ([q for q in paths if not q.name.endswith("-executed.json")]
               + [q for q in paths if q.name.endswith("-executed.json")])
    for path in ordered:
        files_seen += 1
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                for entry in data:
                    if _scenario_key(entry.get("scenario")) == want:
                        fw = entry["framework"]
                        executed[fw] = entry
            elif isinstance(data, dict) and _scenario_key(data.get("scenario")) == want:
                if "frameworks" in data and isinstance(data["frameworks"], dict):
                    for fw, fw_data in data["frameworks"].items():
                        # Read whether the KEY is present, never whether its value is
                        # truthy. `a or b` treats a legitimate null -- and a legitimate
                        # 0 -- as absent. That is how agno used to be dropped here: it
                        # was executed, its budget was not enforced, no counter was
                        # emitted, so consumed_at_ground_truth is null by MEASUREMENT.
                        # The `if consumed is not None` gate below it then excluded the
                        # row from the executed set altogether, and generate_json_report
                        # re-materialised it from the prediction model as consumed=3 and
                        # relabelled it "modeled" -- a number for a counter that never
                        # emitted, erasing the finding. A null row is kept and carried.
                        if "consumed_at_ground_truth" in fw_data:
                            consumed = fw_data["consumed_at_ground_truth"]
                        elif "consumed" in fw_data:
                            consumed = fw_data["consumed"]
                        else:
                            # Neither key present: this row carries no reading of any
                            # kind, which is different from a row carrying a null one.
                            continue
                        executed[fw] = {
                            "framework": fw,
                            "scenario": scenario,
                            "consumed_at_ground_truth": consumed,
                            "unit_observed": fw_data.get("unit_observed"),
                            "enforced": fw_data.get("enforced", True),
                            "framework_version": fw_data.get("version"),
                            "provenance": data.get("provenance", "executed"),
                            # Per-cell validity contract (see the `schema` block and
                            # `validity_contract` in results/S2-executed.json).
                            "tier": fw_data.get("tier", "executed"),
                            "status": fw_data.get("status"),
                            "reason": fw_data.get("reason"),
                            # Observed API surface. Preferred over the model's
                            # budget_param, which is a reading of the source, not of
                            # the run -- and which is wrong for agno (`max_iterations`
                            # where the real parameter is `tool_call_limit`).
                            "budget_param": fw_data.get("budget_param"),
                            "budget_value": fw_data.get("budget_value"),
                        }
                elif "framework" in data:
                    executed[data["framework"]] = data
        except (json.JSONDecodeError, KeyError):
            continue

    # The guard that matters, and the one the earlier version could not see.
    # It checked only that results/ existed and held some .json, which was true
    # in exactly the state that produced a silently all-modelled report: a
    # directory full of harness output whose scenario field matched nothing.
    # Zero matched rows has the same consequence as an empty directory, so it
    # raises for the same reason.
    if not executed and not os.environ.get("ABS_ALLOW_MODELLED_ONLY"):
        raise SystemExit(
            f"no executed rows matched scenario {scenario!r}.\n"
            f"Read {files_seen} JSON file(s) in {results_dir.resolve()} and none "
            f"carried a matching scenario.\n\n"
            "Every row would fall back to the prediction model and be labelled\n"
            "'modeled', which silently replaces the executed readings. That\n"
            "substitution is the one thing the validity contract exists to refuse.\n\n"
            "If these are files `harness.py` wrote, check the scenario name: the\n"
            "harness records the scenario YAML's `name` while the report asks for\n"
            "the slug. Both forms are accepted now, so a mismatch here means a\n"
            "genuinely different scenario.\n"
            "To generate a model-only report anyway, set ABS_ALLOW_MODELLED_ONLY=1."
        )
    return executed


def generate_json_report(scenario: str, llm_calls: int, tool_calls: int,
                          total_tokens: int, budget_limit: int,
                          harness_results: Optional[dict] = None) -> dict:
    """Generate structured JSON report.

    Prefers harness-executed results (provenance: "executed") when available
    in results/. Falls back to _calculate_consumed() model predictions
    (provenance: "modeled") only for a framework with no executed row at all --
    never for an executed row whose consumed reading is legitimately null.
    """
    if harness_results is None:
        harness_results = _load_harness_results(scenario)

    results = {}
    for fw in FRAMEWORK_BUDGET_SEMANTICS:
        if fw in harness_results:
            hr = harness_results[fw]
            # An executed row stays executed. Its consumed reading may legitimately
            # be None -- that is the measurement for a framework that ran without
            # enforcing its budget -- and None must NOT fall through to the
            # prediction model. The old `or`-chain plus `if consumed is None:
            # consumed = _calculate_consumed(...)` did exactly that, turning agno's
            # "no counter was emitted" into "consumed 3, provenance modeled". The
            # only remaining fallback is for a framework with no executed row at all.
            consumed = hr["consumed_at_ground_truth"]
            provenance = hr.get("provenance", "executed")
            version = hr.get("framework_version") or FRAMEWORK_VERSIONS.get(fw, {}).get("version", "unknown")
            status = hr.get("status")
            reason = hr.get("reason")
            enforced = hr.get("enforced", True)
            budget_param = hr.get("budget_param") or FRAMEWORK_BUDGET_SEMANTICS[fw]["budget_param"]
        else:
            consumed = _calculate_consumed(fw, llm_calls, tool_calls)
            provenance = "modeled"
            version = FRAMEWORK_VERSIONS.get(fw, {}).get("version", "unknown")
            # A modeled row is a source-code prediction, not a validity reading.
            # It is neither informative nor uninformative in the sense of the
            # validity contract, which gates measurements.
            status = "modeled_not_measured"
            reason = None
            enforced = None
            budget_param = FRAMEWORK_BUDGET_SEMANTICS[fw]["budget_param"]

        results[fw] = {
            "consumed": consumed,
            "utilization": (
                round(consumed / budget_limit, 2)
                if consumed is not None and budget_limit > 0 else None
            ),
            "exceeded": consumed > budget_limit if consumed is not None else None,
            "budget_param": budget_param,
            # Named counting_unit, not counting_method: the retired proposal in
            # Recommendation 1 was an OTel attribute spelled
            # gen_ai.agent.iteration_budget.counting_method, and reusing that word
            # here makes a reader think the report still proposes it.
            "counting_unit": FRAMEWORK_BUDGET_SEMANTICS[fw]["iteration_definition"],
            "provenance": provenance,
            "version": version,
            "tier": hr.get("tier", "executed") if fw in harness_results
                    else FRAMEWORK_VERSIONS.get(fw, {}).get("tier", "modeled"),
            "status": status,
            "reason": reason,
            "enforced": enforced,
        }

    # None is excluded from the disagreement set: a framework that reported no
    # value did not report a DIFFERENT value, and folding it in either way would
    # misstate the count. It is reported separately as `uninformative`.
    consumed_values = sorted(
        {r["consumed"] for r in results.values() if r["consumed"] is not None}
    )
    executed_count = sum(1 for r in results.values() if r["provenance"] == "executed")
    modeled_count = sum(1 for r in results.values() if r["provenance"] == "modeled")

    # Overlay the executed tier and version onto the static table. Left alone, the
    # static table reports every framework at its modeled tier and modeled version
    # even where an executed row exists -- and a hand-edited report.json once
    # claimed tier "executed" for all eleven, including adk and anthropic, which
    # were never run, and swarm, which is archived. Tier is derived, not typed.
    framework_versions = {}
    for fw, meta in FRAMEWORK_VERSIONS.items():
        entry = dict(meta)
        if fw in harness_results:
            entry["tier"] = harness_results[fw].get("tier", "executed")
            if harness_results[fw].get("framework_version"):
                entry["version"] = harness_results[fw]["framework_version"]
        framework_versions[fw] = entry

    informative = [fw for fw, r in results.items()
                   if r["provenance"] == "executed" and r["status"] == "informative"]
    uninformative = [fw for fw, r in results.items()
                     if r["provenance"] == "executed" and r["status"] == "uninformative"]

    return {
        "scenario": scenario,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ground_truth": {
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "total_tokens": total_tokens,
            "budget_limit": budget_limit,
        },
        "framework_versions": framework_versions,
        "frameworks": results,
        "summary": {
            "unique_consumed_values": consumed_values,
            "disagreement_factor": len(consumed_values),
            "frameworks_exceeded": [
                fw for fw, r in results.items() if r["exceeded"]
            ],
            "frameworks_uninformative": uninformative,
            "provenance_breakdown": {
                "executed": executed_count,
                "modeled": modeled_count,
            },
            "denominators": {
                "rows_total": len(results),
                "rows_executed": executed_count,
                "rows_informative": len(informative),
                "rows_uninformative": len(uninformative),
                "note": (
                    "disagreement_factor counts distinct non-null consumed values. "
                    "A row whose consumed is null reported no value rather than a "
                    "different one, and is counted in rows_uninformative instead of "
                    "being scored as agreement or disagreement. Validity gate after "
                    "arXiv:2608.29930 section 4.3: such a cell scores None, not zero. "
                    "rows_informative and rows_uninformative partition rows_executed "
                    "only. The remaining rows_total - rows_executed rows are modeled: "
                    "a source-code prediction is not a measurement and does not share "
                    "a denominator with one. See summary.provenance_breakdown."
                ),
            },
        },
    }


def write_full_report(output_dir: str = "reports"):
    """Generate all report artifacts."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load once and pass to both consumers, so the matrix and the JSON report
    # cannot summarise two different reads of the same tree.
    scenario = "S2-budget-exhaustion"
    harness_results = _load_harness_results(scenario)

    matrix = generate_divergence_matrix(
        llm_calls=4, tool_calls=3, total_tokens=800, budget_limit=3,
        scenario=scenario, harness_results=harness_results,
    )
    (out / "divergence-matrix.md").write_text(matrix)

    evidence = generate_dimension_evidence()
    (out / "dimension-evidence.md").write_text(evidence)

    cards = generate_framework_cards()
    (out / "framework-cards.md").write_text(cards)

    report = generate_json_report(
        scenario=scenario,
        llm_calls=4, tool_calls=3, total_tokens=800, budget_limit=3,
        harness_results=harness_results,
    )

    # Derived from the report that was just built off the same load, so the
    # recommendations cannot cite a divergence count the data no longer supports.
    recommendations = generate_otel_recommendations(
        disagreement_factor=report["summary"]["disagreement_factor"],
        executed_count=report["summary"]["provenance_breakdown"]["executed"],
        modeled_count=report["summary"]["provenance_breakdown"]["modeled"],
    )
    (out / "otel-recommendations.md").write_text(recommendations)

    (out / "report.json").write_text(json.dumps(report, indent=2))

    print(f"Reports written to {output_dir}/")
    print(f"  divergence-matrix.md")
    print(f"  dimension-evidence.md")
    print(f"  framework-cards.md")
    print(f"  otel-recommendations.md")
    print(f"  report.json")


if __name__ == "__main__":
    write_full_report()
