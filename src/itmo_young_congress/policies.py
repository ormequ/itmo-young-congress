from __future__ import annotations

from dataclasses import dataclass

from itmo_young_congress.domain import EpochState, PolicyDecision, TelemetrySample


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


@dataclass
class FixedEpochPolicy:
    epoch_size: int
    min_epoch: int
    max_epoch: int

    @property
    def fixed_target(self) -> int:
        return _clamp(self.epoch_size, self.min_epoch, self.max_epoch)

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        del telemetry
        target = self.fixed_target
        return PolicyDecision(next_target=target, should_close=state.event_count >= target)


@dataclass
class AdaptiveEpochPolicy:
    target_window: float
    min_epoch: int
    max_epoch: int
    ema_alpha: float
    change_threshold: float
    ack_target: float
    use_arrival_rate: bool = True
    use_ack_latency: bool = True
    use_cpu_load: bool = True
    use_queue_fill: bool = True
    use_early_close: bool = True
    criticality_threshold: float = 0.9

    def evaluate(self, state: EpochState, telemetry: TelemetrySample) -> PolicyDecision:
        base_rate = telemetry.arrival_rate if self.use_arrival_rate else max(1.0, state.current_target / self.target_window)
        base_target = max(1, round(base_rate * self.target_window))
        scaled_target = float(base_target)

        if self.use_ack_latency and telemetry.ack_latency > self.ack_target:
            scaled_target *= 1.0 + min((telemetry.ack_latency / self.ack_target - 1.0) * 0.25, 0.35)
        if self.use_cpu_load and telemetry.cpu_load > 0.8:
            scaled_target *= 1.0 + min((telemetry.cpu_load - 0.8) / 0.2, 0.2)
        if self.use_queue_fill and telemetry.queue_fill > 0.8:
            scaled_target *= max(0.25, 1.0 - telemetry.queue_fill)

        candidate = _clamp(round(scaled_target), self.min_epoch, self.max_epoch)
        delta_ratio = abs(candidate - state.current_target) / max(1, state.current_target)
        next_target = candidate if delta_ratio > self.change_threshold else state.current_target

        should_close = (
            (self.use_early_close and telemetry.critical_event)
            or (self.use_early_close and telemetry.anomaly_detected)
            or (self.use_early_close and telemetry.data_criticality >= self.criticality_threshold)
            or (self.use_early_close and telemetry.queue_fill >= 0.9)
            or (self.use_early_close and telemetry.cpu_load >= 0.95)
            or (self.use_early_close and telemetry.ack_latency >= 3 * self.ack_target)
            or state.event_count >= next_target
        )
        return PolicyDecision(next_target=next_target, should_close=should_close)
