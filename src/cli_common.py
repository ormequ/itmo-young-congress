from __future__ import annotations

import json
from pathlib import Path

from domain import ArrivalSegment, ScenarioConfig
from policies import AdaptiveEpochPolicy, FixedEpochPolicy
from settings import load_settings


def load_scenario(path: Path) -> ScenarioConfig:
    settings = load_settings()
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = tuple(ArrivalSegment(**segment) for segment in payload["segments"])
    return ScenarioConfig(
        name=payload["name"],
        duration=payload["duration"],
        queue_capacity=payload["queue_capacity"],
        target_commit_latency=payload["target_commit_latency"],
        segments=segments,
        telemetry_window_size=payload.get("telemetry_window_size", settings.telemetry_window_size),
        anomaly_score_threshold=payload.get("anomaly_score_threshold", settings.anomaly_score_threshold),
        criticality_threshold=payload.get("criticality_threshold", settings.criticality_threshold),
        epoch_buffer_budget_bytes=payload.get("epoch_buffer_budget_bytes", settings.epoch_buffer_budget_bytes),
        max_pending_anchors=payload.get("max_pending_anchors", settings.max_pending_anchors),
    )


def make_policies(scenario: ScenarioConfig) -> dict:
    settings = load_settings()
    nominal = max(2, round(scenario.target_commit_latency * scenario.segments[0].rate))
    adaptive = AdaptiveEpochPolicy(
        target_commit_latency=scenario.target_commit_latency,
        min_epoch_events=settings.min_epoch_events,
        max_epoch_events=settings.max_epoch_events,
        min_epoch_duration_seconds=settings.min_epoch_duration_seconds,
        max_epoch_duration_seconds=settings.max_epoch_duration_seconds,
        change_threshold=settings.policy_change_threshold,
        anchor_ack_target=settings.policy_anchor_ack_target,
        criticality_threshold=scenario.criticality_threshold,
        anomaly_score_threshold=scenario.anomaly_score_threshold,
        epoch_buffer_budget_bytes=scenario.epoch_buffer_budget_bytes,
        max_pending_anchors=scenario.max_pending_anchors,
    )
    return {
        "fixed-small": FixedEpochPolicy(
            epoch_size=max(1, nominal // 2),
        ),
        "fixed-nominal": FixedEpochPolicy(
            epoch_size=nominal,
        ),
        "fixed-large": FixedEpochPolicy(
            epoch_size=max(nominal * 4, 1),
        ),
        "adaptive": adaptive,
        "adaptive-no-arrival-rate": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_arrival_rate": False}),
        "adaptive-no-anchor-ack-latency": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_anchor_ack_latency": False}),
        "adaptive-no-cpu-load": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_cpu_load": False}),
        "adaptive-no-input-queue-fill": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_input_queue_fill": False}),
        "adaptive-no-pending-anchors": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_pending_anchors": False}),
        "adaptive-no-early-close": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_early_close": False}),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
