from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Sequence

from cli_common import make_policies
from domain import ScenarioConfig
from simulator import run_simulation


def run_batch(
    scenarios: Sequence[ScenarioConfig],
    policies: Dict[str, object],
    seeds: Sequence[int],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for scenario in scenarios:
        for seed in seeds:
            for policy_name, policy in policies.items():
                result = run_simulation(scenario, policy, seed=seed)
                rows.append(
                    {
                        "scenario": scenario.name,
                        "seed": seed,
                        "policy": policy_name,
                        "avg_vulnerability_window": result.metrics.avg_vulnerability_window,
                        "max_vulnerability_window": result.metrics.max_vulnerability_window,
                        "commit_frequency": result.metrics.commit_frequency,
                        "max_queue_depth": result.metrics.max_queue_depth,
                        "throughput": result.metrics.throughput,
                        "avg_proof_bytes": result.metrics.avg_proof_bytes,
                        "signature_time_per_second": result.metrics.signature_time_per_second,
                    }
                )

    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return summary_path


def _aggregate(rows: Sequence[dict]) -> List[dict]:
    grouped: Dict[tuple, List[dict]] = {}
    for row in rows:
        grouped.setdefault((row["scenario"], row["policy"]), []).append(row)

    summary = []
    for (scenario, policy), group in grouped.items():
        count = len(group)
        summary.append(
            {
                "scenario": scenario,
                "policy": policy,
                "avg_vulnerability_window": sum(item["avg_vulnerability_window"] for item in group) / count,
                "max_vulnerability_window": max(item["max_vulnerability_window"] for item in group),
                "commit_frequency": sum(item["commit_frequency"] for item in group) / count,
                "max_queue_depth": max(item["max_queue_depth"] for item in group),
                "throughput": sum(item["throughput"] for item in group) / count,
                "avg_proof_bytes": sum(item["avg_proof_bytes"] for item in group) / count,
                "signature_time_per_second": sum(item["signature_time_per_second"] for item in group) / count,
            }
        )
    summary.sort(key=lambda item: (item["scenario"], item["policy"]))
    return summary


def build_report(summary_path: Path, report_dir: Path) -> Path:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    summary = _aggregate(rows)
    report_dir.mkdir(parents=True, exist_ok=True)

    csv_path = report_dir / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    md_path = report_dir / "summary.md"
    md_lines = [
        "| scenario | policy | avg_window | max_window | commit_frequency | max_queue_depth | throughput | avg_proof_bytes | signature_time_per_second |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        md_lines.append(
            "| {scenario} | {policy} | {avg_vulnerability_window:.3f} | {max_vulnerability_window:.3f} | "
            "{commit_frequency:.3f} | {max_queue_depth} | {throughput:.3f} | {avg_proof_bytes:.1f} | "
            "{signature_time_per_second:.3f} |".format(
                **row
            )
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    svg_path = report_dir / "avg_window.svg"
    max_value = max(row["avg_vulnerability_window"] for row in summary) or 1.0
    bar_width = 80
    gap = 20
    height = 50 + 40 * len(summary)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="{height}">',
        '<style>text { font: 12px monospace; }</style>',
    ]
    for index, row in enumerate(summary):
        y = 30 + index * 35
        width = 20 + (row["avg_vulnerability_window"] / max_value) * 400
        label = f'{row["scenario"]}/{row["policy"]}'
        lines.append(f'<text x="10" y="{y + 12}">{label}</text>')
        lines.append(f'<rect x="220" y="{y}" width="{width:.1f}" height="20" fill="#1f77b4" />')
        lines.append(
            f'<text x="{230 + width:.1f}" y="{y + 12}">{row["avg_vulnerability_window"]:.3f}</text>'
        )
    lines.append("</svg>")
    svg_path.write_text("\n".join(lines), encoding="utf-8")

    return report_dir


def _scenario_with_rate(scenario: ScenarioConfig, rate: float) -> ScenarioConfig:
    segments = tuple(
        type(segment)(
            duration=segment.duration,
            rate=rate,
            ack_latency=segment.ack_latency,
            cpu_load=segment.cpu_load,
            queue_fill=segment.queue_fill,
            critical_every=segment.critical_every,
        )
        for segment in scenario.segments
    )
    return ScenarioConfig(
        name=f"{scenario.name}-stress-{rate:g}",
        duration=scenario.duration,
        queue_capacity=scenario.queue_capacity,
        target_window=scenario.target_window,
        segments=segments,
        telemetry_window_size=scenario.telemetry_window_size,
        anomaly_sigma_threshold=scenario.anomaly_sigma_threshold,
        criticality_threshold=scenario.criticality_threshold,
    )


def run_stress_test(
    scenario: ScenarioConfig,
    arrival_rates: Sequence[float],
    seeds: Sequence[int],
    window_limit: float,
    queue_fill_limit: float,
    commit_frequency_limit: float = float("inf"),
) -> Dict[str, dict]:
    policies = make_policies(scenario)
    summary: Dict[str, dict] = {}
    queue_limit = scenario.queue_capacity * queue_fill_limit

    for policy_name, policy in policies.items():
        if policy_name.startswith("adaptive-no-"):
            continue
        safe_rate = 0.0
        safe_metrics = {
            "avg_vulnerability_window": 0.0,
            "max_vulnerability_window": 0.0,
            "commit_frequency_at_safe_throughput": 0.0,
            "max_queue_depth_at_safe_throughput": 0.0,
            "avg_proof_bytes_at_safe_throughput": 0.0,
            "signature_time_per_second_at_safe_throughput": 0.0,
            "passes_constraints": False,
        }

        for rate in sorted(arrival_rates):
            stress_scenario = _scenario_with_rate(scenario, rate)
            results = [run_simulation(stress_scenario, policy, seed=seed) for seed in seeds]
            avg_window = sum(result.metrics.avg_vulnerability_window for result in results) / len(results)
            max_window = max(result.metrics.max_vulnerability_window for result in results)
            commit_frequency = sum(result.metrics.commit_frequency for result in results) / len(results)
            max_queue_depth = max(result.metrics.max_queue_depth for result in results)
            avg_proof_bytes = sum(result.metrics.avg_proof_bytes for result in results) / len(results)
            signature_time_per_second = (
                sum(result.metrics.signature_time_per_second for result in results) / len(results)
            )
            is_safe = (
                max_window <= window_limit
                and max_queue_depth <= queue_limit
                and commit_frequency <= commit_frequency_limit
            )
            if is_safe:
                safe_rate = rate
                safe_metrics = {
                    "avg_vulnerability_window": avg_window,
                    "max_vulnerability_window": max_window,
                    "commit_frequency_at_safe_throughput": commit_frequency,
                    "max_queue_depth_at_safe_throughput": max_queue_depth,
                    "avg_proof_bytes_at_safe_throughput": avg_proof_bytes,
                    "signature_time_per_second_at_safe_throughput": signature_time_per_second,
                    "passes_constraints": True,
                }
            else:
                break

        summary[policy_name] = {
            "safe_throughput": safe_rate,
            **safe_metrics,
        }

    return summary
