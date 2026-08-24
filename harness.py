"""
Differential testing harness for agent budget semantics.

Orchestrates:
1. Start mock LLM server with scenario script
2. For each framework, run the scenario with various budget configs
3. Compare results against the mock LLM ledger (ground truth)
4. Produce the divergence matrix

Usage:
    python harness.py --scenario scenarios/s2_budget_exhaustion.yaml
    python harness.py --scenario scenarios/s2_budget_exhaustion.yaml --frameworks autogen,adk
    python harness.py --all
"""

import argparse
import asyncio
import importlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

from runners.base import RunResult

RUNNERS = {
    "autogen": "runners.runner_autogen",
    "openai_agents": "runners.runner_openai_agents",
    "langchain": "runners.runner_langchain",
    "langgraph": "runners.runner_langgraph",
    "crewai": "runners.runner_crewai",
    "adk": "runners.runner_adk",
    "semantic_kernel": "runners.runner_semantic_kernel",
    "anthropic": "runners.runner_anthropic",
}

MOCK_PORT = 9111
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"


def start_mock_server(scenario_path: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "mock-llm/server.py", f"--port={MOCK_PORT}", f"--script={scenario_path}"],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        try:
            r = httpx.get(f"{MOCK_URL}/health", timeout=0.5)
            if r.status_code == 200:
                return proc
        except httpx.ConnectError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Mock LLM failed to start")


def reset_mock():
    httpx.post(f"{MOCK_URL}/reset")


def get_ledger() -> list[dict]:
    resp = httpx.get(f"{MOCK_URL}/ledger")
    data = resp.json()
    return data.get("entries", data) if isinstance(data, dict) else data


async def run_framework(framework: str, scenario: dict, budget_value: int) -> RunResult:
    module = importlib.import_module(RUNNERS[framework])
    return await module.run(scenario, MOCK_URL, budget_value)


async def run_scenario(scenario_path: str, frameworks: list[str]) -> list[dict]:
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    results = []

    for framework in frameworks:
        if framework not in RUNNERS:
            print(f"  Unknown framework: {framework}, skipping")
            continue

        budget_configs = scenario.get("budget_configs", {}).get(framework, {})
        values_to_test = budget_configs.get("values_to_test", [3])

        for budget_value in values_to_test:
            reset_mock()
            time.sleep(0.05)

            print(f"  {framework} (budget={budget_value})...", end=" ", flush=True)
            result = await run_framework(framework, scenario, budget_value)

            ledger = get_ledger()
            ledger_llm_calls = len(ledger)
            ledger_total_tokens = sum(e.get("total_tokens", 0) for e in ledger)
            ledger_tool_calls = sum(e.get("tool_calls_requested", 0) for e in ledger)

            comparison = {
                "framework": framework,
                "scenario": scenario["name"],
                "budget_param": result.budget_param,
                "budget_value": budget_value,
                "framework_reports": {
                    "llm_calls": result.actual_llm_calls,
                    "tool_calls": result.actual_tool_calls,
                    "stopped_by": result.stopped_by,
                    "token_count": result.framework_token_count,
                },
                "ground_truth": {
                    "llm_calls": ledger_llm_calls,
                    "tool_calls": ledger_tool_calls,
                    "total_tokens": ledger_total_tokens,
                },
                "divergences": {},
                "error": result.error,
            }

            if result.stopped_by != "error":
                if result.actual_tool_calls != ledger_tool_calls:
                    comparison["divergences"]["tool_call_count"] = {
                        "framework_says": result.actual_tool_calls,
                        "ledger_says": ledger_tool_calls,
                    }

            status = "OK" if not result.error else f"ERR: {result.error[:50]}"
            print(f"{result.stopped_by} | calls={ledger_llm_calls} tools={ledger_tool_calls} | {status}")

            results.append(comparison)

    return results


def print_matrix(all_results: list[dict]):
    print()
    print("=" * 80)
    print("DIVERGENCE MATRIX")
    print("=" * 80)

    by_scenario = {}
    for r in all_results:
        by_scenario.setdefault(r["scenario"], []).append(r)

    for scenario_name, results in by_scenario.items():
        print(f"\nScenario: {scenario_name}")
        print("-" * 80)
        fw_h = "Framework"
        p_h = "Param"
        b_h = "Budget"
        s_h = "Stopped"
        l_h = "LLM"
        t_h = "Tools"
        tk_h = "Tokens"
        print(f"{fw_h:<15} {p_h:<20} {b_h:<8} {s_h:<10} {l_h:<6} {t_h:<6} {tk_h:<8}")
        print("-" * 80)

        for r in results:
            gt = r["ground_truth"]
            fr = r["framework_reports"]
            fw = r["framework"]
            bp = r["budget_param"]
            bv = r["budget_value"]
            sb = fr["stopped_by"]
            lc = gt["llm_calls"]
            tc = gt["tool_calls"]
            tt = gt["total_tokens"]
            print(f"{fw:<15} {bp:<20} {bv:<8} {sb:<10} {lc:<6} {tc:<6} {tt:<8}")
            if r["divergences"]:
                for key, val in r["divergences"].items():
                    fs = val["framework_says"]
                    ls = val["ledger_says"]
                    print(f"  ^ {key}: framework={fs}, ground_truth={ls}")
            if r["error"]:
                err = r["error"][:70]
                print(f"  ! {err}")


async def main():
    parser = argparse.ArgumentParser(description="Agent budget semantics differential harness")
    parser.add_argument("--scenario", help="Path to a specific scenario YAML")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--frameworks", default=",".join(RUNNERS.keys()),
                        help="Comma-separated list of frameworks")
    parser.add_argument("--output", help="Write results JSON to this path")
    args = parser.parse_args()

    frameworks = [f.strip() for f in args.frameworks.split(",")]

    scenarios = []
    if args.all:
        scenario_dir = Path("scenarios")
        scenarios = sorted(scenario_dir.glob("s*.yaml"))
    elif args.scenario:
        scenarios = [Path(args.scenario)]
    else:
        parser.error("Specify --scenario or --all")

    print("Starting mock LLM server...")
    proc = start_mock_server(str(scenarios[0]))
    print(f"Mock LLM running on {MOCK_URL}\n")

    all_results = []
    try:
        for scenario_path in scenarios:
            print(f"Scenario: {scenario_path.name}")
            results = await run_scenario(str(scenario_path), frameworks)
            all_results.extend(results)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print_matrix(all_results)

    output_path = args.output or "results/latest.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults written to {output_path}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
