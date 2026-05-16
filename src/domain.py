from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from settings import load_settings


def clamp_source_priority(value: float) -> float:
    settings = load_settings()
    return max(settings.source_priority_min, min(value, settings.source_priority_max))


@dataclass(frozen=True)
class TelemetrySample:
    arrival_rate: float
    anchor_ack_latency: float = 0.0
    cpu_load: float = 0.0
    input_queue_fill: float = 0.0
    critical_event: bool = False
    rolling_anchor_ack_mean: float = 0.0
    rolling_anchor_ack_std: float = 0.0
    rolling_cpu_mean: float = 0.0
    rolling_cpu_std: float = 0.0
    rolling_input_queue_mean: float = 0.0
    rolling_input_queue_std: float = 0.0
    rolling_data_mean: float = 0.0
    rolling_data_std: float = 0.0
    anomaly_score: float = 0.0
    criticality_level: float = 0.0
    source_priority: float = 1.0
    effective_criticality_level: float = 0.0
    epoch_payload_bytes: int = 0
    memory_pressure: float = 0.0
    pending_anchor_count: int = 0


@dataclass(frozen=True)
class EpochState:
    epoch_event_count: int
    current_target: int
    epoch_payload_bytes: int = 0


@dataclass(frozen=True)
class PolicyDecision:
    next_target: int
    should_close: bool


@dataclass(frozen=True)
class ArrivalSegment:
    duration: float
    rate: float
    anchor_ack_latency: float = field(default_factory=lambda: load_settings().segment_anchor_ack_latency)
    cpu_load: float = field(default_factory=lambda: load_settings().segment_cpu_load)
    input_queue_fill: float = field(default_factory=lambda: load_settings().segment_input_queue_fill)
    critical_every: int = 0
    source_priority: float = field(default_factory=lambda: load_settings().segment_source_priority)


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    duration: float
    queue_capacity: int
    target_commit_latency: float
    segments: Tuple[ArrivalSegment, ...]
    telemetry_window_size: int = field(default_factory=lambda: load_settings().telemetry_window_size)
    anomaly_score_threshold: float = field(default_factory=lambda: load_settings().anomaly_score_threshold)
    criticality_threshold: float = field(default_factory=lambda: load_settings().criticality_threshold)
    epoch_buffer_budget_bytes: float = field(default_factory=lambda: load_settings().epoch_buffer_budget_bytes)
    max_pending_anchors: float = field(default_factory=lambda: load_settings().max_pending_anchors)


@dataclass(frozen=True)
class Event:
    event_id: int
    arrival_time: float
    payload: bytes
    anchor_ack_latency: float
    cpu_load: float
    input_queue_fill: float
    critical: bool
    arrival_rate: float
    data_value: float = 0.0
    criticality_level: float = 0.0
    payload_size_bytes: int = 0
    source_priority: float = 1.0

    def with_arrival(self, arrival_time: float) -> "Event":
        return Event(
            event_id=self.event_id,
            arrival_time=arrival_time,
            payload=self.payload,
            anchor_ack_latency=self.anchor_ack_latency,
            cpu_load=self.cpu_load,
            input_queue_fill=self.input_queue_fill,
            critical=self.critical,
            arrival_rate=self.arrival_rate,
            data_value=self.data_value,
            criticality_level=self.criticality_level,
            payload_size_bytes=self.payload_size_bytes,
            source_priority=self.source_priority,
        )


@dataclass(frozen=True)
class CommitRecord:
    root: bytes
    root_signature: bytes
    event_ids: Tuple[int, ...]
    commit_time: float
    signature_time: float
    proof_sizes: Tuple[int, ...]


@dataclass(frozen=True)
class RunMetrics:
    avg_commit_latency: float
    p95_commit_latency: float
    max_commit_latency: float
    commit_frequency: float
    max_queue_depth: int
    p95_queue_depth: float
    throughput: float
    queue_over_capacity_count: int
    max_epoch_payload_bytes: int
    p95_epoch_payload_bytes: float
    max_pending_anchor_count: int
    p95_pending_anchor_count: float
    avg_proof_hashes: float
    avg_proof_bytes: float
    signature_count: int
    avg_signature_time: float
    total_signature_time: float
    signature_time_per_second: float


@dataclass(frozen=True)
class SimulationResult:
    scenario: str
    policy: str
    metrics: RunMetrics
    commits: Tuple[CommitRecord, ...]
