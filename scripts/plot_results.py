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
from matplotlib.lines import Line2D


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
PRESENTATION_SCENARIOS = ["anomaly-recovery", "storage-degradation", "queue-saturation"]


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
        "anomaly-recovery": "anomaly",
        "anomaly-spike": "anomaly",
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
    values = {(row["scenario"], row["policy"]): row[metric_key] for row in rows}
    return [values.get((scenario, policy), 0.0) for scenario in scenarios]


def _step_series(points: list[dict], metric_key: str) -> tuple[list[float], list[float]]:
    return [point["time"] for point in points], [point[metric_key] for point in points]


def _phase_label(phase: dict) -> str:
    if phase["queue_fill"] >= 0.9 or phase["ack_latency"] >= 2.5:
        return "Крит."
    if phase["rate"] >= 14:
        return "Пик"
    if phase["rate"] <= 6 and phase["ack_latency"] <= 1.1:
        return "Восст."
    return "Переход"


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


def build_stress_response_plot(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    traces = payload["policies"]
    phases = payload.get("phases", [])
    window_points = payload.get("window_points", {})
    _apply_presentation_style()

    reference_policy = next(iter(traces))
    reference_points = traces[reference_policy]
    times = [point["time"] for point in reference_points]

    fig, axes = plt.subplots(4, 1, figsize=(14, 11.5), sharex=True)
    _shade_phases(list(axes), phases)
    axes[0].step(times, [point["arrival_rate"] for point in reference_points], where="post", linewidth=2.5, color="#2ca02c")
    ack_axis = axes[0].twinx()
    ack_axis.step(times, [point["ack_latency"] for point in reference_points], where="post", linewidth=2.0, color="#9467bd")
    axes[0].set_title("Stress-response: как adaptive меняет режим работы под давлением среды", pad=16)
    axes[0].set_ylabel("Поток, evt/s")
    ack_axis.set_ylabel("Ack, с")
    axes[0].legend(
        handles=[
            Line2D([0], [0], color="#2ca02c", lw=2.5, label="Входной поток"),
            Line2D([0], [0], color="#9467bd", lw=2.0, label="Ack latency"),
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

    axes[1].set_ylabel("Размер эпохи")
    axes[1].legend(frameon=False, ncol=4, loc="upper left")

    for policy in response_policy_order:
        if policy not in window_points:
            continue
        points = window_points[policy]
        axes[2].plot(
            [point["time"] for point in points],
            [point["avg_window"] for point in points],
            marker="o",
            linewidth=2.2,
            markersize=3.8,
            color=POLICY_COLORS[policy],
            label=POLICY_LABELS[policy],
        )
    axes[2].set_ylabel("Avg окно, с")
    axes[2].legend(frameon=False, ncol=4, loc="upper left")

    axes[3].step(times, [point["queue_fill"] for point in reference_points], where="post", linewidth=2.4, color="#ff7f0e")
    axes[3].axhline(0.9, color="#444444", linestyle="--", linewidth=1.4)
    axes[3].text(times[-1], 0.92, "Порог early close", ha="right", va="bottom", fontsize=10, color="#444444")
    axes[3].set_ylabel("Очередь")
    axes[3].set_xlabel("Время, с")

    for ax in axes:
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_stress_capacity_plot(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    curves = payload["curves"]
    _apply_presentation_style()

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharex=True)
    metrics = [
        ("commit_frequency", "Частота фиксаций", "Фиксаций в секунду"),
        ("signature_time_per_second", "Крипто-время в секунду", "Секунды/с"),
    ]

    for ax, (metric_key, title, ylabel) in zip(axes, metrics):
        for policy in POLICY_ORDER:
            if policy not in curves:
                continue
            points = curves[policy]
            x_values = [point["arrival_rate"] for point in points]
            y_values = [point[metric_key] for point in points]
            ax.plot(
                x_values,
                y_values,
                marker="o",
                linewidth=2.4,
                markersize=6,
                color=POLICY_COLORS[policy],
                label=POLICY_LABELS[policy],
            )
        ax.set_title(title)
        ax.set_xlabel("Входной поток, evt/s")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    fig.suptitle("Stress-capacity: цена устойчивости при росте нагрузки", fontsize=18, y=1.02)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_stress_summary_table(summary_path: Path, output_path: Path) -> None:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    curves = payload["curves"]
    _apply_presentation_style()

    rows = []
    for policy in POLICY_ORDER:
        if policy not in curves or not curves[policy]:
            continue
        point = curves[policy][-1]
        rows.append(
            [
                POLICY_LABELS[policy],
                f"{point['arrival_rate']:.0f}",
                f"{point['avg_vulnerability_window']:.2f}",
                f"{point['commit_frequency']:.2f}",
                f"{point['signature_time_per_second']:.3f}",
            ]
        )

    fig, ax = plt.subplots(figsize=(11.5, 3.6))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=["Политика", "Поток", "Avg окно", "Фиксации/с", "Крипто-время/с"],
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
    ax.set_title("Итоги при максимальном уровне нагрузки", fontsize=16, pad=16)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
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
    for ax, metric_key, title, ylabel in [
        (axes[0], "avg_vulnerability_window", "Среднее окно уязвимости", "Секунды"),
        (axes[1], "max_vulnerability_window", "Максимальное окно уязвимости", "Секунды"),
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
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios])
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.legend(handles=legend_handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Безопасность в переменных сценариях", fontsize=18, y=1.08)
    fig.tight_layout()
    fig.savefig(output_dir / "window_overview.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # 2. Cost overview.
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharex=True)
    for ax, metric_key, title, ylabel in [
        (axes[0], "commit_frequency", "Частота фиксаций", "Фиксаций в секунду"),
        (axes[1], "max_queue_depth", "Пиковая глубина очереди", "События"),
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
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(x_positions)
        ax.set_xticklabels([_short_scenario_name(scenario) for scenario in scenarios])
        ax.grid(axis="y", alpha=0.2, linestyle="--")
        ax.set_axisbelow(True)
    fig.legend(handles=legend_handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("Цена достижения устойчивости", fontsize=18, y=1.08)
    fig.tight_layout()
    fig.savefig(output_dir / "cost_overview.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # 3. Stress summary table.
    fig, ax = plt.subplots(figsize=(12.5, 3.8))
    ax.axis("off")
    headers = ["Политика", "Достигнутый поток", "Max окно", "Частота фиксаций", "Крипто-время/с"]
    body = []
    for policy in POLICY_ORDER:
        row = stress_summary.get(policy, {})
        is_safe = row.get("safe_throughput", 0.0) > 0.0
        body.append(
            [
                POLICY_LABELS[policy],
                f"{row.get('safe_throughput', 0.0):.2f}" if is_safe else "не удерживает верхний уровень",
                f"{row.get('max_vulnerability_window', 0.0):.2f}" if is_safe else "—",
                f"{row.get('commit_frequency_at_safe_throughput', 0.0):.2f}" if is_safe else "—",
                f"{row.get('signature_time_per_second_at_safe_throughput', 0.0):.2f}" if is_safe else "—",
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
        elif body[row_index - 1][1] == "не удерживает верхний уровень":
            cell.set_facecolor("#f8d7da")
        else:
            cell.set_facecolor("#f8f9fa")
        cell.set_edgecolor("#c7cdd6")
    ax.set_title(
        "Итоги stress-сценария",
        fontsize=16,
        pad=18,
    )
    fig.tight_layout()
    fig.savefig(output_dir / "stress_summary_table.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # 4. Dynamic adaptation timeline.
    adaptive_points = adaptive_trace["points"]
    fixed_points = fixed_trace["points"]
    adaptive_times, adaptive_rates = _step_series(adaptive_points, "arrival_rate")
    _, adaptive_ack = _step_series(adaptive_points, "ack_latency")
    _, adaptive_queue = _step_series(adaptive_points, "queue_fill")
    _, adaptive_targets = _step_series(adaptive_points, "next_target")
    fixed_times, fixed_targets = _step_series(fixed_points, "next_target")
    close_times = [point["time"] for point in adaptive_points if point["should_close"]]
    close_targets = [point["next_target"] for point in adaptive_points if point["should_close"]]

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    axes[0].step(adaptive_times, adaptive_rates, where="post", color="#2ca02c", linewidth=2.5, label="Входной поток")
    ack_axis = axes[0].twinx()
    ack_axis.step(adaptive_times, adaptive_ack, where="post", color="#9467bd", linewidth=2.0, label="Ack latency")
    axes[0].set_ylabel("Событий/с")
    ack_axis.set_ylabel("Ack, с")
    axes[0].set_title("Адаптивная политика перестраивает размер эпохи по ходу сценария")
    axes[0].grid(alpha=0.2, linestyle="--")
    top_handles = [
        Line2D([0], [0], color="#2ca02c", lw=2.5, label="Входной поток"),
        Line2D([0], [0], color="#9467bd", lw=2.0, label="Ack latency"),
    ]
    axes[0].legend(handles=top_handles, frameon=False, loc="upper left")

    axes[1].step(adaptive_times, adaptive_targets, where="post", color=POLICY_COLORS["adaptive"], linewidth=2.8, label="Adaptive")
    axes[1].step(fixed_times, fixed_targets, where="post", color=POLICY_COLORS["fixed-small"], linewidth=2.4, label="Fixed-S")
    if close_times:
        axes[1].scatter(close_times, close_targets, color="#d62728", s=60, zorder=3, label="Закрытие эпохи")
    axes[1].set_ylabel("Размер эпохи")
    axes[1].grid(alpha=0.2, linestyle="--")
    axes[1].legend(frameon=False, ncol=3, loc="upper left")

    axes[2].step(adaptive_times, adaptive_queue, where="post", color="#ff7f0e", linewidth=2.4)
    axes[2].axhline(0.9, color="#444444", linestyle="--", linewidth=1.4)
    axes[2].text(adaptive_times[-1], 0.92, "Порог early close", ha="right", va="bottom", fontsize=10, color="#444444")
    axes[2].set_ylabel("Очередь")
    axes[2].set_xlabel("Время, с")
    axes[2].grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    fig.savefig(output_dir / "adaptation_timeline.png", dpi=180, bbox_inches="tight")
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
