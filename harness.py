"""
Differential testing harness for agent budget semantics.

Orchestrates:
1. Start mock LLM server with scenario script
2. Run each framework runner against the same scenario
3. Collect results and compare dimensions
4. Produce divergence report
"""

import json
import sys
import time
import subprocess
import signal
import asyncio
import importlib.util
from pathlib import Path

import yaml
import requests


RUNNERS_DIR = Path(__file__).parent / "runners"
RESULTS_DIR = Path(__file__).parent / "results"
MOCK_URL = "http://127.0.0.1:9111"


def start_mock_server(scenario_path: str, port: int = 9111) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "mock-llm/server.py", f"--port={port}", f"--script={scenario_path}"],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if r.status_code == 200:
                return proc
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Mock LLM server failed to start")


def reset_mock(port: int = 9111):
    requests.post(f"http://127.0.0.1:{port}/reset")


def discover_runners() -> list[str]:
    return sorted([
        p.stem.replace("_runner", "")
        for p in RUNNERS_DIR.glob("*_runner.py")
    ])


async def run_single(runner_name: str, scenario_path: str, mock_url: str) -> dict:
    module_path = RUNNERS_DIR / f"{runner_name}_runner.py"
    spec = importlib.util.spec_from_file_location(f"{runner_name}_runner", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    reset_mock()
    time.sleep(0.1)

    result = await module.run_scenario(scenario_path, mock_url)
    return result


def compare_dimensions(results: list[dict]) -> dict:
    dimensions = ["D1_iteration_unit", "D2_token_accounting", "D3_enforcement_point", "D4_exhaustion_behavior"]
    comparison = {}

    for dim in dimensions:
        values = {}
        for r in results:
            fw = r.get("framework", "unknown")
            obs = r.get("observations", {}).get(dim, {})
            values[fw] = obs.get("value", "error")

        unique_values = set(values.values()) - {"unknown", "error", "needs_investigation"}
        comparison[dim] = {
            "values": values,
            "divergent": len(unique_values) > 1,
            "unique_interpretations": list(unique_values),
        }

    return comparison


def produce_report(scenario_name: str, results: list[dict], comparison: dict) -> dict:
    divergent_dims = [k for k, v in comparison.items() if v["divergent"]]

    return {
        "scenario": scenario_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frameworks_tested": [r.get("framework") for r in results],
        "frameworks_errored": [r.get("framework") for r in results if r.get("error")],
        "divergent_dimensions": divergent_dims,
        "total_dimensions": len(comparison),
        "divergence_count": len(divergent_dims),
        "comparison": comparison,
        "raw_results": results,
    }


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Agent Budget Semantics Differential Harness")
    parser.add_argument("scenario", nargs="?", help="Path to scenario YAML")
    parser.add_argument("--scenario", dest="scenario_flag", help="Path to scenario YAML (alternative)")
    parser.add_argument("--runners", nargs="*", help="Specific runners to use (default: all)")
    parser.add_argument("--frameworks", help="Comma-separated frameworks (alias for --runners)")
    parser.add_argument("--port", type=int, default=9111)
    parser.add_argument("--output", help="Output file (default: results/<scenario>.json)")
    args = parser.parse_args()

    scenario_path = args.scenario or args.scenario_flag
    if not scenario_path:
        parser.error("Specify scenario as positional arg or --scenario")

    if args.frameworks:
        runners_override = [r.strip() for r in args.frameworks.split(",")]
        if not args.runners:
            args.runners = runners_override

    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    scenario_name = scenario["name"]
    print(f"Running scenario: {scenario_name}")
    print(f"  Budget: {scenario['budget']}")
    print(f"  Script turns: {len(scenario.get('script', []))}")

    available = discover_runners()
    runners = args.runners if args.runners else available
    print(f"  Runners: {runners}")

    print("\nStarting mock LLM server...")
    mock_proc = start_mock_server(scenario_path, args.port)
    mock_url = f"http://127.0.0.1:{args.port}"

    results = []
    try:
        for runner_name in runners:
            if runner_name not in available:
                print(f"  SKIP {runner_name} (not found)")
                continue

            print(f"\n  Running: {runner_name}...")
            try:
                result = await run_single(runner_name, scenario_path, mock_url)
                results.append(result)
                if result.get("error"):
                    print(f"    ERROR: {result['error']}")
                else:
                    print(f"    LLM calls: {result.get('llm_calls_made', '?')}")
                    print(f"    Messages: {result.get('messages_produced', '?')}")
                    print(f"    Stopped: {result.get('stopped_reason', '?')}")
            except Exception as e:
                print(f"    FATAL: {e}")
                results.append({"framework": runner_name, "error": str(e)})
    finally:
        mock_proc.send_signal(signal.SIGTERM)
        mock_proc.wait(timeout=5)

    comparison = compare_dimensions(results)
    report = produce_report(scenario_name, results, comparison)

    RESULTS_DIR.mkdir(exist_ok=True)
    output_path = args.output or str(RESULTS_DIR / f"{scenario_name}.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"RESULTS: {scenario_name}")
    print(f"{'='*60}")
    print(f"Frameworks tested: {len(results)}")
    print(f"Frameworks errored: {len(report['frameworks_errored'])}")
    print(f"Divergent dimensions: {report['divergence_count']}/{report['total_dimensions']}")

    if report["divergent_dimensions"]:
        print(f"\nDIVERGENCES FOUND:")
        for dim in report["divergent_dimensions"]:
            c = comparison[dim]
            print(f"  {dim}:")
            for fw, val in c["values"].items():
                print(f"    {fw}: {val}")

    print(f"\nFull report: {output_path}")
    return report


if __name__ == "__main__":
    asyncio.run(main())
