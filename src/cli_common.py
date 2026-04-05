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
        target_window=payload["target_window"],
        segments=segments,
        telemetry_window_size=payload.get("telemetry_window_size", settings.telemetry_window_size),
        anomaly_sigma_threshold=payload.get("anomaly_sigma_threshold", settings.anomaly_sigma_threshold),
        criticality_threshold=payload.get("criticality_threshold", settings.criticality_threshold),
    )


def make_policies(scenario: ScenarioConfig) -> dict:
    settings = load_settings()
    nominal = max(2, round(scenario.target_window * scenario.segments[0].rate))
    adaptive = AdaptiveEpochPolicy(
        target_window=scenario.target_window,
        min_epoch_events=settings.min_epoch_events,
        max_epoch_events=settings.max_epoch_events,
        min_window_seconds=settings.min_window_seconds,
        max_window_seconds=settings.max_window_seconds,
        change_threshold=settings.policy_change_threshold,
        ack_target=settings.policy_ack_target,
        criticality_threshold=scenario.criticality_threshold,
    )
    return {
        "fixed-small": FixedEpochPolicy(
            epoch_size=max(1, nominal // 2),
            min_epoch_events=settings.min_epoch_events,
            max_epoch_events=settings.max_epoch_events,
            min_window_seconds=settings.min_window_seconds,
            max_window_seconds=settings.max_window_seconds,
        ),
        "fixed-nominal": FixedEpochPolicy(
            epoch_size=nominal,
            min_epoch_events=settings.min_epoch_events,
            max_epoch_events=settings.max_epoch_events,
            min_window_seconds=settings.min_window_seconds,
            max_window_seconds=settings.max_window_seconds,
        ),
        "fixed-large": FixedEpochPolicy(
            epoch_size=max(nominal * 4, 1),
            min_epoch_events=settings.min_epoch_events,
            max_epoch_events=settings.max_epoch_events,
            min_window_seconds=settings.min_window_seconds,
            max_window_seconds=settings.max_window_seconds,
        ),
        "adaptive": adaptive,
        "adaptive-no-arrival-rate": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_arrival_rate": False}),
        "adaptive-no-ack-latency": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_ack_latency": False}),
        "adaptive-no-cpu-load": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_cpu_load": False}),
        "adaptive-no-queue-fill": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_queue_fill": False}),
        "adaptive-no-early-close": AdaptiveEpochPolicy(**{**adaptive.__dict__, "use_early_close": False}),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
