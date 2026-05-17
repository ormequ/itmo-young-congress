from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile

_cache_dir = Path(tempfile.gettempdir()) / "matplotlib-cache"
_cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_cache_dir))
os.environ.setdefault("XDG_CACHE_HOME", str(_cache_dir))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


FIGURE_DPI = 300
POLICY_ORDER = ["adaptive", "fixed-small", "fixed-nominal", "fixed-large"]
POLICY_COLORS = {
    "adaptive": "#1f77b4",
    "fixed-small": "#ff7f0e",
    "fixed-nominal": "#2ca02c",
    "fixed-large": "#d62728",
}
POLICY_LABELS = {
    "adaptive": "Adaptive",
    "fixed-small": "Fixed-small",
    "fixed-nominal": "Fixed-nominal",
    "fixed-large": "Fixed-large",
}
ABLATION_POLICY_ORDER = ["adaptive", "adaptive-no-pending-anchors", "fixed-small", "fixed-nominal"]
ABLATION_POLICY_LABELS = {
    "adaptive": "Adaptive full",
    "adaptive-no-pending-anchors": "Adaptive w/o anchor BP",
    "fixed-small": "Fixed-small",
    "fixed-nominal": "Fixed-nominal",
}
PRESENTATION_SCENARIOS = ["critical-event-injection", "storage-degradation", "queue-saturation"]
COMMIT_LATENCY_OVERVIEW_SCENARIOS = [
    "anchor-backpressure",
    "burst",
    "memory-pressure",
    "queue-saturation",
    "combined-stress",
    "steady",
]
COMMIT_LATENCY_OVERVIEW_PANELS = [
    ("p95_commit_latency", "P95 commit latency, s"),
    ("max_commit_latency", "Max commit latency, s"),
]
COST_OVERVIEW_SCENARIOS = ["burst", "anchor-backpressure", "memory-pressure", "queue-saturation", "combined-stress"]
COST_OVERVIEW_PANELS = [
    ("commit_frequency", "Commit frequency, 1/s"),
    ("queue_over_capacity_count", "Queue over-capacity count"),
]
COMBINED_STRESS_TABLE_COLUMNS = [
    ("p95_commit_latency", "P95 latency, s", 1.0),
    ("commit_frequency", "Commit freq., 1/s", 1.0),
    ("p95_epoch_payload_bytes", "P95 payload, KiB", 1 / 1024),
    ("p95_queue_depth", "P95 queue depth", 1.0),
    ("queue_over_capacity_count", "Queue over-capacity", 1.0),
]
CLOSE_REASON_ORDER = [
    "target_reached",
    "max_epoch_duration",
    "max_epoch_events",
    "memory_pressure",
    "input_queue_pressure",
    "anchor_backpressure",
    "critical_event",
    "anomaly_score",
]


def _apply_presentation_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 14,
            "xtick.labelsize": 11,
            "ytick.labelsize": 12,
            "legend.fontsize": 11,
        }
    )


def _short_scenario_name(name: str) -> str:
    mapping = {
        "anomaly-recovery": "Anomaly recovery",
        "anomaly-spike": "Anomaly spike",
        "combined-stress": "Combined stress",
        "critical-event-injection": "Critical events",
        "critical-event": "Critical events",
        "storage-degradation": "Storage degradation",
        "memory-pressure": "Memory pressure",
        "anchor-backpressure": "Anchor backpressure",
        "queue-saturation": "Queue saturation",
        "cpu-pressure": "CPU pressure",
        "burst": "Burst traffic",
        "steady": "Steady state",
    }
    return mapping.get(name, name)


def _aggregate_batch_rows(rows: list[dict]) -> list[dict]:
    rows = [row for row in rows if row["policy"] in POLICY_ORDER]
    grouped: dict[tuple[str, str], list[dict]] = {}
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
                "p95_commit_latency": sum(item.get("p95_commit_latency", 0.0) for item in group) / count,
                "max_commit_latency": max(item["max_commit_latency"] for item in group),
                "commit_frequency": sum(item["commit_frequency"] for item in group) / count,
                "max_queue_depth": max(item["max_queue_depth"] for item in group),
                "p95_queue_depth": sum(item.get("p95_queue_depth", 0.0) for item in group) / count,
                "queue_over_capacity_count": sum(item.get("queue_over_capacity_count", 0) for item in group),
                "max_epoch_payload_bytes": max(item.get("max_epoch_payload_bytes", 0) for item in group),
                "p95_epoch_payload_bytes": sum(item.get("p95_epoch_payload_bytes", 0.0) for item in group) / count,
                "max_pending_anchor_count": max(item.get("max_pending_anchor_count", 0) for item in group),
                "p95_pending_anchor_count": sum(item.get("p95_pending_anchor_count", 0.0) for item in group)
                / count,
                "avg_proof_bytes": sum(item["avg_proof_bytes"] for item in group) / count,
                "signature_time_per_second": sum(item.get("signature_time_per_second", 0.0) for item in group)
                / count,
                "target_commit_latency": (
                    sum(item.get("target_commit_latency", 0.0) for item in group) / count
                    if any("target_commit_latency" in item for item in group)
                    else None
                ),
            }
        )
    summary.sort(key=lambda item: (item["scenario"], POLICY_ORDER.index(item["policy"])))
    return summary


def _aggregate_rows_for_policies(rows: list[dict], policy_order: list[str]) -> list[dict]:
    rows = [row for row in rows if row["policy"] in policy_order]
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["scenario"], row["policy"]), []).append(row)

    summary = []
    for (scenario, policy), group in grouped.items():
        count = len(group)
        summary.append(
            {
                "scenario": scenario,
                "policy": policy,
                "p95_pending_anchor_count": sum(item.get("p95_pending_anchor_count", 0.0) for item in group)
                / count,
                "commit_frequency": sum(item["commit_frequency"] for item in group) / count,
                "p95_commit_latency": sum(item.get("p95_commit_latency", 0.0) for item in group) / count,
            }
        )
    summary.sort(key=lambda item: (item["scenario"], policy_order.index(item["policy"])))
    return summary


def _annotate_bars(ax: plt.Axes, bars, values: list[float], *, decimals: int = 2, skip_zero: bool = False) -> None:
    max_height = max(values) if values else 0.0
    offset = 0.03 if max_height <= 1.0 else max_height * 0.03
    for bar, value in zip(bars, values):
        if skip_zero and value == 0.0:
            continue
        text_y = value + offset if value > 0 else offset
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            text_y,
            f"{value:.{decimals}f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )


def _scenario_subset(rows: list[dict], scenarios: list[str]) -> list[dict]:
    available = {row["scenario"] for row in rows}
    selected = [scenario for scenario in scenarios if scenario in available]
    return [row for row in rows if row["scenario"] in selected] if selected else rows


def _build_legend_handles() -> list[Line2D]:
    return [Line2D([0], [0], color=POLICY_COLORS[policy], lw=8, label=POLICY_LABELS[policy]) for policy in POLICY_ORDER]


def _metric_values(rows: list[dict], scenarios: list[str], policy: str, metric_key: str) -> list[float]:
    if metric_key.endswith("_kib"):
        source_key = f"{metric_key[:-4]}_bytes"
        values = {(row["scenario"], row["policy"]): row.get(source_key, 0.0) / 1024 for row in rows}
        return [values.get((scenario, policy), 0.0) for scenario in scenarios]
    values = {(row["scenario"], row["policy"]): row.get(metric_key, 0.0) for row in rows}
    return [values.get((scenario, policy), 0.0) for scenario in scenarios]


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0
    return statistics.mean(values), statistics.stdev(values)


def _format_mean_std(values: list[float], scale: float = 1.0) -> str:
    scaled = [value * scale for value in values]
    mean, std = _mean_std(scaled)
    return f"{mean:.2f} +/- {std:.2f}"


def _warn_missing_metrics(rows: list[dict], metric_keys: list[str], context: str) -> None:
    missing = sorted({metric_key for row in rows for metric_key in metric_keys if metric_key not in row})
    if missing:
        print(f"warning: missing metrics in {context}: {', '.join(missing)}", file=sys.stderr)


def _step_series(points: list[dict], metric_key: str) -> tuple[list[float], list[float]]:
    return [point["time"] for point in points], [point[metric_key] for point in points]


def _fixed_nominal_target(points: list[dict], fallback: float = 0.0) -> float:
    targets = [point.get("next_target", 0) for point in points if point.get("next_target", 0) > 0]
    if not targets:
        return fallback
    return sorted(targets)[len(targets) // 2]


def _commit_frequency_series(points: list[dict], window_seconds: float = 2.0) -> list[float]:
    close_times = [point["time"] for point in points if point.get("should_close")]
    values = []
    for point in points:
        start = point["time"] - window_seconds
        count = sum(1 for close_time in close_times if start < close_time <= point["time"])
        values.append(count / window_seconds)
    return values


def _phase_label(phase: dict) -> str:
    if phase["input_queue_fill"] >= 0.9 or phase["anchor_ack_latency"] >= 2.5:
        return "Critical"
    if phase["rate"] >= 14:
        return "Peak"
    if phase["rate"] <= 6 and phase["anchor_ack_latency"] <= 1.1:
        return "Recovery"
    return "Transition"


def _target_commit_latency(rows: list[dict], scenarios: list[str]) -> float | None:
    values = {
        row.get("target_commit_latency")
        for row in rows
        if row["scenario"] in scenarios and row.get("target_commit_latency") not in (None, 0.0)
    }
    return next(iter(values)) if len(values) == 1 else None


def _add_target_latency_line(ax: plt.Axes, target: float | None) -> None:
    if target is None:
        return
    ax.axhline(target, color="#555555", linestyle="--", linewidth=1.2, label="Target commit latency")


def _shade_phases(axes: list[plt.Axes], phases: list[dict]) -> None:
    if not phases:
        return
    colors = ["#f8fbff", "#f5f7fa"]
    for index, phase in enumerate(phases):
        color = colors[index % len(colors)]
        for ax in axes:
            ax.axvspan(phase["start"], phase["end"], color=color, alpha=0.35, zorder=0)
        center = (phase["start"] + phase["end"]) / 2
        axes[0].text(
            center,
            0.96,
            _phase_label(phase),
            transform=axes[0].get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            color="#55606f",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1.2},
        )


def _plot_grouped_bars(
    rows: list[dict],
    metric_key: str,
    title: str,
    ylabel: str,
    output_path: Path,
) -> None:
    _apply_presentation_style()
    scenarios = sorted({row["scenario"] for row in rows})
    policies = [policy for policy in POLICY_ORDER if any(row["policy"] == policy for row in rows)]
    target_commit_latency = _target_commit_latency(rows, scenarios) if metric_key.endswith("commit_latency") else None

    fig, ax = plt.subplots(figsize=(11, 5.8))
    width = 0.18 if len(policies) > 1 else 0.5
    x_positions = list(range(len(scenarios)))

    for index, policy in enumerate(policies):
        offsets = [x + (index - (len(policies) - 1) / 2) * width for x in x_positions]
        heights = _metric_values(rows, scenarios, policy, metric_key)
        bars = ax.bar(
            offsets,
            heights,
            width=width,
            label=POLICY_LABELS.get(policy, policy),
            color=POLICY_COLORS.get(policy),
            edgecolor="white",
            linewidth=0.8,
        )
        for bar, height in zip(bars, heights):
            text_y = height + max(max(heights) * 0.02, 0.02) if height > 0 else 0.02
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                text_y,
                f"{height:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
                rotation=90 if len(scenarios) > 4 else 0,
            )

    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios], rotation=15, ha="right")
    _add_target_latency_line(ax, target_commit_latency)
    ax.legend(loc="upper center", ncol=len(policies), frameon=False, bbox_to_anchor=(0.5, 1.12))
    ax.grid(axis="y", alpha=0.2, linestyle="--")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def _plot_grouped_bar_panels(
    rows: list[dict],
    panels: list[tuple[str, str]],
    output_path: Path,
    *,
    scenarios: list[str] | None = None,
    ncols: int = 3,
) -> None:
    _apply_presentation_style()
    if scenarios is None:
        scenarios = sorted({row["scenario"] for row in rows})
    else:
        available = {row["scenario"] for row in rows}
        scenarios = [scenario for scenario in scenarios if scenario in available]
    if not scenarios:
        scenarios = sorted({row["scenario"] for row in rows})
    policies = [policy for policy in POLICY_ORDER if any(row["policy"] == policy for row in rows)]
    ncols = max(1, min(ncols, len(panels)))
    nrows = (len(panels) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 4.0 * nrows), squeeze=False, sharex=True)
    width = 0.18 if len(policies) > 1 else 0.5
    x_positions = list(range(len(scenarios)))
    target_commit_latency = _target_commit_latency(rows, scenarios)

    for panel_index, (metric_key, ylabel) in enumerate(panels):
        ax = axes[panel_index // ncols][panel_index % ncols]
        for policy_index, policy in enumerate(policies):
            offsets = [x + (policy_index - (len(policies) - 1) / 2) * width for x in x_positions]
            heights = _metric_values(rows, scenarios, policy, metric_key)
            ax.bar(
                offsets,
                heights,
                width=width,
                color=POLICY_COLORS.get(policy),
                edgecolor="white",
                linewidth=0.8,
            )
        ax.set_ylabel(ylabel)
        if metric_key.endswith("commit_latency"):
            _add_target_latency_line(ax, target_commit_latency)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios], rotation=18, ha="right")
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)

    for empty_index in range(len(panels), nrows * ncols):
        axes[empty_index // ncols][empty_index % ncols].axis("off")

    handles = _build_legend_handles()
    if any(metric_key.endswith("commit_latency") for metric_key, _ in panels) and target_commit_latency is not None:
        handles.append(Line2D([0], [0], color="#555555", lw=1.2, linestyle="--", label="Target commit latency"))
    fig.legend(handles=handles, loc="upper center", ncol=min(len(handles), 5), frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def _plot_ablation_panels(rows: list[dict], output_path: Path) -> None:
    scenario_rows = [row for row in rows if row["scenario"] == "anchor-backpressure"]
    if not scenario_rows:
        return
    summary = _aggregate_rows_for_policies(scenario_rows, ABLATION_POLICY_ORDER)
    if not summary:
        return
    _apply_presentation_style()
    panels = [
        ("p95_pending_anchor_count", "P95 pending anchors"),
        ("commit_frequency", "Commit frequency, 1/s"),
        ("p95_commit_latency", "P95 commit latency, s"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.5))
    policies = [policy for policy in ABLATION_POLICY_ORDER if any(row["policy"] == policy for row in summary)]
    x_positions = list(range(len(policies)))

    for ax, (metric_key, ylabel) in zip(axes, panels):
        heights = [
            next((row[metric_key] for row in summary if row["policy"] == policy), 0.0)
            for policy in policies
        ]
        ax.bar(
            x_positions,
            heights,
            color=[POLICY_COLORS.get(policy, "#7f7f7f") for policy in policies],
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_ylabel(ylabel)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([ABLATION_POLICY_LABELS[policy] for policy in policies], rotation=18, ha="right")
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_combined_stress_table(summary_path: Path, output_dir: Path) -> None:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_rows = [
        row
        for row in rows
        if row.get("scenario") == "combined-stress" and row.get("policy") in POLICY_ORDER
    ]
    grouped: dict[str, list[dict]] = {policy: [] for policy in POLICY_ORDER}
    for row in scenario_rows:
        grouped[row["policy"]].append(row)

    metric_keys = [metric_key for metric_key, _, _ in COMBINED_STRESS_TABLE_COLUMNS]
    _warn_missing_metrics(scenario_rows, metric_keys, "combined-stress table")

    headers = ["Policy"] + [label for _, label, _ in COMBINED_STRESS_TABLE_COLUMNS]
    table_rows: list[list[str]] = []
    for policy in POLICY_ORDER:
        policy_rows = grouped[policy]
        if not policy_rows:
            continue
        table_row = [POLICY_LABELS[policy]]
        for metric_key, _, scale in COMBINED_STRESS_TABLE_COLUMNS:
            values = [float(row.get(metric_key, 0.0)) for row in policy_rows]
            table_row.append(_format_mean_std(values, scale))
        table_rows.append(table_row)

    seed_count = len({row.get("seed") for row in scenario_rows if row.get("seed") is not None})
    seed_label = f"{seed_count} seeds" if seed_count else "available seeds"
    md_lines = [
        f"Combined stress results, mean +/- std over {seed_label}.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] + ["---:"] * (len(headers) - 1)) + " |",
    ]
    for row in table_rows:
        md_lines.append("| " + " | ".join(row) + " |")
    (output_dir / "combined_stress_table.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    with (output_dir / "combined_stress_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(table_rows)


def build_close_reason_counts(trace_path: Path, output_dir: Path) -> None:
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    if payload.get("scenario") != "combined-stress":
        return

    if "points" in payload:
        points = payload["points"]
    else:
        points = payload.get("policies", {}).get("adaptive", [])

    counts = {reason: 0 for reason in CLOSE_REASON_ORDER}
    for point in points:
        if not point.get("should_close"):
            continue
        reasons = point.get("close_reasons") or (["target_reached"] if point.get("should_close") else [])
        for reason in reasons:
            counts.setdefault(reason, 0)
            counts[reason] += 1

    ordered_items = [(reason, counts.get(reason, 0)) for reason in CLOSE_REASON_ORDER]
    extra_items = sorted((reason, count) for reason, count in counts.items() if reason not in CLOSE_REASON_ORDER)
    rows = ordered_items + extra_items

    md_lines = [
        "Adaptive close reason counts for Combined stress.",
        "",
        "| Close reason | Count |",
        "| --- | ---: |",
    ]
    for reason, count in rows:
        md_lines.append(f"| {reason} | {count} |")
    (output_dir / "close_reason_counts_combined_stress.md").write_text(
        "\n".join(md_lines) + "\n",
        encoding="utf-8",
    )

    with (output_dir / "close_reason_counts_combined_stress.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Close reason", "Count"])
        writer.writerows(rows)


def _plot_tradeoff(rows: list[dict], output_path: Path) -> None:
    _apply_presentation_style()
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for policy in POLICY_ORDER:
        policy_rows = [row for row in rows if row["policy"] == policy]
        if not policy_rows:
            continue
        x = [row["commit_frequency"] for row in policy_rows]
        y = [row["avg_commit_latency"] for row in policy_rows]
        ax.scatter(x, y, label=POLICY_LABELS.get(policy, policy), s=90, color=POLICY_COLORS.get(policy))
        for row in policy_rows:
            ax.annotate(
                _short_scenario_name(row["scenario"]),
                (row["commit_frequency"], row["avg_commit_latency"]),
                fontsize=9,
                xytext=(5, 5),
                textcoords="offset points",
            )

    ax.set_xlabel("Commit frequency, 1/s")
    ax.set_ylabel("Average commit latency, s")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_batch_plots(summary_path: Path, output_dir: Path) -> None:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    summary = _aggregate_batch_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    _plot_grouped_bars(
        summary,
        "avg_commit_latency",
        "Average commit latency",
        "Seconds",
        output_dir / "avg_commit_latency.png",
    )
    _plot_grouped_bars(
        summary,
        "max_commit_latency",
        "Max commit latency",
        "Seconds",
        output_dir / "max_commit_latency.png",
    )
    _plot_grouped_bars(
        summary,
        "commit_frequency",
        "Commit frequency",
        "Commits per second",
        output_dir / "commit_frequency.png",
    )
    _plot_grouped_bars(
        summary,
        "p95_queue_depth",
        "P95 queue depth",
        "Events",
        output_dir / "p95_queue_depth.png",
    )
    _plot_grouped_bars(
        summary,
        "avg_proof_bytes",
        "Average proof size",
        "Bytes",
        output_dir / "avg_proof_bytes.png",
    )
    _plot_tradeoff(summary, output_dir / "tradeoff.png")
    _plot_grouped_bar_panels(
        summary,
        COMMIT_LATENCY_OVERVIEW_PANELS,
        output_dir / "commit_latency_overview.png",
        scenarios=COMMIT_LATENCY_OVERVIEW_SCENARIOS,
        ncols=2,
    )
    _plot_grouped_bar_panels(
        summary,
        [
            ("avg_commit_latency", "Average commit latency, s"),
            ("p95_commit_latency", "P95 commit latency, s"),
            ("max_commit_latency", "Max commit latency, s"),
        ],
        output_dir / "commit_latency_full.png",
    )
    _plot_grouped_bar_panels(
        summary,
        COST_OVERVIEW_PANELS,
        output_dir / "cost_and_stability_overview.png",
        scenarios=COST_OVERVIEW_SCENARIOS,
        ncols=2,
    )
    _plot_grouped_bar_panels(
        summary,
        [
            ("commit_frequency", "Commit frequency, 1/s"),
            ("signature_time_per_second", "Signature time per second, s/s"),
            ("p95_queue_depth", "P95 queue depth"),
            ("max_queue_depth", "Max queue depth"),
            ("queue_over_capacity_count", "Queue over-capacity count"),
        ],
        output_dir / "cost_and_stability_full.png",
    )
    _plot_grouped_bar_panels(
        summary,
        [
            ("max_epoch_payload_kib", "Max epoch payload, KiB"),
            ("p95_epoch_payload_kib", "P95 epoch payload, KiB"),
        ],
        output_dir / "memory_pressure_overview.png",
        scenarios=["burst", "memory-pressure", "combined-stress"],
        ncols=2,
    )
    _plot_grouped_bar_panels(
        summary,
        [
            ("p95_pending_anchor_count", "P95 pending anchors"),
            ("p95_commit_latency", "P95 commit latency, s"),
        ],
        output_dir / "anchor_backpressure_overview.png",
        scenarios=["storage-degradation", "anchor-backpressure", "combined-stress"],
        ncols=2,
    )
    _plot_grouped_bar_panels(
        summary,
        [
            ("max_pending_anchor_count", "Max pending anchors"),
            ("p95_pending_anchor_count", "P95 pending anchors"),
            ("commit_frequency", "Commit frequency, 1/s"),
            ("p95_commit_latency", "P95 commit latency, s"),
        ],
        output_dir / "anchor_backpressure_full.png",
        scenarios=["storage-degradation", "anchor-backpressure", "combined-stress"],
        ncols=2,
    )
    _plot_ablation_panels(rows, output_dir / "anchor_backpressure_ablation.png")
    build_combined_stress_table(summary_path, output_dir)


def build_stress_plots(summary_path: Path, output_dir: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    if "curves" in summary:
        build_stress_capacity_plot(summary_path, output_dir / "stress_capacity.png")
        build_stress_summary_table(summary_path, output_dir / "stress_summary_table.png")
        return
    policies = [policy for policy in POLICY_ORDER if policy in summary]

    def plot_metric(metric_key: str, title: str, ylabel: str, filename: str) -> None:
        _apply_presentation_style()
        fig, ax = plt.subplots(figsize=(9, 5.5))
        heights = [summary[policy][metric_key] for policy in policies]
        colors = [POLICY_COLORS.get(policy) for policy in policies]
        labels = [POLICY_LABELS.get(policy, policy) for policy in policies]
        bars = ax.bar(labels, heights, color=colors, edgecolor="white", linewidth=0.8)
        max_height = max(heights) if heights else 0.0
        for bar, height in zip(bars, heights):
            text_y = height + max(max_height * 0.03, 0.03) if height > 0 else 0.03
            ax.text(bar.get_x() + bar.get_width() / 2, text_y, f"{height:.2f}", ha="center", va="bottom", fontsize=10)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
        fig.tight_layout()
        fig.savefig(output_dir / filename, dpi=FIGURE_DPI, bbox_inches="tight")
        plt.close(fig)

    plot_metric("safe_throughput", "Safe throughput", "Events per second", "safe_throughput.png")
    plot_metric(
        "commit_frequency_at_safe_throughput",
        "Commit frequency at safe throughput",
        "Commits per second",
        "stress_commit_frequency.png",
    )
    plot_metric(
        "max_commit_latency",
        "Max commit latency at safe throughput",
        "Seconds",
        "stress_max_commit_latency.png",
    )
    plot_metric(
        "avg_proof_bytes_at_safe_throughput",
        "Average proof size at safe throughput",
        "Bytes",
        "stress_avg_proof_bytes.png",
    )


def build_timeline_plots(trace_path: Path, output_dir: Path) -> None:
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    comparison_points: list[dict] = []
    comparison_policy = ""
    scenario_name = payload.get("scenario", "")
    if "points" in payload:
        points = payload["points"]
    else:
        traces = payload["policies"]
        points = traces.get("adaptive") or next(iter(traces.values()))
        for policy in ["fixed-nominal", "fixed-small", "fixed-large"]:
            if policy in traces:
                comparison_policy = policy
                comparison_points = traces[policy]
                break
    output_dir.mkdir(parents=True, exist_ok=True)
    _apply_presentation_style()

    times = [point["time"] for point in points]
    next_targets = [point["next_target"] for point in points]
    arrival_rates = [point["arrival_rate"] for point in points]
    input_queue_fill = [point["input_queue_fill"] for point in points]
    memory_pressure = [point.get("memory_pressure", 0.0) for point in points]
    pending_anchor_count = [point.get("pending_anchor_count", 0) for point in points]
    max_pending_anchors = [point.get("max_pending_anchors", 0) for point in points]
    anchor_ack_latency = [point["anchor_ack_latency"] for point in points]
    close_times = [point["time"] for point in points if point["should_close"]]
    close_targets = [point["next_target"] for point in points if point["should_close"]]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.step(times, next_targets, where="post", color=POLICY_COLORS["adaptive"], linewidth=2.5, label="Target epoch size")
    if close_times:
        ax.scatter(close_times, close_targets, color="#d62728", s=70, zorder=3, label="Epoch close")
    ax.set_xlabel("Time, s")
    ax.set_ylabel("Target epoch size, events")
    ax.grid(alpha=0.2, linestyle="--")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "target_timeline.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    axes[0].step(times, arrival_rates, where="post", color="#2ca02c", linewidth=2.0)
    axes[0].set_ylabel("Input rate, events/s")
    axes[0].grid(alpha=0.2, linestyle="--")

    axes[1].step(times, input_queue_fill, where="post", color="#ff7f0e", linewidth=2.0)
    axes[1].set_ylabel("Input queue fill")
    axes[1].grid(alpha=0.2, linestyle="--")

    axes[2].step(times, anchor_ack_latency, where="post", color="#9467bd", linewidth=2.0)
    axes[2].set_ylabel("Anchor ack latency, s")
    axes[2].set_xlabel("Time, s")
    axes[2].grid(alpha=0.2, linestyle="--")

    fig.tight_layout()
    fig.savefig(output_dir / "telemetry_timeline.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(13, 10.5), sharex=True)
    axes[0].step(times, arrival_rates, where="post", color="#2ca02c", linewidth=2.3, label="Input rate")
    ack_axis = axes[0].twinx()
    ack_axis.step(times, anchor_ack_latency, where="post", color="#9467bd", linewidth=2.0, label="Anchor ack")
    axes[0].set_ylabel("evt/s")
    ack_axis.set_ylabel("Anchor ack latency, s")
    axes[0].legend(
        handles=[
            Line2D([0], [0], color="#2ca02c", lw=2.3, label="Input rate"),
            Line2D([0], [0], color="#9467bd", lw=2.0, label="Anchor ack latency"),
        ],
        frameon=False,
        loc="upper left",
    )

    axes[1].step(
        times,
        next_targets,
        where="post",
        color=POLICY_COLORS["adaptive"],
        linewidth=2.5,
        label="Adaptive target",
    )
    if comparison_points:
        axes[1].step(
            [point["time"] for point in comparison_points],
            [point["next_target"] for point in comparison_points],
            where="post",
            color=POLICY_COLORS.get(comparison_policy, "#666666"),
            linewidth=2.0,
            label=POLICY_LABELS.get(comparison_policy, comparison_policy),
        )
    if close_times:
        axes[1].scatter(close_times, close_targets, color="#d62728", s=52, zorder=3, label="Epoch close")
    axes[1].legend(frameon=False, loc="upper left")
    axes[1].set_ylabel("Target epoch size, events")

    axes[2].step(times, input_queue_fill, where="post", color="#ff7f0e", linewidth=2.2, label="Input queue fill")
    axes[2].step(times, memory_pressure, where="post", color="#8c564b", linewidth=2.2, label="Memory pressure")
    axes[2].axhline(0.9, color="#555555", linestyle="--", linewidth=1.2, label="Queue close threshold")
    axes[2].axhline(1.0, color="#d62728", linestyle="--", linewidth=1.2, label="Memory hard-close threshold")
    axes[2].set_ylabel("Constraints")
    axes[2].legend(frameon=False, ncol=4, loc="upper left")

    axes[3].step(times, pending_anchor_count, where="post", color="#17becf", linewidth=2.3, label="Pending anchor count")
    finite_anchor_limits = [value for value in max_pending_anchors if value != float("inf")]
    if finite_anchor_limits:
        axes[3].axhline(max(finite_anchor_limits), color="#555555", linestyle="--", linewidth=1.2, label="Max pending anchors")
    axes[3].set_ylabel("Pending anchors")
    axes[3].set_xlabel("Time, s")
    axes[3].legend(frameon=False, loc="upper left")

    for ax in axes:
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_dir / "adaptation_timeline.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    build_close_reason_counts(trace_path, output_dir)

    if scenario_name not in {"anchor-backpressure", "storage-degradation"}:
        return

    anchor_ack_target = payload.get("anchor_ack_target", 1.0)
    if "phases" in payload:
        phase_targets = [phase.get("anchor_ack_target") for phase in payload["phases"] if phase.get("anchor_ack_target")]
        if phase_targets:
            anchor_ack_target = phase_targets[0]
    fixed_nominal_target = _fixed_nominal_target(comparison_points, fallback=next_targets[0] if next_targets else 0.0)
    commit_frequency = _commit_frequency_series(points)

    fig, axes = plt.subplots(4, 1, figsize=(12.5, 10.2), sharex=True)
    axes[0].step(times, anchor_ack_latency, where="post", color="#9467bd", linewidth=2.2, label="Anchor ack latency")
    axes[0].axhline(anchor_ack_target, color="#555555", linestyle="--", linewidth=1.2, label="Anchor ack target")
    axes[0].set_ylabel("Anchor ack latency, s")
    axes[0].legend(frameon=False, loc="upper left")

    axes[1].step(times, pending_anchor_count, where="post", color="#17becf", linewidth=2.2, label="Pending anchor count")
    finite_anchor_limits = [value for value in max_pending_anchors if value != float("inf")]
    if finite_anchor_limits:
        axes[1].axhline(max(finite_anchor_limits), color="#555555", linestyle="--", linewidth=1.2, label="Max pending anchors")
    axes[1].set_ylabel("Pending anchor count")
    axes[1].legend(frameon=False, loc="upper left")

    axes[2].step(times, next_targets, where="post", color=POLICY_COLORS["adaptive"], linewidth=2.4, label="Adaptive target epoch size")
    if fixed_nominal_target:
        axes[2].axhline(fixed_nominal_target, color=POLICY_COLORS["fixed-nominal"], linestyle="--", linewidth=1.4, label="Fixed-nominal target")
    axes[2].set_ylabel("Target epoch size")
    axes[2].legend(frameon=False, loc="upper left")

    axes[3].step(times, commit_frequency, where="post", color="#7f7f7f", linewidth=2.2, label="Local commit frequency")
    if close_times:
        for index, close_time in enumerate(close_times):
            axes[3].axvline(
                close_time,
                color="#d62728",
                linestyle="--",
                linewidth=0.9,
                alpha=0.45,
                label="Root commit" if index == 0 else None,
            )
    axes[3].set_ylabel("Local commit frequency, 1/s")
    axes[3].set_xlabel("Time, s")
    axes[3].legend(frameon=False, loc="upper left")

    for ax in axes:
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_dir / "backpressure_response_timeline.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_stress_response_plot(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    traces = payload["policies"]
    phases = payload.get("phases", [])
    _apply_presentation_style()

    reference_policy = next(iter(traces))
    reference_points = traces[reference_policy]
    times = [point["time"] for point in reference_points]

    fig, axes = plt.subplots(3, 1, figsize=(14, 8.8), sharex=True)
    _shade_phases(list(axes), phases)
    axes[0].step(times, [point["arrival_rate"] for point in reference_points], where="post", linewidth=2.5, color="#2ca02c")
    ack_axis = axes[0].twinx()
    ack_axis.step(times, [point["anchor_ack_latency"] for point in reference_points], where="post", linewidth=2.0, color="#9467bd")
    axes[0].set_ylabel("Input rate, events/s")
    ack_axis.set_ylabel("Anchor ack latency, s")
    axes[0].legend(
        handles=[
            Line2D([0], [0], color="#2ca02c", lw=2.5, label="Input rate"),
            Line2D([0], [0], color="#9467bd", lw=2.0, label="Anchor ack latency"),
        ],
        frameon=False,
        loc="upper left",
    )

    response_policy_order = ["adaptive", "fixed-small", "fixed-nominal", "fixed-large"]
    for policy in response_policy_order:
        if policy not in traces:
            continue
        points = traces[policy]
        policy_times = [point["time"] for point in points]
        axes[1].step(
            policy_times,
            [point["next_target"] for point in points],
            where="post",
            linewidth=2.4,
            color=POLICY_COLORS[policy],
            label=POLICY_LABELS[policy],
        )

    axes[1].set_ylabel("Target epoch size, events")
    axes[1].legend(frameon=False, ncol=4, loc="upper left")

    close_markers_added = False
    for policy in response_policy_order:
        if policy not in traces:
            continue
        points = traces[policy]
        close_times = [point["time"] for point in points if point["should_close"]]
        close_targets = [point["next_target"] for point in points if point["should_close"]]
        if close_times:
            axes[1].scatter(
                close_times,
                close_targets,
                color=POLICY_COLORS[policy],
                s=26,
                alpha=0.8,
                zorder=3,
                label=f"{POLICY_LABELS[policy]} close" if not close_markers_added else None,
            )
            close_markers_added = True

    axes[2].step(times, [point["input_queue_fill"] for point in reference_points], where="post", linewidth=2.4, color="#ff7f0e")
    axes[2].axhline(0.9, color="#444444", linestyle="--", linewidth=1.4)
    axes[2].text(times[-1], 0.92, "Early-close threshold", ha="right", va="bottom", fontsize=10, color="#444444")
    axes[2].set_ylabel("Input queue fill")
    axes[2].set_xlabel("Time, s")

    for ax in axes:
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_stress_capacity_plot(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    curves = payload["curves"]
    _apply_presentation_style()

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharex=True)
    metrics = [
        ("p95_commit_latency", "P95 commit latency, s"),
        ("p95_queue_depth", "P95 queue depth, events"),
    ]

    for ax, (metric_key, ylabel) in zip(axes, metrics):
        for policy in POLICY_ORDER:
            if policy not in curves:
                continue
            points = curves[policy]
            x_values = [point["arrival_rate"] for point in points]
            y_values = [point.get(metric_key, 0.0) for point in points]
            ax.plot(
                x_values,
                y_values,
                marker="o",
                linewidth=2.4,
                markersize=6,
                color=POLICY_COLORS[policy],
                label=POLICY_LABELS[policy],
            )
            unsafe_x = [point["arrival_rate"] for point in points if not point.get("is_safe", True)]
            unsafe_y = [point.get(metric_key, 0.0) for point in points if not point.get("is_safe", True)]
            if unsafe_x:
                ax.scatter(unsafe_x, unsafe_y, marker="x", s=75, color=POLICY_COLORS[policy], linewidths=2.0)
        ax.set_xlabel("Input rate, events/s")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_stress_summary_table(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    curves = payload["curves"]
    policy_summaries = payload.get("policies", {})
    _apply_presentation_style()

    rows = []
    for policy in POLICY_ORDER:
        if policy not in curves or not curves[policy]:
            continue
        safe_point = policy_summaries.get(policy, {}).get("safe_point")
        if safe_point is None:
            safe_points = [point for point in curves[policy] if point.get("is_safe", True)]
            safe_point = safe_points[-1] if safe_points else None
        safe_throughput = policy_summaries.get(policy, {}).get(
            "safe_throughput",
            safe_point["arrival_rate"] if safe_point else 0.0,
        )
        rows.append(
            [
                POLICY_LABELS[policy],
                f"{safe_throughput:.0f}" if safe_point else "0",
                f"{safe_point.get('p95_commit_latency', 0.0):.2f}" if safe_point else "—",
                f"{safe_point.get('commit_frequency', 0.0):.2f}" if safe_point else "—",
                f"{safe_point.get('p95_queue_depth', 0.0):.1f}" if safe_point else "—",
            ]
        )

    fig, ax = plt.subplots(figsize=(11.5, 3.8))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=["Policy", "Safe throughput", "P95 latency", "Commits/s", "P95 queue"],
        loc="center",
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.0, 1.85)
    for (row_index, _), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_facecolor("#e9eef5")
            cell.set_text_props(weight="bold")
        elif row_index == 1:
            cell.set_facecolor("#d9edf7")
        else:
            cell.set_facecolor("#f8f9fa")
        cell.set_edgecolor("#c7cdd6")
    fig.tight_layout()
    fig.savefig(output_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def build_presentation_plots(
    batch_summary_path: Path,
    stress_summary_path: Path,
    adaptive_trace_path: Path,
    fixed_trace_path: Path,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _apply_presentation_style()

    batch_rows = _scenario_subset(
        _aggregate_batch_rows(json.loads(batch_summary_path.read_text(encoding="utf-8"))),
        PRESENTATION_SCENARIOS,
    )
    stress_summary = json.loads(stress_summary_path.read_text(encoding="utf-8"))
    adaptive_trace = json.loads(adaptive_trace_path.read_text(encoding="utf-8"))
    fixed_trace = json.loads(fixed_trace_path.read_text(encoding="utf-8"))
    scenarios = [scenario for scenario in PRESENTATION_SCENARIOS if any(row["scenario"] == scenario for row in batch_rows)]
    width = 0.18
    x_positions = list(range(len(scenarios)))
    legend_handles = _build_legend_handles()

    # 1. Security overview.
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharex=True)
    for ax, metric_key, ylabel in [
        (axes[0], "avg_commit_latency", "Average commit latency, s"),
        (axes[1], "p95_commit_latency", "P95 commit latency, s"),
    ]:
        for index, policy in enumerate(POLICY_ORDER):
            offsets = [x + (index - (len(POLICY_ORDER) - 1) / 2) * width for x in x_positions]
            heights = _metric_values(batch_rows, scenarios, policy, metric_key)
            bars = ax.bar(
                offsets,
                heights,
                width=width,
                color=POLICY_COLORS[policy],
                edgecolor="white",
                linewidth=0.8,
            )
            _annotate_bars(ax, bars, heights)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios])
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.legend(handles=legend_handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout()
    fig.savefig(output_dir / "commit_latency_overview.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    # 2. Cost overview.
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharex=True)
    for ax, metric_key, title, ylabel in [
        (axes[0], "commit_frequency", "", "Commit frequency, 1/s"),
        (axes[1], "p95_queue_depth", "", "P95 queue depth, events"),
    ]:
        for index, policy in enumerate(POLICY_ORDER):
            offsets = [x + (index - (len(POLICY_ORDER) - 1) / 2) * width for x in x_positions]
            heights = _metric_values(batch_rows, scenarios, policy, metric_key)
            bars = ax.bar(
                offsets,
                heights,
                width=width,
                color=POLICY_COLORS[policy],
                edgecolor="white",
                linewidth=0.8,
            )
            _annotate_bars(ax, bars, heights)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios])
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.legend(handles=legend_handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout()
    fig.savefig(output_dir / "cost_overview.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    # 3. Stress summary table.
    fig, ax = plt.subplots(figsize=(12.5, 3.8))
    ax.axis("off")
    headers = ["Policy", "Safe throughput", "Max latency", "Commits/s"]
    body = []
    for policy in POLICY_ORDER:
        row = stress_summary.get(policy, {})
        is_safe = row.get("safe_throughput", 0.0) > 0.0
        body.append(
            [
                POLICY_LABELS[policy],
                f"{row.get('safe_throughput', 0.0):.2f}" if is_safe else "unsafe",
                f"{row.get('max_commit_latency', 0.0):.2f}" if is_safe else "—",
                f"{row.get('commit_frequency_at_safe_throughput', 0.0):.2f}" if is_safe else "—",
            ]
        )
    table = ax.table(cellText=body, colLabels=headers, loc="center", cellLoc="center", colLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.05, 2.0)
    for (row_index, col_index), cell in table.get_celld().items():
        if row_index == 0:
            cell.set_facecolor("#e9eef5")
            cell.set_text_props(weight="bold")
        elif row_index == 1:
            cell.set_facecolor("#d9edf7")
        elif body[row_index - 1][1] == "unsafe":
            cell.set_facecolor("#f8d7da")
        else:
            cell.set_facecolor("#f8f9fa")
        cell.set_edgecolor("#c7cdd6")
    fig.tight_layout()
    fig.savefig(output_dir / "stress_summary_table.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)

    # 4. Dynamic adaptation timeline.
    adaptive_points = adaptive_trace["points"]
    fixed_points = fixed_trace["points"]
    adaptive_times, adaptive_rates = _step_series(adaptive_points, "arrival_rate")
    _, adaptive_ack = _step_series(adaptive_points, "anchor_ack_latency")
    _, adaptive_queue = _step_series(adaptive_points, "input_queue_fill")
    _, adaptive_targets = _step_series(adaptive_points, "next_target")
    fixed_times, fixed_targets = _step_series(fixed_points, "next_target")
    close_times = [point["time"] for point in adaptive_points if point["should_close"]]
    close_targets = [point["next_target"] for point in adaptive_points if point["should_close"]]

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    axes[0].step(adaptive_times, adaptive_rates, where="post", color="#2ca02c", linewidth=2.5, label="Input rate")
    ack_axis = axes[0].twinx()
    ack_axis.step(adaptive_times, adaptive_ack, where="post", color="#9467bd", linewidth=2.0, label="Anchor ack latency")
    axes[0].set_ylabel("events/s")
    ack_axis.set_ylabel("Anchor ack latency, s")
    axes[0].grid(alpha=0.2, linestyle="--")
    top_handles = [
        Line2D([0], [0], color="#2ca02c", lw=2.5, label="Input rate"),
        Line2D([0], [0], color="#9467bd", lw=2.0, label="Anchor ack latency"),
    ]
    axes[0].legend(handles=top_handles, frameon=False, loc="upper left")

    axes[1].step(adaptive_times, adaptive_targets, where="post", color=POLICY_COLORS["adaptive"], linewidth=2.8, label="Adaptive")
    axes[1].step(
        fixed_times,
        fixed_targets,
        where="post",
        color=POLICY_COLORS["fixed-small"],
        linewidth=2.4,
        label="Fixed-small",
    )
    if close_times:
        axes[1].scatter(close_times, close_targets, color="#d62728", s=60, zorder=3, label="Epoch close")
    axes[1].set_ylabel("Target epoch size, events")
    axes[1].grid(alpha=0.2, linestyle="--")
    axes[1].legend(frameon=False, ncol=3, loc="upper left")

    axes[2].step(adaptive_times, adaptive_queue, where="post", color="#ff7f0e", linewidth=2.4)
    axes[2].axhline(0.9, color="#444444", linestyle="--", linewidth=1.4)
    axes[2].text(adaptive_times[-1], 0.92, "Early-close threshold", ha="right", va="bottom", fontsize=10, color="#444444")
    axes[2].set_ylabel("Input queue fill")
    axes[2].set_xlabel("Time, s")
    axes[2].grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    fig.savefig(output_dir / "adaptation_timeline.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build PNG plots from batch or stress summaries.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--summary", required=True)
    batch_parser.add_argument("--output-dir", required=True)

    stress_parser = subparsers.add_parser("stress")
    stress_parser.add_argument("--summary", required=True)
    stress_parser.add_argument("--output-dir", required=True)

    timeline_parser = subparsers.add_parser("timeline")
    timeline_parser.add_argument("--summary", required=True)
    timeline_parser.add_argument("--output-dir", required=True)

    response_parser = subparsers.add_parser("stress-response")
    response_parser.add_argument("--summary", required=True)
    response_parser.add_argument("--output", required=True)

    capacity_parser = subparsers.add_parser("stress-capacity")
    capacity_parser.add_argument("--summary", required=True)
    capacity_parser.add_argument("--output", required=True)

    summary_table_parser = subparsers.add_parser("stress-summary-table")
    summary_table_parser.add_argument("--summary", required=True)
    summary_table_parser.add_argument("--output", required=True)

    presentation_parser = subparsers.add_parser("presentation")
    presentation_parser.add_argument("--batch-summary", required=True)
    presentation_parser.add_argument("--stress-summary", required=True)
    presentation_parser.add_argument("--adaptive-trace", required=True)
    presentation_parser.add_argument("--fixed-trace", required=True)
    presentation_parser.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)
    if args.command == "batch":
        build_batch_plots(Path(args.summary), Path(args.output_dir))
    elif args.command == "stress":
        build_stress_plots(Path(args.summary), Path(args.output_dir))
    elif args.command == "timeline":
        build_timeline_plots(Path(args.summary), Path(args.output_dir))
    elif args.command == "stress-response":
        build_stress_response_plot(Path(args.summary), Path(args.output))
    elif args.command == "stress-capacity":
        build_stress_capacity_plot(Path(args.summary), Path(args.output))
    elif args.command == "stress-summary-table":
        build_stress_summary_table(Path(args.summary), Path(args.output))
    else:
        build_presentation_plots(
            batch_summary_path=Path(args.batch_summary),
            stress_summary_path=Path(args.stress_summary),
            adaptive_trace_path=Path(args.adaptive_trace),
            fixed_trace_path=Path(args.fixed_trace),
            output_dir=Path(args.output_dir),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
