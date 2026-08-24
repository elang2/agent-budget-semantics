#!/usr/bin/env python3
"""
CLI for agent-budget-semantics.

Usage:
    agent-budget-semantics compare           # Show iteration divergence matrix
    agent-budget-semantics cost              # Show cost divergence
    agent-budget-semantics spans             # Show OTel span divergence
    agent-budget-semantics report            # Generate full report suite
    agent-budget-semantics run --all         # Run full differential test suite
    agent-budget-semantics run --scenario S2 # Run specific scenario
    agent-budget-semantics dimensions        # Print dimension taxonomy
"""

import argparse
import sys


def cmd_compare(args):
    from otel_comparison import print_comparison

    if args.scenario == "S4":
        print_comparison(
            scenario="S4-parallel-tools",
            budget_limit=2, llm_calls=2, tool_calls=3, total_tokens=370
        )
    else:
        print_comparison(
            scenario="S2-budget-exhaustion",
            budget_limit=3, llm_calls=4, tool_calls=3, total_tokens=478
        )


def cmd_cost(args):
    from cost_divergence import print_cost_comparison, print_monthly_projection

    print_cost_comparison(
        scenario="S2-budget-exhaustion (typical agent loop)",
        llm_calls=args.llm_calls, tool_calls=args.tool_calls,
        input_tokens=args.input_tokens, output_tokens=args.output_tokens,
        pricing_key=args.pricing,
    )

    if args.daily_runs:
        print()
        print_monthly_projection(
            daily_agent_runs=args.daily_runs,
            llm_calls_per_run=args.llm_calls,
            tool_calls_per_run=args.tool_calls,
            input_tokens_per_run=args.input_tokens,
            output_tokens_per_run=args.output_tokens,
        )


def cmd_spans(args):
    from otel_span_capture import print_telemetry_comparison

    print_telemetry_comparison(
        scenario="S2-budget-exhaustion",
        budget_limit=3, llm_calls=4, tool_calls=3, total_tokens=478,
    )


def cmd_report(args):
    from report_generator import write_full_report
    write_full_report(output_dir=args.output)


def cmd_run(args):
    import asyncio
    sys.path.insert(0, ".")
    from harness import main as harness_main

    if args.all:
        sys.argv = ["harness.py", "--all"]
    elif args.scenario:
        sys.argv = ["harness.py", "--scenario", args.scenario]
    else:
        sys.argv = ["harness.py", "--all"]

    if args.frameworks:
        sys.argv.extend(["--frameworks", args.frameworks])

    asyncio.run(harness_main())


def cmd_dimensions(args):
    from pathlib import Path
    dims = Path(__file__).parent / "DIMENSIONS.md"
    if dims.exists():
        print(dims.read_text())
    else:
        print("DIMENSIONS.md not found. Run from the project root.")


def cmd_mock(args):
    """Start the mock LLM server standalone (for manual testing)."""
    import yaml
    from mock_llm_pkg.server import run, load_script

    if args.script:
        with open(args.script) as f:
            scenario = yaml.safe_load(f)
        load_script(scenario.get("script", []))
        print(f"Loaded: {scenario.get('name', args.script)}")

    run(port=args.port)


def main():
    parser = argparse.ArgumentParser(
        prog="agent-budget-semantics",
        description="Differential testing of budget enforcement across AI agent frameworks",
    )
    sub = parser.add_subparsers(dest="command")

    p_compare = sub.add_parser("compare", help="Show iteration divergence matrix")
    p_compare.add_argument("--scenario", default="S2", help="Scenario (S2 or S4)")
    p_compare.set_defaults(func=cmd_compare)

    p_cost = sub.add_parser("cost", help="Show cost divergence across frameworks")
    p_cost.add_argument("--llm-calls", type=int, default=4)
    p_cost.add_argument("--tool-calls", type=int, default=3)
    p_cost.add_argument("--input-tokens", type=int, default=350)
    p_cost.add_argument("--output-tokens", type=int, default=128)
    p_cost.add_argument("--pricing", default="enterprise-chargeback",
                        choices=["gpt-4o", "gpt-4o-mini", "claude-sonnet-4",
                                 "claude-opus-4", "enterprise-chargeback"])
    p_cost.add_argument("--daily-runs", type=int, default=0,
                        help="If set, project monthly costs")
    p_cost.set_defaults(func=cmd_cost)

    p_spans = sub.add_parser("spans", help="Show OTel telemetry divergence")
    p_spans.set_defaults(func=cmd_spans)

    p_report = sub.add_parser("report", help="Generate full markdown/JSON report suite")
    p_report.add_argument("--output", default="reports", help="Output directory")
    p_report.set_defaults(func=cmd_report)

    p_run = sub.add_parser("run", help="Run differential tests against frameworks")
    p_run.add_argument("--all", action="store_true", help="Run all scenarios")
    p_run.add_argument("--scenario", help="Path to scenario YAML")
    p_run.add_argument("--frameworks", help="Comma-separated framework list")
    p_run.set_defaults(func=cmd_run)

    p_dims = sub.add_parser("dimensions", help="Print dimension taxonomy")
    p_dims.set_defaults(func=cmd_dimensions)

    p_mock = sub.add_parser("mock", help="Start mock LLM server")
    p_mock.add_argument("--port", type=int, default=9111)
    p_mock.add_argument("--script", help="Scenario YAML to load")
    p_mock.set_defaults(func=cmd_mock)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
