from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from itmo_young_congress.crypto import verify_merkle_proof
from itmo_young_congress.demo import run_demo_gateway
from itmo_young_congress.domain import ArrivalSegment, ScenarioConfig
from itmo_young_congress.policies import AdaptiveEpochPolicy, FixedEpochPolicy
from itmo_young_congress.reporting import build_report, run_batch
from itmo_young_congress.simulator import run_simulation, simulation_to_json


def load_scenario(path: Path) -> ScenarioConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = tuple(ArrivalSegment(**segment) for segment in payload["segments"])
    return ScenarioConfig(
        name=payload["name"],
        duration=payload["duration"],
        queue_capacity=payload["queue_capacity"],
        target_window=payload["target_window"],
        segments=segments,
    )


def make_policies(scenario: ScenarioConfig) -> dict:
    nominal = max(2, round(scenario.target_window * scenario.segments[0].rate))
    adaptive = AdaptiveEpochPolicy(
        target_window=scenario.target_window,
        min_epoch=2,
        max_epoch=max(4 * nominal, 8),
        ema_alpha=0.2,
        change_threshold=0.1,
        ack_target=1.0,
    )
    return {
        "fixed-small": FixedEpochPolicy(epoch_size=max(1, nominal // 2), min_epoch=2, max_epoch=4 * nominal),
        "fixed-nominal": FixedEpochPolicy(epoch_size=nominal, min_epoch=2, max_epoch=4 * nominal),
        "fixed-large": FixedEpochPolicy(epoch_size=max(nominal * 4, 2), min_epoch=2, max_epoch=4 * nominal),
        "adaptive": adaptive,
        "adaptive-no-arrival-rate": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_arrival_rate": False}),
        "adaptive-no-ack-latency": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_ack_latency": False}),
        "adaptive-no-cpu-load": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_cpu_load": False}),
        "adaptive-no-queue-fill": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_queue_fill": False}),
        "adaptive-no-early-close": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_early_close": False}),
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _cmd_verify_proof(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    proof = [(bytes.fromhex(item["hash"]), item["left"]) for item in payload["proof"]]
    valid = verify_merkle_proof(
        bytes.fromhex(payload["leaf"]),
        proof,
        bytes.fromhex(payload["root"]),
    )
    return 0 if valid else 1


def _cmd_demo_gateway(args: argparse.Namespace) -> int:
    scenario = load_scenario(Path(args.config))
    result = asyncio.run(run_demo_gateway(scenario, seed=args.seed))
    _write_json(Path(args.output), result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itmo-young-congress")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_scenario = subparsers.add_parser("run-scenario")
    run_scenario.add_argument("--config", required=True)
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
    run_scenario.add_argument("--seed", type=int, default=1)
    run_scenario.add_argument("--output-dir", required=True)
    run_scenario.set_defaults(handler=_cmd_run_scenario)

    run_batch_parser = subparsers.add_parser("run-batch")
    run_batch_parser.add_argument("--config", required=True)
    run_batch_parser.add_argument("--seeds", required=True)
    run_batch_parser.add_argument("--output-dir", required=True)
    run_batch_parser.set_defaults(handler=_cmd_run_batch)

    build_report_parser = subparsers.add_parser("build-report")
    build_report_parser.add_argument("--summary", required=True)
    build_report_parser.add_argument("--output-dir", required=True)
    build_report_parser.set_defaults(handler=_cmd_build_report)

    verify_parser = subparsers.add_parser("verify-proof")
    verify_parser.add_argument("--input", required=True)
    verify_parser.set_defaults(handler=_cmd_verify_proof)

    demo_parser = subparsers.add_parser("demo-gateway")
    demo_parser.add_argument("--config", required=True)
    demo_parser.add_argument("--seed", type=int, default=1)
    demo_parser.add_argument("--output", required=True)
    demo_parser.set_defaults(handler=_cmd_demo_gateway)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
