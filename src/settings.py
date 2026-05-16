from __future__ import annotations

from dataclasses import dataclass
import os


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    # Default telemetry values for generated scenario segments when JSON omits them.
    segment_anchor_ack_latency: float
    segment_cpu_load: float
    segment_input_queue_fill: float
    segment_source_priority: float
    # Rolling-window settings for anomaly detection over telemetry and data values.
    telemetry_window_size: int
    anomaly_score_threshold: float
    criticality_threshold: float
    # Optional lower/upper bounds for epoch size in number of events.
    min_epoch_events: int
    max_epoch_events: float
    # Optional lower/upper bounds for open-window duration in seconds.
    min_epoch_duration_seconds: float
    max_epoch_duration_seconds: float
    # Core adaptive-policy controls.
    policy_change_threshold: float
    policy_anchor_ack_target: float
    # Scaling factors for adaptive reaction to degraded storage latency.
    policy_anchor_ack_latency_scale: float
    policy_anchor_ack_latency_cap: float
    # Scaling factors for adaptive reaction to high CPU pressure.
    policy_cpu_load_trigger: float
    policy_cpu_load_scale: float
    policy_cpu_load_cap: float
    # Queue-based shrinking and hard early-close thresholds.
    policy_input_queue_fill_trigger: float
    policy_input_queue_fill_min_scale: float
    policy_input_queue_close_threshold: float
    epoch_buffer_budget_bytes: float
    policy_memory_pressure_trigger: float
    policy_memory_pressure_min_scale: float
    max_pending_anchors: float
    policy_pending_anchor_scale: float
    policy_pending_anchor_cap: float
    policy_cpu_close_threshold: float
    # Generated event defaults for synthetic data value and criticality labels.
    simulator_generated_data_value: float
    simulator_generated_criticality_default: float
    simulator_generated_criticality_critical: float


def load_settings() -> Settings:
    return Settings(
        # Baseline segment telemetry used when configs omit per-segment values.
        segment_anchor_ack_latency=_env_float("SEGMENT_ANCHOR_ACK_LATENCY", 1.0),
        segment_cpu_load=_env_float("SEGMENT_CPU_LOAD", 0.2),
        segment_input_queue_fill=_env_float("SEGMENT_INPUT_QUEUE_FILL", 0.1),
        segment_source_priority=_env_float("SEGMENT_SOURCE_PRIORITY", 1.0),
        # Rolling anomaly detector defaults.
        telemetry_window_size=_env_int("TELEMETRY_WINDOW_SIZE", 5),
        anomaly_score_threshold=_env_float("ANOMALY_SCORE_THRESHOLD", 3.0),
        criticality_threshold=_env_float("CRITICALITY_THRESHOLD", 0.95),
        # Optional epoch constraints; default values keep them effectively disabled.
        min_epoch_events=_env_int("MIN_EPOCH_EVENTS", 0),
        max_epoch_events=_env_float("MAX_EPOCH_EVENTS", float("inf")),
        min_epoch_duration_seconds=_env_float("MIN_EPOCH_DURATION_SECONDS", 0.0),
        max_epoch_duration_seconds=_env_float("MAX_EPOCH_DURATION_SECONDS", float("inf")),
        # Core adaptive-policy defaults.
        policy_change_threshold=_env_float("POLICY_CHANGE_THRESHOLD", 0.15),
        policy_anchor_ack_target=_env_float("POLICY_ANCHOR_ACK_TARGET", 1.0),
        # Storage-latency adjustment coefficients.
        policy_anchor_ack_latency_scale=_env_float("POLICY_ANCHOR_ACK_LATENCY_SCALE", 0.15),
        policy_anchor_ack_latency_cap=_env_float("POLICY_ANCHOR_ACK_LATENCY_CAP", 0.2),
        # CPU-load adjustment coefficients.
        policy_cpu_load_trigger=_env_float("POLICY_CPU_LOAD_TRIGGER", 0.8),
        policy_cpu_load_scale=_env_float("POLICY_CPU_LOAD_SCALE", 0.3),
        policy_cpu_load_cap=_env_float("POLICY_CPU_LOAD_CAP", 0.1),
        # Queue and anomaly-triggered early-close thresholds.
        policy_input_queue_fill_trigger=_env_float("POLICY_INPUT_QUEUE_FILL_TRIGGER", 0.8),
        policy_input_queue_fill_min_scale=_env_float("POLICY_INPUT_QUEUE_FILL_MIN_SCALE", 0.25),
        policy_input_queue_close_threshold=_env_float("POLICY_INPUT_QUEUE_CLOSE_THRESHOLD", 0.9),
        epoch_buffer_budget_bytes=_env_float("EPOCH_BUFFER_BUDGET_BYTES", float("inf")),
        policy_memory_pressure_trigger=_env_float("POLICY_MEMORY_PRESSURE_TRIGGER", 0.8),
        policy_memory_pressure_min_scale=_env_float("POLICY_MEMORY_PRESSURE_MIN_SCALE", 0.25),
        max_pending_anchors=_env_float("MAX_PENDING_ANCHORS", float("inf")),
        policy_pending_anchor_scale=_env_float("POLICY_PENDING_ANCHOR_SCALE", 0.25),
        policy_pending_anchor_cap=_env_float("POLICY_PENDING_ANCHOR_CAP", 0.5),
        policy_cpu_close_threshold=_env_float("POLICY_CPU_CLOSE_THRESHOLD", 0.95),
        # Synthetic event payload defaults used by the simulator.
        simulator_generated_data_value=_env_float("SIMULATOR_DATA_VALUE", 1.0),
        simulator_generated_criticality_default=_env_float("SIMULATOR_CRITICALITY_DEFAULT", 0.1),
        simulator_generated_criticality_critical=_env_float("SIMULATOR_CRITICALITY_CRITICAL", 1.0),
    )
