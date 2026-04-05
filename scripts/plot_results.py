from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

_cache_dir = Path(tempfile.gettempdir()) / "matplotlib-cache"
_cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_cache_dir))
os.environ.setdefault("XDG_CACHE_HOME", str(_cache_dir))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


POLICY_ORDER = ["adaptive", "fixed-small", "fixed-nominal", "fixed-large"]
POLICY_COLORS = {
    "adaptive": "#1f77b4",
    "fixed-small": "#ff7f0e",
    "fixed-nominal": "#2ca02c",
    "fixed-large": "#d62728",
}
POLICY_LABELS = {
    "adaptive": "Adaptive",
    "fixed-small": "Fixed-S",
    "fixed-nominal": "Fixed-N",
    "fixed-large": "Fixed-L",
}


def _apply_presentation_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 16,
            "axes.labelsize": 13,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
        }
    )


def _short_scenario_name(name: str) -> str:
    mapping = {
        "combined-stress": "combined",
        "critical-event-injection": "critical",
        "storage-degradation": "storage",
        "queue-saturation": "queue",
        "cpu-pressure": "cpu",
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
                "avg_vulnerability_window": sum(item["avg_vulnerability_window"] for item in group) / count,
                "max_vulnerability_window": max(item["max_vulnerability_window"] for item in group),
                "commit_frequency": sum(item["commit_frequency"] for item in group) / count,
                "max_queue_depth": max(item["max_queue_depth"] for item in group),
                "avg_proof_bytes": sum(item["avg_proof_bytes"] for item in group) / count,
            }
        )
    summary.sort(key=lambda item: (item["scenario"], POLICY_ORDER.index(item["policy"])))
    return summary


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
    values = {
        (row["scenario"], row["policy"]): row[metric_key]
        for row in rows
    }

    fig, ax = plt.subplots(figsize=(12, 6.5))
    width = 0.18 if len(policies) > 1 else 0.5
    x_positions = list(range(len(scenarios)))

    for index, policy in enumerate(policies):
        offsets = [x + (index - (len(policies) - 1) / 2) * width for x in x_positions]
        heights = [values.get((scenario, policy), 0.0) for scenario in scenarios]
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

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios], rotation=15, ha="right")
    ax.legend(loc="upper center", ncol=len(policies), frameon=False, bbox_to_anchor=(0.5, 1.12))
    ax.grid(axis="y", alpha=0.2, linestyle="--")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_tradeoff(rows: list[dict], output_path: Path) -> None:
    _apply_presentation_style()
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for policy in POLICY_ORDER:
        policy_rows = [row for row in rows if row["policy"] == policy]
        if not policy_rows:
            continue
        x = [row["commit_frequency"] for row in policy_rows]
        y = [row["avg_vulnerability_window"] for row in policy_rows]
        ax.scatter(x, y, label=POLICY_LABELS.get(policy, policy), s=90, color=POLICY_COLORS.get(policy))
        for row in policy_rows:
            ax.annotate(
                _short_scenario_name(row["scenario"]),
                (row["commit_frequency"], row["avg_vulnerability_window"]),
                fontsize=9,
                xytext=(5, 5),
                textcoords="offset points",
            )

    ax.set_title("Компромисс: частота фиксаций и окно уязвимости")
    ax.set_xlabel("Частота фиксаций")
    ax.set_ylabel("Среднее окно уязвимости")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def build_batch_plots(summary_path: Path, output_dir: Path) -> None:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    summary = _aggregate_batch_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    _plot_grouped_bars(
        summary,
        "avg_vulnerability_window",
        "Среднее окно уязвимости",
        "Секунды",
        output_dir / "avg_window.png",
    )
    _plot_grouped_bars(
        summary,
        "max_vulnerability_window",
        "Максимальное окно уязвимости",
        "Секунды",
        output_dir / "max_window.png",
    )
    _plot_grouped_bars(
        summary,
        "commit_frequency",
        "Частота фиксаций",
        "Фиксаций в секунду",
        output_dir / "commit_frequency.png",
    )
    _plot_grouped_bars(
        summary,
        "max_queue_depth",
        "Максимальная глубина очереди",
        "События",
        output_dir / "max_queue_depth.png",
    )
    _plot_grouped_bars(
        summary,
        "avg_proof_bytes",
        "Средний размер доказательства",
        "Байты",
        output_dir / "avg_proof_bytes.png",
    )
    _plot_tradeoff(summary, output_dir / "tradeoff.png")


def build_stress_plots(summary_path: Path, output_dir: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
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
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
        fig.tight_layout()
        fig.savefig(output_dir / filename, dpi=180)
        plt.close(fig)

    plot_metric("safe_throughput", "Безопасная пропускная способность", "Событий в секунду", "safe_throughput.png")
    plot_metric(
        "commit_frequency_at_safe_throughput",
        "Частота фиксаций при безопасной пропускной способности",
        "Фиксаций в секунду",
        "stress_commit_frequency.png",
    )
    plot_metric(
        "max_vulnerability_window",
        "Максимальное окно уязвимости при безопасной пропускной способности",
        "Секунды",
        "stress_max_window.png",
    )
    plot_metric(
        "avg_proof_bytes_at_safe_throughput",
        "Средний размер доказательства при безопасной пропускной способности",
        "Байты",
        "stress_avg_proof_bytes.png",
    )


def build_timeline_plots(trace_path: Path, output_dir: Path) -> None:
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    points = payload["points"]
    output_dir.mkdir(parents=True, exist_ok=True)
    _apply_presentation_style()

    times = [point["time"] for point in points]
    next_targets = [point["next_target"] for point in points]
    arrival_rates = [point["arrival_rate"] for point in points]
    queue_fill = [point["queue_fill"] for point in points]
    ack_latency = [point["ack_latency"] for point in points]
    close_times = [point["time"] for point in points if point["should_close"]]
    close_targets = [point["next_target"] for point in points if point["should_close"]]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.step(times, next_targets, where="post", color=POLICY_COLORS["adaptive"], linewidth=2.5, label="Target эпохи")
    if close_times:
        ax.scatter(close_times, close_targets, color="#d62728", s=70, zorder=3, label="Закрытие эпохи")
    ax.set_title(f"Перестройка размера эпохи во времени: {payload['scenario']}")
    ax.set_xlabel("Время, с")
    ax.set_ylabel("Целевой размер эпохи, событий")
    ax.grid(alpha=0.2, linestyle="--")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "target_timeline.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    axes[0].step(times, arrival_rates, where="post", color="#2ca02c", linewidth=2.0)
    axes[0].set_ylabel("Поток, evt/s")
    axes[0].set_title(f"Изменение условий во времени: {payload['scenario']}")
    axes[0].grid(alpha=0.2, linestyle="--")

    axes[1].step(times, queue_fill, where="post", color="#ff7f0e", linewidth=2.0)
    axes[1].set_ylabel("Очередь")
    axes[1].grid(alpha=0.2, linestyle="--")

    axes[2].step(times, ack_latency, where="post", color="#9467bd", linewidth=2.0)
    axes[2].set_ylabel("Ack, с")
    axes[2].set_xlabel("Время, с")
    axes[2].grid(alpha=0.2, linestyle="--")

    fig.tight_layout()
    fig.savefig(output_dir / "telemetry_timeline.png", dpi=180)
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

    args = parser.parse_args(argv)
    summary_path = Path(args.summary)
    output_dir = Path(args.output_dir)

    if args.command == "batch":
        build_batch_plots(summary_path, output_dir)
    elif args.command == "stress":
        build_stress_plots(summary_path, output_dir)
    else:
        build_timeline_plots(summary_path, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
