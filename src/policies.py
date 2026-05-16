from __future__ import annotations

from dataclasses import dataclass, field
import math

from domain import EpochState, PolicyDecision, TelemetrySample
from settings import load_settings


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


@dataclass
class FixedEpochPolicy:
    epoch_size: int

    @property
    def fixed_target(self) -> int:
        return self.epoch_size

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        del telemetry
        target = self.fixed_target
        return PolicyDecision(next_target=target, should_close=state.epoch_event_count >= target)


@dataclass
class AdaptiveEpochPolicy:
    target_commit_latency: float
    min_epoch_events: int
    max_epoch_events: float
    min_epoch_duration_seconds: float
    max_epoch_duration_seconds: float
    change_threshold: float
    anchor_ack_target: float
    use_arrival_rate: bool = True
    use_anchor_ack_latency: bool = True
    use_cpu_load: bool = True
    use_input_queue_fill: bool = True
    use_early_close: bool = True
    criticality_threshold: float = field(default_factory=lambda: load_settings().criticality_threshold)
    anomaly_score_threshold: float = field(default_factory=lambda: load_settings().anomaly_score_threshold)

    def _bounds_for_rate(self, arrival_rate: float) -> tuple[int, int]:
        lower = self.min_epoch_events
        upper = math.inf if math.isinf(self.max_epoch_events) else int(self.max_epoch_events)
        if self.min_epoch_duration_seconds > 0.0:
            lower = max(lower, math.ceil(arrival_rate * self.min_epoch_duration_seconds))
        if math.isfinite(self.max_epoch_duration_seconds):
            upper = min(upper, math.floor(arrival_rate * self.max_epoch_duration_seconds))
        if upper < lower:
            upper = lower
        return lower, upper

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        base_rate = telemetry.arrival_rate if self.use_arrival_rate else max(1.0, state.current_target / self.target_commit_latency)
        base_target = max(1, round(base_rate * self.target_commit_latency))
        scaled_target = float(base_target)
        settings = load_settings()

        if self.use_anchor_ack_latency and telemetry.anchor_ack_latency > self.anchor_ack_target:
            scaled_target *= 1.0 + min(
                (telemetry.anchor_ack_latency / self.anchor_ack_target - 1.0) * settings.policy_anchor_ack_latency_scale,
                settings.policy_anchor_ack_latency_cap,
            )
        if self.use_cpu_load and telemetry.cpu_load > settings.policy_cpu_load_trigger:
            scaled_target *= 1.0 + min(
                (telemetry.cpu_load - settings.policy_cpu_load_trigger) / settings.policy_cpu_load_scale,
                settings.policy_cpu_load_cap,
            )
        if self.use_input_queue_fill and telemetry.input_queue_fill > settings.policy_input_queue_fill_trigger:
            scaled_target *= max(settings.policy_input_queue_fill_min_scale, 1.0 - telemetry.input_queue_fill)

        lower, upper = self._bounds_for_rate(base_rate)
        candidate = max(round(scaled_target), lower) if math.isinf(upper) else _clamp(round(scaled_target), lower, upper)
        delta_ratio = abs(candidate - state.current_target) / max(1, state.current_target)
        next_target = candidate if delta_ratio > self.change_threshold else state.current_target

        should_close = (
            (self.use_early_close and telemetry.critical_event)
            or (self.use_early_close and telemetry.anomaly_score >= self.anomaly_score_threshold)
            or (self.use_early_close and telemetry.criticality_level >= self.criticality_threshold)
            or (self.use_early_close and telemetry.input_queue_fill >= settings.policy_input_queue_close_threshold)
            or (self.use_early_close and telemetry.cpu_load >= settings.policy_cpu_close_threshold)
            or state.epoch_event_count >= next_target
        )
        return PolicyDecision(next_target=next_target, should_close=should_close)
