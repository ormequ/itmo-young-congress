from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cli_common import load_scenario, make_policies, write_json
from demo import run_demo_gateway
from reporting import build_report, run_batch, run_stress_test
from simulator import run_simulation, simulation_to_json


DEFAULT_DEMO_STRESS_WINDOW_LIMIT = 5.0
DEFAULT_DEMO_STRESS_QUEUE_FILL_LIMIT = 0.9


def _cmd_run_scenario(args: argparse.Namespace) -> int:
    scenario = load_scenario(Path(args.config))
    policy = make_policies(scenario)[args.policy]
    result = run_simulation(scenario, policy, seed=args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(simulation_to_json(result), encoding="utf-8")
    return 0


def _cmd_run_batch(args: argparse.Namespace) -> int:
    scenario = load_scenario(Path(args.config))
    seeds = [int(item) for item in args.seeds.split(",") if item]
    run_batch([scenario], make_policies(scenario), seeds=seeds, output_dir=Path(args.output_dir))
    return 0


def _cmd_build_report(args: argparse.Namespace) -> int:
    build_report(Path(args.summary), Path(args.output_dir))
    return 0


def _cmd_stress_test(args: argparse.Namespace) -> int:
    scenario = load_scenario(Path(args.config))
    arrival_rates = [float(item) for item in args.arrival_rates.split(",") if item]
    seeds = [int(item) for item in args.seeds.split(",") if item]
    summary = run_stress_test(
        scenario=scenario,
        arrival_rates=arrival_rates,
        seeds=seeds,
        window_limit=args.window_limit or DEFAULT_DEMO_STRESS_WINDOW_LIMIT,
        queue_fill_limit=args.queue_fill_limit or DEFAULT_DEMO_STRESS_QUEUE_FILL_LIMIT,
    )
    write_json(Path(args.output_dir) / "stress_summary.json", summary)
    return 0


def _cmd_demo_gateway(args: argparse.Namespace) -> int:
    scenario = load_scenario(Path(args.config))
    result = asyncio.run(run_demo_gateway(scenario, seed=args.seed))
    write_json(Path(args.output), result)
    return 0


def register_demo_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    run_scenario = subparsers.add_parser("demo-run-scenario")
    # Path to a JSON scenario definition.
    run_scenario.add_argument("--config", required=True)
    # Which policy to execute for the selected scenario.
    run_scenario.add_argument(
        "--policy",
        required=True,
        choices=[
            "fixed-small",
            "fixed-nominal",
            "fixed-large",
            "adaptive",
            "adaptive-no-arrival-rate",
            "adaptive-no-ack-latency",
            "adaptive-no-cpu-load",
            "adaptive-no-queue-fill",
            "adaptive-no-early-close",
        ],
    )
    # RNG seed for deterministic event generation.
    run_scenario.add_argument("--seed", type=int, default=1)
    # Directory where the single-run JSON result will be written.
    run_scenario.add_argument("--output-dir", required=True)
    run_scenario.set_defaults(handler=_cmd_run_scenario)

    run_batch_parser = subparsers.add_parser("demo-run-batch")
    # Path to a JSON scenario definition reused across all seeds/policies.
    run_batch_parser.add_argument("--config", required=True)
    # Comma-separated list of RNG seeds for repeated runs.
    run_batch_parser.add_argument("--seeds", required=True)
    # Directory where aggregated batch artifacts will be written.
    run_batch_parser.add_argument("--output-dir", required=True)
    run_batch_parser.set_defaults(handler=_cmd_run_batch)

    build_report_parser = subparsers.add_parser("demo-build-report")
    # Path to a batch summary JSON produced by demo-run-batch.
    build_report_parser.add_argument("--summary", required=True)
    # Directory where CSV/Markdown/SVG report files will be written.
    build_report_parser.add_argument("--output-dir", required=True)
    build_report_parser.set_defaults(handler=_cmd_build_report)

    stress_parser = subparsers.add_parser("demo-stress-test")
    # Path to a JSON scenario definition used as the stress baseline.
    stress_parser.add_argument("--config", required=True)
    # Comma-separated arrival-rate levels to probe during the stress sweep.
    stress_parser.add_argument("--arrival-rates", required=True)
    # Comma-separated seeds for repeated runs at every arrival-rate level.
    stress_parser.add_argument("--seeds", required=True)
    # Optional SLA limit for max vulnerability window during safe-throughput search.
    stress_parser.add_argument("--window-limit", type=float)
    # Optional SLA limit for queue occupancy, expressed as a capacity fraction.
    stress_parser.add_argument("--queue-fill-limit", type=float)
    # Directory where the stress summary JSON will be written.
    stress_parser.add_argument("--output-dir", required=True)
    stress_parser.set_defaults(handler=_cmd_stress_test)

    demo_parser = subparsers.add_parser("demo-gateway")
    # Path to a JSON scenario definition for the asyncio demo pipeline.
    demo_parser.add_argument("--config", required=True)
    # RNG seed for deterministic demo event generation.
    demo_parser.add_argument("--seed", type=int, default=1)
    # Output JSON file for the demo execution summary.
    demo_parser.add_argument("--output", required=True)
    demo_parser.set_defaults(handler=_cmd_demo_gateway)
