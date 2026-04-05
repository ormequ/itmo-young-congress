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
    scenarios = sorted({row["scenario"] for row in rows})
    policies = [policy for policy in POLICY_ORDER if any(row["policy"] == policy for row in rows)]
    values = {
        (row["scenario"], row["policy"]): row[metric_key]
        for row in rows
    }

    fig, ax = plt.subplots(figsize=(12, 6))
    width = 0.18 if len(policies) > 1 else 0.5
    x_positions = list(range(len(scenarios)))

    for index, policy in enumerate(policies):
        offsets = [x + (index - (len(policies) - 1) / 2) * width for x in x_positions]
        heights = [values.get((scenario, policy), 0.0) for scenario in scenarios]
        ax.bar(offsets, heights, width=width, label=policy, color=POLICY_COLORS.get(policy))

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(scenarios, rotation=20, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _plot_tradeoff(rows: list[dict], output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    for policy in POLICY_ORDER:
        policy_rows = [row for row in rows if row["policy"] == policy]
        if not policy_rows:
            continue
        x = [row["commit_frequency"] for row in policy_rows]
        y = [row["avg_vulnerability_window"] for row in policy_rows]
        ax.scatter(x, y, label=policy, s=60, color=POLICY_COLORS.get(policy))
        for row in policy_rows:
            ax.annotate(row["scenario"], (row["commit_frequency"], row["avg_vulnerability_window"]), fontsize=8)

    ax.set_title("Компромисс: частота фиксаций и окно уязвимости")
    ax.set_xlabel("Частота фиксаций")
    ax.set_ylabel("Среднее окно уязвимости")
    ax.legend()
    ax.grid(alpha=0.25)
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
        fig, ax = plt.subplots(figsize=(8, 5))
        heights = [summary[policy][metric_key] for policy in policies]
        colors = [POLICY_COLORS.get(policy) for policy in policies]
        ax.bar(policies, heights, color=colors)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build PNG plots from batch or stress summaries.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--summary", required=True)
    batch_parser.add_argument("--output-dir", required=True)

    stress_parser = subparsers.add_parser("stress")
    stress_parser.add_argument("--summary", required=True)
    stress_parser.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)
    summary_path = Path(args.summary)
    output_dir = Path(args.output_dir)

    if args.command == "batch":
        build_batch_plots(summary_path, output_dir)
    else:
        build_stress_plots(summary_path, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
