from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Sequence

from cli_common import make_policies
from domain import ScenarioConfig
from simulator import generate_events, run_simulation, run_simulation_trace


def run_batch(
    scenarios: Sequence[ScenarioConfig],
    policies: Dict[str, object] | None,
    seeds: Sequence[int],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for scenario in scenarios:
        scenario_policies = policies if policies is not None else make_policies(scenario)
        for seed in seeds:
            for policy_name, policy in scenario_policies.items():
                result = run_simulation(scenario, policy, seed=seed)
                rows.append(
                    {
                        "scenario": scenario.name,
                        "seed": seed,
                        "policy": policy_name,
                        "avg_commit_latency": result.metrics.avg_commit_latency,
                        "p95_commit_latency": result.metrics.p95_commit_latency,
                        "max_commit_latency": result.metrics.max_commit_latency,
                        "target_commit_latency": scenario.target_commit_latency,
                        "commit_frequency": result.metrics.commit_frequency,
                        "max_queue_depth": result.metrics.max_queue_depth,
                        "p95_queue_depth": result.metrics.p95_queue_depth,
                        "queue_over_capacity_count": result.metrics.queue_over_capacity_count,
                        "max_epoch_payload_bytes": result.metrics.max_epoch_payload_bytes,
                        "p95_epoch_payload_bytes": result.metrics.p95_epoch_payload_bytes,
                        "max_pending_anchor_count": result.metrics.max_pending_anchor_count,
                        "p95_pending_anchor_count": result.metrics.p95_pending_anchor_count,
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
                "avg_commit_latency": sum(item["avg_commit_latency"] for item in group) / count,
                "p95_commit_latency": sum(item["p95_commit_latency"] for item in group) / count,
                "max_commit_latency": max(item["max_commit_latency"] for item in group),
                "commit_frequency": sum(item["commit_frequency"] for item in group) / count,
                "max_queue_depth": max(item["max_queue_depth"] for item in group),
                "p95_queue_depth": sum(item["p95_queue_depth"] for item in group) / count,
                "queue_over_capacity_count": sum(item["queue_over_capacity_count"] for item in group),
                "max_epoch_payload_bytes": max(item["max_epoch_payload_bytes"] for item in group),
                "p95_epoch_payload_bytes": sum(item["p95_epoch_payload_bytes"] for item in group) / count,
                "max_pending_anchor_count": max(item["max_pending_anchor_count"] for item in group),
                "p95_pending_anchor_count": sum(item["p95_pending_anchor_count"] for item in group) / count,
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
        "| scenario | policy | avg_commit_latency | p95_commit_latency | max_commit_latency | commit_frequency | max_queue_depth | p95_queue_depth | queue_over_capacity_count | max_epoch_payload_bytes | p95_epoch_payload_bytes | max_pending_anchor_count | p95_pending_anchor_count | throughput | avg_proof_bytes | signature_time_per_second |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        md_lines.append(
            "| {scenario} | {policy} | {avg_commit_latency:.3f} | {p95_commit_latency:.3f} | {max_commit_latency:.3f} | "
            "{commit_frequency:.3f} | {max_queue_depth} | {p95_queue_depth:.3f} | {queue_over_capacity_count} | {max_epoch_payload_bytes} | {p95_epoch_payload_bytes:.1f} | {max_pending_anchor_count} | {p95_pending_anchor_count:.1f} | {throughput:.3f} | {avg_proof_bytes:.1f} | "
            "{signature_time_per_second:.3f} |".format(
                **row
            )
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    svg_path = report_dir / "avg_commit_latency.svg"
    max_value = max(row["avg_commit_latency"] for row in summary) or 1.0
    bar_width = 80
    gap = 20
    height = 50 + 40 * len(summary)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="{height}">',
        '<style>text { font: 12px monospace; }</style>',
    ]
    for index, row in enumerate(summary):
        y = 30 + index * 35
        width = 20 + (row["avg_commit_latency"] / max_value) * 400
        label = f'{row["scenario"]}/{row["policy"]}'
        lines.append(f'<text x="10" y="{y + 12}">{label}</text>')
        lines.append(f'<rect x="220" y="{y}" width="{width:.1f}" height="20" fill="#1f77b4" />')
        lines.append(
            f'<text x="{230 + width:.1f}" y="{y + 12}">{row["avg_commit_latency"]:.3f}</text>'
        )
    lines.append("</svg>")
    svg_path.write_text("\n".join(lines), encoding="utf-8")

    return report_dir


def _scenario_with_rate(scenario: ScenarioConfig, rate: float) -> ScenarioConfig:
    segments = tuple(
        type(segment)(
            duration=segment.duration,
            rate=rate,
            anchor_ack_latency=segment.anchor_ack_latency,
            cpu_load=segment.cpu_load,
            input_queue_fill=segment.input_queue_fill,
            critical_every=segment.critical_every,
            source_priority=segment.source_priority,
            payload_size_bytes=segment.payload_size_bytes,
        )
        for segment in scenario.segments
    )
    return ScenarioConfig(
        name=f"{scenario.name}-stress-{rate:g}",
        duration=scenario.duration,
        queue_capacity=scenario.queue_capacity,
        target_commit_latency=scenario.target_commit_latency,
        segments=segments,
        telemetry_window_size=scenario.telemetry_window_size,
        anomaly_score_threshold=scenario.anomaly_score_threshold,
        criticality_threshold=scenario.criticality_threshold,
        epoch_buffer_budget_bytes=scenario.epoch_buffer_budget_bytes,
        max_pending_anchors=scenario.max_pending_anchors,
    )


def _stress_policies(scenario: ScenarioConfig) -> Dict[str, object]:
    policies = make_policies(scenario)
    for policy_name, policy in list(policies.items()):
        if policy_name.startswith("adaptive") and hasattr(policy, "use_early_close"):
            policies[policy_name] = type(policy)(**{**policy.__dict__, "use_early_close": False})
    return policies


def _phase_payload(scenario: ScenarioConfig) -> List[dict]:
    phases: List[dict] = []
    current_time = 0.0
    for index, segment in enumerate(scenario.segments, start=1):
        start = current_time
        end = min(scenario.duration, current_time + segment.duration)
        phases.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "rate": segment.rate,
                "anchor_ack_latency": segment.anchor_ack_latency,
                "input_queue_fill": segment.input_queue_fill,
                "source_priority": segment.source_priority,
                "payload_size_bytes": segment.payload_size_bytes,
            }
        )
        current_time = end
        if current_time >= scenario.duration:
            break
    return phases


def _commit_latency_points(result, events) -> List[dict]:
    event_by_id = {event.event_id: event for event in events}
    points: List[dict] = []
    for commit in result.commits:
        latencies = [commit.commit_time - event_by_id[event_id].arrival_time for event_id in commit.event_ids]
        points.append(
            {
                "time": commit.commit_time,
                "avg_commit_latency": sum(latencies) / len(latencies),
                "max_commit_latency": max(latencies),
                "epoch_event_count": len(commit.event_ids),
                "epoch_payload_bytes": sum(
                    event_by_id[event_id].payload_size_bytes or len(event_by_id[event_id].payload)
                    for event_id in commit.event_ids
                ),
            }
        )
    return points


def run_stress_test(
    scenario: ScenarioConfig,
    arrival_rates: Sequence[float],
    seeds: Sequence[int],
    commit_latency_limit: float,
    input_queue_fill_limit: float,
    commit_frequency_limit: float = float("inf"),
) -> Dict[str, dict]:
    policies = _stress_policies(scenario)
    summary: Dict[str, dict] = {}
    queue_limit = scenario.queue_capacity * input_queue_fill_limit

    for policy_name, policy in policies.items():
        if policy_name.startswith("adaptive-no-"):
            continue
        safe_rate = 0.0
        safe_metrics = {
            "avg_commit_latency": 0.0,
            "p95_commit_latency": 0.0,
            "max_commit_latency": 0.0,
            "commit_frequency_at_safe_throughput": 0.0,
            "max_queue_depth_at_safe_throughput": 0.0,
            "p95_queue_depth_at_safe_throughput": 0.0,
            "queue_over_capacity_count_at_safe_throughput": 0,
            "max_pending_anchor_count_at_safe_throughput": 0,
            "avg_proof_bytes_at_safe_throughput": 0.0,
            "signature_time_per_second_at_safe_throughput": 0.0,
            "passes_constraints": False,
        }

        for rate in sorted(arrival_rates):
            stress_scenario = _scenario_with_rate(scenario, rate)
            results = [run_simulation(stress_scenario, policy, seed=seed) for seed in seeds]
            avg_commit_latency = sum(result.metrics.avg_commit_latency for result in results) / len(results)
            p95_commit_latency = sum(result.metrics.p95_commit_latency for result in results) / len(results)
            max_commit_latency = max(result.metrics.max_commit_latency for result in results)
            commit_frequency = sum(result.metrics.commit_frequency for result in results) / len(results)
            max_queue_depth = max(result.metrics.max_queue_depth for result in results)
            p95_queue_depth = sum(result.metrics.p95_queue_depth for result in results) / len(results)
            queue_over_capacity_count = sum(result.metrics.queue_over_capacity_count for result in results)
            max_pending_anchor_count = max(result.metrics.max_pending_anchor_count for result in results)
            avg_proof_bytes = sum(result.metrics.avg_proof_bytes for result in results) / len(results)
            signature_time_per_second = (
                sum(result.metrics.signature_time_per_second for result in results) / len(results)
            )
            pending_anchor_limit = scenario.max_pending_anchors
            pending_anchor_safe = (
                pending_anchor_limit == float("inf") or max_pending_anchor_count <= pending_anchor_limit
            )
            is_safe = (
                p95_commit_latency <= commit_latency_limit
                and p95_queue_depth <= queue_limit
                and queue_over_capacity_count == 0
                and pending_anchor_safe
                and commit_frequency <= commit_frequency_limit
            )
            if is_safe:
                safe_rate = rate
                safe_metrics = {
                    "avg_commit_latency": avg_commit_latency,
                    "p95_commit_latency": p95_commit_latency,
                    "max_commit_latency": max_commit_latency,
                    "commit_frequency_at_safe_throughput": commit_frequency,
                    "max_queue_depth_at_safe_throughput": max_queue_depth,
                    "p95_queue_depth_at_safe_throughput": p95_queue_depth,
                    "queue_over_capacity_count_at_safe_throughput": queue_over_capacity_count,
                    "max_pending_anchor_count_at_safe_throughput": max_pending_anchor_count,
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


def run_stress_response(
    scenario: ScenarioConfig,
    policies: Sequence[str],
    seed: int,
) -> Dict[str, object]:
    available = _stress_policies(scenario)
    events = generate_events(scenario, seed)
    traces: Dict[str, List[dict]] = {}
    commit_latency_points: Dict[str, List[dict]] = {}
    for policy_name in policies:
        policy = available[policy_name]
        traces[policy_name] = run_simulation_trace(scenario, policy, seed=seed, events=events)
        result = run_simulation(scenario, policy, seed=seed, events=events)
        commit_latency_points[policy_name] = _commit_latency_points(result, events)
    return {
        "scenario": scenario.name,
        "seed": seed,
        "phases": _phase_payload(scenario),
        "policies": traces,
        "commit_latency_points": commit_latency_points,
    }


def run_stress_capacity(
    scenario: ScenarioConfig,
    arrival_rates: Sequence[float],
    seeds: Sequence[int],
    policies: Sequence[str],
    commit_latency_limit: float = 5.0,
    input_queue_fill_limit: float = 0.9,
) -> Dict[str, object]:
    available = _stress_policies(scenario)
    curves: Dict[str, List[dict]] = {}
    policy_summaries: Dict[str, dict] = {}
    queue_limit = scenario.queue_capacity * input_queue_fill_limit

    for policy_name in policies:
        policy = available[policy_name]
        points: List[dict] = []
        safe_throughput = 0.0
        safe_point: dict | None = None
        for rate in arrival_rates:
            stress_scenario = _scenario_with_rate(scenario, rate)
            results = [run_simulation(stress_scenario, policy, seed=seed) for seed in seeds]
            avg_commit_latency = sum(result.metrics.avg_commit_latency for result in results) / len(results)
            p95_commit_latency = sum(result.metrics.p95_commit_latency for result in results) / len(results)
            max_commit_latency = max(result.metrics.max_commit_latency for result in results)
            commit_frequency = sum(result.metrics.commit_frequency for result in results) / len(results)
            max_queue_depth = max(result.metrics.max_queue_depth for result in results)
            p95_queue_depth = sum(result.metrics.p95_queue_depth for result in results) / len(results)
            queue_over_capacity_count = sum(result.metrics.queue_over_capacity_count for result in results)
            max_pending_anchor_count = max(result.metrics.max_pending_anchor_count for result in results)
            pending_anchor_limit = scenario.max_pending_anchors
            pending_anchor_safe = (
                pending_anchor_limit == float("inf") or max_pending_anchor_count <= pending_anchor_limit
            )
            is_safe = (
                p95_commit_latency <= commit_latency_limit
                and p95_queue_depth <= queue_limit
                and queue_over_capacity_count == 0
                and pending_anchor_safe
            )
            point = {
                "arrival_rate": rate,
                "avg_commit_latency": avg_commit_latency,
                "p95_commit_latency": p95_commit_latency,
                "max_commit_latency": max_commit_latency,
                "commit_frequency": commit_frequency,
                "max_queue_depth": max_queue_depth,
                "p95_queue_depth": p95_queue_depth,
                "queue_over_capacity_count": queue_over_capacity_count,
                "max_pending_anchor_count": max_pending_anchor_count,
                "avg_proof_bytes": sum(result.metrics.avg_proof_bytes for result in results) / len(results),
                "signature_time_per_second": sum(
                    result.metrics.signature_time_per_second for result in results
                )
                / len(results),
                "is_safe": is_safe,
            }
            points.append(point)
            if is_safe:
                safe_throughput = rate
                safe_point = point
        curves[policy_name] = points
        policy_summaries[policy_name] = {
            "safe_throughput": safe_throughput,
            "safe_point": safe_point,
        }

    return {
        "scenario": scenario.name,
        "arrival_rates": list(arrival_rates),
        "curves": curves,
        "policies": policy_summaries,
    }
