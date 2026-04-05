from __future__ import annotations

from dataclasses import asdict
import json
import random
import statistics
from typing import List, Optional, Sequence

from crypto import build_merkle_tree
from domain import (
    CommitRecord,
    EpochState,
    Event,
    RunMetrics,
    ScenarioConfig,
    SimulationResult,
    TelemetrySample,
)
from settings import load_settings


def generate_events(scenario: ScenarioConfig, seed: int) -> List[Event]:
    settings = load_settings()
    rng = random.Random(seed)
    events: List[Event] = []
    current_time = 0.0
    event_id = 1

    for segment in scenario.segments:
        segment_end = current_time + segment.duration
        while current_time < segment_end and segment.rate > 0:
            current_time += rng.expovariate(segment.rate)
            if current_time > segment_end or current_time > scenario.duration:
                break
            critical = segment.critical_every > 0 and event_id % segment.critical_every == 0
            payload = f"{scenario.name}:{event_id}:{current_time:.6f}".encode("utf-8")
            events.append(
                Event(
                    event_id=event_id,
                    arrival_time=current_time,
                    payload=payload,
                    ack_latency=segment.ack_latency,
                    cpu_load=segment.cpu_load,
                    queue_fill=segment.queue_fill,
                    critical=critical,
                    arrival_rate=segment.rate,
                    data_value=segment.rate * settings.simulator_generated_data_value,
                    data_criticality=(
                        settings.simulator_generated_criticality_critical
                        if critical
                        else settings.simulator_generated_criticality_default
                    ),
                )
            )
            event_id += 1
        current_time = segment_end
        if current_time >= scenario.duration:
            break

    return events


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = float(statistics.mean(values))
    if len(values) == 1:
        return mean, 0.0
    return mean, float(statistics.pstdev(values))


def _is_anomalous(value: float, history: Sequence[float], sigma_threshold: float) -> bool:
    if len(history) < 2:
        return False
    mean, std = _mean_std(history)
    if std < 1e-9:
        return abs(value - mean) > 0.0
    return abs(value - mean) > sigma_threshold * std


def _policy_name(policy: object) -> str:
    name = policy.__class__.__name__
    return name.replace("EpochPolicy", "").replace("Policy", "").lower()


def run_simulation(
    scenario: ScenarioConfig,
    policy: object,
    seed: int = 1,
    events: Optional[Sequence[Event]] = None,
) -> SimulationResult:
    event_stream = list(events) if events is not None else generate_events(scenario, seed)
    epoch_events: List[Event] = []
    commits: List[CommitRecord] = []
    vulnerability_windows: List[float] = []
    queue_depths: List[int] = []
    ack_history: List[float] = []
    cpu_history: List[float] = []
    queue_history: List[float] = []
    data_history: List[float] = []

    current_target = getattr(policy, "fixed_target", max(1, round(scenario.target_window)))

    def close_epoch(commit_reference_time: float) -> None:
        nonlocal epoch_events
        if not epoch_events:
            return

        tree = build_merkle_tree([event.payload for event in epoch_events])
        commit_time = commit_reference_time + max(event.ack_latency for event in epoch_events)
        proof_sizes = tuple(len(tree.proof_for(index)) for index, _ in enumerate(epoch_events))
        for event in epoch_events:
            vulnerability_windows.append(commit_time - event.arrival_time)
        commits.append(
            CommitRecord(
                root=tree.root,
                event_ids=tuple(event.event_id for event in epoch_events),
                commit_time=commit_time,
                proof_sizes=proof_sizes,
            )
        )
        epoch_events = []

    for event in event_stream:
        epoch_events.append(event)
        queue_depths.append(len(epoch_events))
        rolling_queue_fill = max(event.queue_fill, len(epoch_events) / max(1, scenario.queue_capacity))
        ack_window = ack_history[-scenario.telemetry_window_size :]
        cpu_window = cpu_history[-scenario.telemetry_window_size :]
        queue_window = queue_history[-scenario.telemetry_window_size :]
        data_window = data_history[-scenario.telemetry_window_size :]
        rolling_ack_mean, rolling_ack_std = _mean_std(ack_window)
        rolling_cpu_mean, rolling_cpu_std = _mean_std(cpu_window)
        rolling_queue_mean, rolling_queue_std = _mean_std(queue_window)
        rolling_data_mean, rolling_data_std = _mean_std(data_window)

        telemetry = TelemetrySample(
            arrival_rate=event.arrival_rate,
            ack_latency=event.ack_latency,
            cpu_load=event.cpu_load,
            queue_fill=rolling_queue_fill,
            critical_event=event.critical,
            rolling_ack_mean=rolling_ack_mean,
            rolling_ack_std=rolling_ack_std,
            rolling_cpu_mean=rolling_cpu_mean,
            rolling_cpu_std=rolling_cpu_std,
            rolling_queue_mean=rolling_queue_mean,
            rolling_queue_std=rolling_queue_std,
            rolling_data_mean=rolling_data_mean,
            rolling_data_std=rolling_data_std,
            anomaly_detected=any(
                (
                    _is_anomalous(event.ack_latency, ack_window, scenario.anomaly_sigma_threshold),
                    _is_anomalous(event.cpu_load, cpu_window, scenario.anomaly_sigma_threshold),
                    _is_anomalous(rolling_queue_fill, queue_window, scenario.anomaly_sigma_threshold),
                    _is_anomalous(event.data_value, data_window, scenario.anomaly_sigma_threshold),
                )
            ),
            data_criticality=event.data_criticality,
        )
        state = EpochState(event_count=len(epoch_events), current_target=current_target)
        decision = policy.evaluate(state, telemetry)
        current_target = decision.next_target
        if decision.should_close:
            close_epoch(event.arrival_time)

        ack_history.append(event.ack_latency)
        cpu_history.append(event.cpu_load)
        queue_history.append(rolling_queue_fill)
        data_history.append(event.data_value)

    if epoch_events:
        tail_time = event_stream[-1].arrival_time if event_stream else scenario.duration
        close_epoch(tail_time)

    avg_window = statistics.mean(vulnerability_windows) if vulnerability_windows else 0.0
    avg_proof_hashes = (
        statistics.mean(size for commit in commits for size in commit.proof_sizes) if commits else 0.0
    )
    metrics = RunMetrics(
        avg_vulnerability_window=avg_window,
        p95_vulnerability_window=_p95(vulnerability_windows),
        max_vulnerability_window=max(vulnerability_windows) if vulnerability_windows else 0.0,
        commit_frequency=len(commits) / max(scenario.duration, 1e-9),
        max_queue_depth=max(queue_depths) if queue_depths else 0,
        p95_queue_depth=_p95([float(depth) for depth in queue_depths]),
        throughput=len(event_stream) / max(scenario.duration, 1e-9),
        lost_events=max(0, len([depth for depth in queue_depths if depth > scenario.queue_capacity])),
        avg_proof_hashes=avg_proof_hashes,
        avg_proof_bytes=avg_proof_hashes * 32.0,
    )
    return SimulationResult(
        scenario=scenario.name,
        policy=_policy_name(policy),
        metrics=metrics,
        commits=tuple(commits),
    )


def simulation_to_json(result: SimulationResult) -> str:
    payload = {
        "scenario": result.scenario,
        "policy": result.policy,
        "metrics": asdict(result.metrics),
        "commits": [
            {
                "event_ids": commit.event_ids,
                "commit_time": commit.commit_time,
                "proof_sizes": commit.proof_sizes,
            }
            for commit in result.commits
        ],
    }
    return json.dumps(payload, indent=2)
