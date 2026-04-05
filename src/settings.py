from __future__ import annotations

from dataclasses import dataclass
import os


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    segment_ack_latency: float
    segment_cpu_load: float
    segment_queue_fill: float
    telemetry_window_size: int
    anomaly_sigma_threshold: float
    criticality_threshold: float
    policy_min_epoch: int
    policy_max_epoch_floor: int
    policy_max_epoch_multiplier: int
    policy_change_threshold: float
    policy_ack_target: float
    policy_ack_latency_scale: float
    policy_ack_latency_cap: float
    policy_cpu_load_trigger: float
    policy_cpu_load_scale: float
    policy_cpu_load_cap: float
    policy_queue_fill_trigger: float
    policy_queue_fill_min_scale: float
    policy_queue_close_threshold: float
    policy_cpu_close_threshold: float
    policy_ack_close_multiplier: float
    simulator_generated_data_value: float
    simulator_generated_criticality_default: float
    simulator_generated_criticality_critical: float


def load_settings() -> Settings:
    return Settings(
        segment_ack_latency=_env_float("IYC_SEGMENT_ACK_LATENCY", 1.0),
        segment_cpu_load=_env_float("IYC_SEGMENT_CPU_LOAD", 0.2),
        segment_queue_fill=_env_float("IYC_SEGMENT_QUEUE_FILL", 0.1),
        telemetry_window_size=_env_int("IYC_TELEMETRY_WINDOW_SIZE", 5),
        anomaly_sigma_threshold=_env_float("IYC_ANOMALY_SIGMA_THRESHOLD", 3.0),
        criticality_threshold=_env_float("IYC_CRITICALITY_THRESHOLD", 0.9),
        policy_min_epoch=_env_int("IYC_POLICY_MIN_EPOCH", 2),
        policy_max_epoch_floor=_env_int("IYC_POLICY_MAX_EPOCH_FLOOR", 8),
        policy_max_epoch_multiplier=_env_int("IYC_POLICY_MAX_EPOCH_MULTIPLIER", 4),
        policy_change_threshold=_env_float("IYC_POLICY_CHANGE_THRESHOLD", 0.1),
        policy_ack_target=_env_float("IYC_POLICY_ACK_TARGET", 1.0),
        policy_ack_latency_scale=_env_float("IYC_POLICY_ACK_LATENCY_SCALE", 0.25),
        policy_ack_latency_cap=_env_float("IYC_POLICY_ACK_LATENCY_CAP", 0.35),
        policy_cpu_load_trigger=_env_float("IYC_POLICY_CPU_LOAD_TRIGGER", 0.8),
        policy_cpu_load_scale=_env_float("IYC_POLICY_CPU_LOAD_SCALE", 0.2),
        policy_cpu_load_cap=_env_float("IYC_POLICY_CPU_LOAD_CAP", 0.2),
        policy_queue_fill_trigger=_env_float("IYC_POLICY_QUEUE_FILL_TRIGGER", 0.8),
        policy_queue_fill_min_scale=_env_float("IYC_POLICY_QUEUE_FILL_MIN_SCALE", 0.25),
        policy_queue_close_threshold=_env_float("IYC_POLICY_QUEUE_CLOSE_THRESHOLD", 0.9),
        policy_cpu_close_threshold=_env_float("IYC_POLICY_CPU_CLOSE_THRESHOLD", 0.95),
        policy_ack_close_multiplier=_env_float("IYC_POLICY_ACK_CLOSE_MULTIPLIER", 3.0),
        simulator_generated_data_value=_env_float("IYC_SIMULATOR_DATA_VALUE", 1.0),
        simulator_generated_criticality_default=_env_float("IYC_SIMULATOR_CRITICALITY_DEFAULT", 0.1),
        simulator_generated_criticality_critical=_env_float("IYC_SIMULATOR_CRITICALITY_CRITICAL", 1.0),
    )
