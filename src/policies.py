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
    min_epoch_events: int
    max_epoch_events: float
    min_window_seconds: float
    max_window_seconds: float

    @property
    def fixed_target(self) -> int:
        return self.target_for_rate(0.0)

    def _bounds_for_rate(self, arrival_rate: float) -> tuple[int, int]:
        lower = self.min_epoch_events
        upper = math.inf if math.isinf(self.max_epoch_events) else int(self.max_epoch_events)
        if self.min_window_seconds > 0.0:
            lower = max(lower, math.ceil(arrival_rate * self.min_window_seconds))
        if math.isfinite(self.max_window_seconds):
            upper = min(upper, math.floor(arrival_rate * self.max_window_seconds))
        if upper < lower:
            upper = lower
        return lower, upper

    def target_for_rate(self, arrival_rate: float) -> int:
        lower, upper = self._bounds_for_rate(arrival_rate)
        if math.isinf(upper):
            return max(self.epoch_size, lower)
        return _clamp(self.epoch_size, lower, upper)

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        target = self.target_for_rate(telemetry.arrival_rate)
        return PolicyDecision(next_target=target, should_close=state.event_count >= target)


@dataclass
class AdaptiveEpochPolicy:
    target_window: float
    min_epoch_events: int
    max_epoch_events: float
    min_window_seconds: float
    max_window_seconds: float
    change_threshold: float
    ack_target: float
    use_arrival_rate: bool = True
    use_ack_latency: bool = True
    use_cpu_load: bool = True
    use_queue_fill: bool = True
    use_early_close: bool = True
    criticality_threshold: float = field(default_factory=lambda: load_settings().criticality_threshold)

    def _bounds_for_rate(self, arrival_rate: float) -> tuple[int, int]:
        lower = self.min_epoch_events
        upper = math.inf if math.isinf(self.max_epoch_events) else int(self.max_epoch_events)
        if self.min_window_seconds > 0.0:
            lower = max(lower, math.ceil(arrival_rate * self.min_window_seconds))
        if math.isfinite(self.max_window_seconds):
            upper = min(upper, math.floor(arrival_rate * self.max_window_seconds))
        if upper < lower:
            upper = lower
        return lower, upper

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        base_rate = telemetry.arrival_rate if self.use_arrival_rate else max(1.0, state.current_target / self.target_window)
        base_target = max(1, round(base_rate * self.target_window))
        scaled_target = float(base_target)
        settings = load_settings()

        if self.use_ack_latency and telemetry.ack_latency > self.ack_target:
            scaled_target *= 1.0 + min(
                (telemetry.ack_latency / self.ack_target - 1.0) * settings.policy_ack_latency_scale,
                settings.policy_ack_latency_cap,
            )
        if self.use_cpu_load and telemetry.cpu_load > settings.policy_cpu_load_trigger:
            scaled_target *= 1.0 + min(
                (telemetry.cpu_load - settings.policy_cpu_load_trigger) / settings.policy_cpu_load_scale,
                settings.policy_cpu_load_cap,
            )
        if self.use_queue_fill and telemetry.queue_fill > settings.policy_queue_fill_trigger:
            scaled_target *= max(settings.policy_queue_fill_min_scale, 1.0 - telemetry.queue_fill)

        lower, upper = self._bounds_for_rate(base_rate)
        candidate = max(round(scaled_target), lower) if math.isinf(upper) else _clamp(round(scaled_target), lower, upper)
        delta_ratio = abs(candidate - state.current_target) / max(1, state.current_target)
        next_target = candidate if delta_ratio > self.change_threshold else state.current_target

        should_close = (
            (self.use_early_close and telemetry.critical_event)
            or (self.use_early_close and telemetry.anomaly_detected)
            or (self.use_early_close and telemetry.data_criticality >= self.criticality_threshold)
            or (self.use_early_close and telemetry.queue_fill >= settings.policy_queue_close_threshold)
            or (self.use_early_close and telemetry.cpu_load >= settings.policy_cpu_close_threshold)
            or (self.use_early_close and telemetry.ack_latency >= settings.policy_ack_close_multiplier * self.ack_target)
            or state.event_count >= next_target
        )
        return PolicyDecision(next_target=next_target, should_close=should_close)
