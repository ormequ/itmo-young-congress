from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TelemetrySample:
    arrival_rate: float
    ack_latency: float = 0.0
    cpu_load: float = 0.0
    queue_fill: float = 0.0
    critical_event: bool = False
    rolling_ack_mean: float = 0.0
    rolling_ack_std: float = 0.0
    rolling_cpu_mean: float = 0.0
    rolling_cpu_std: float = 0.0
    rolling_queue_mean: float = 0.0
    rolling_queue_std: float = 0.0
    rolling_data_mean: float = 0.0
    rolling_data_std: float = 0.0
    anomaly_detected: bool = False
    data_criticality: float = 0.0


@dataclass(frozen=True)
class EpochState:
    event_count: int
    current_target: int


@dataclass(frozen=True)
class PolicyDecision:
    next_target: int
    should_close: bool


@dataclass(frozen=True)
class ArrivalSegment:
    duration: float
    rate: float
    ack_latency: float = 1.0
    cpu_load: float = 0.2
    queue_fill: float = 0.1
    critical_every: int = 0


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    duration: float
    queue_capacity: int
    target_window: float
    segments: Tuple[ArrivalSegment, ...]
    telemetry_window_size: int = 5
    anomaly_sigma_threshold: float = 3.0
    criticality_threshold: float = 0.9


@dataclass(frozen=True)
class Event:
    event_id: int
    arrival_time: float
    payload: bytes
    ack_latency: float
    cpu_load: float
    queue_fill: float
    critical: bool
    arrival_rate: float
    data_value: float = 0.0
    data_criticality: float = 0.0

    def with_arrival(self, arrival_time: float) -> "Event":
        return Event(
            event_id=self.event_id,
            arrival_time=arrival_time,
            payload=self.payload,
            ack_latency=self.ack_latency,
            cpu_load=self.cpu_load,
            queue_fill=self.queue_fill,
            critical=self.critical,
            arrival_rate=self.arrival_rate,
            data_value=self.data_value,
            data_criticality=self.data_criticality,
        )


@dataclass(frozen=True)
class CommitRecord:
    root: bytes
    event_ids: Tuple[int, ...]
    commit_time: float
    proof_sizes: Tuple[int, ...]


@dataclass(frozen=True)
class RunMetrics:
    avg_vulnerability_window: float
    p95_vulnerability_window: float
    max_vulnerability_window: float
    commit_frequency: float
    max_queue_depth: int
    p95_queue_depth: float
    throughput: float
    lost_events: int
    avg_proof_hashes: float
    avg_proof_bytes: float


@dataclass(frozen=True)
class SimulationResult:
    scenario: str
    policy: str
    metrics: RunMetrics
    commits: Tuple[CommitRecord, ...]
