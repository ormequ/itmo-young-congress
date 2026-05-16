from __future__ import annotations

from dataclasses import asdict
import json
import random
import statistics
import time
from typing import List, Optional, Sequence

from crypto import ECDSARootSigner, build_merkle_tree, create_ecdsa_signer, sign_root_ecdsa
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
                    anchor_ack_latency=segment.anchor_ack_latency,
                    cpu_load=segment.cpu_load,
                    input_queue_fill=segment.input_queue_fill,
                    critical=critical,
                    arrival_rate=segment.rate,
                    data_value=segment.rate * settings.simulator_generated_data_value,
                    criticality_level=(
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


def _anomaly_score(value: float, history: Sequence[float]) -> float:
    if len(history) < 2:
        return 0.0
    mean, std = _mean_std(history)
    if std < 1e-9:
        return 1_000_000.0 if abs(value - mean) > 0.0 else 0.0
    return abs(value - mean) / std


def _policy_name(policy: object) -> str:
    name = policy.__class__.__name__
    return name.replace("EpochPolicy", "").replace("Policy", "").lower()


def run_simulation(
    scenario: ScenarioConfig,
    policy: object,
    seed: int = 1,
    events: Optional[Sequence[Event]] = None,
    signer: Optional[ECDSARootSigner] = None,
) -> SimulationResult:
    result, _ = _run_simulation_internal(
        scenario,
        policy,
        seed=seed,
        events=events,
        collect_trace=False,
        signer=signer,
    )
    return result


def run_simulation_trace(
    scenario: ScenarioConfig,
    policy: object,
    seed: int = 1,
    events: Optional[Sequence[Event]] = None,
    signer: Optional[ECDSARootSigner] = None,
) -> list[dict]:
    _, trace = _run_simulation_internal(
        scenario,
        policy,
        seed=seed,
        events=events,
        collect_trace=True,
        signer=signer,
    )
    return trace


def _run_simulation_internal(
    scenario: ScenarioConfig,
    policy: object,
    seed: int = 1,
    events: Optional[Sequence[Event]] = None,
    collect_trace: bool = False,
    signer: Optional[ECDSARootSigner] = None,
) -> tuple[SimulationResult, list[dict]]:
    event_stream = list(events) if events is not None else generate_events(scenario, seed)
    root_signer = signer or create_ecdsa_signer()
    epoch_events: List[Event] = []
    commits: List[CommitRecord] = []
    commit_latencies: List[float] = []
    queue_depths: List[int] = []
    signature_times: List[float] = []
    anchor_ack_history: List[float] = []
    cpu_history: List[float] = []
    input_queue_history: List[float] = []
    data_history: List[float] = []
    trace: List[dict] = []

    current_target = getattr(policy, "fixed_target", max(1, round(scenario.target_commit_latency)))

    def close_epoch(commit_reference_time: float) -> None:
        nonlocal epoch_events
        if not epoch_events:
            return

        tree = build_merkle_tree([event.payload for event in epoch_events])
        signature_started = time.perf_counter()
        root_signature = sign_root_ecdsa(root_signer.private_key, tree.root)
        measured_signature_time = time.perf_counter() - signature_started
        effective_signature_time = max(measured_signature_time, 0.05)
        signature_times.append(effective_signature_time)
        commit_time = commit_reference_time + max(event.anchor_ack_latency for event in epoch_events) + effective_signature_time
        proof_sizes = tuple(len(tree.proof_for(index)) for index, _ in enumerate(epoch_events))
        for event in epoch_events:
            commit_latencies.append(commit_time - event.arrival_time)
        commits.append(
            CommitRecord(
                root=tree.root,
                root_signature=root_signature,
                event_ids=tuple(event.event_id for event in epoch_events),
                commit_time=commit_time,
                signature_time=effective_signature_time,
                proof_sizes=proof_sizes,
            )
        )
        epoch_events = []

    for event in event_stream:
        epoch_events.append(event)
        queue_depths.append(len(epoch_events))
        rolling_input_queue_fill = max(event.input_queue_fill, len(epoch_events) / max(1, scenario.queue_capacity))
        anchor_ack_window = anchor_ack_history[-scenario.telemetry_window_size :]
        cpu_window = cpu_history[-scenario.telemetry_window_size :]
        input_queue_window = input_queue_history[-scenario.telemetry_window_size :]
        data_window = data_history[-scenario.telemetry_window_size :]
        rolling_anchor_ack_mean, rolling_anchor_ack_std = _mean_std(anchor_ack_window)
        rolling_cpu_mean, rolling_cpu_std = _mean_std(cpu_window)
        rolling_input_queue_mean, rolling_input_queue_std = _mean_std(input_queue_window)
        rolling_data_mean, rolling_data_std = _mean_std(data_window)

        telemetry = TelemetrySample(
            arrival_rate=event.arrival_rate,
            anchor_ack_latency=event.anchor_ack_latency,
            cpu_load=event.cpu_load,
            input_queue_fill=rolling_input_queue_fill,
            critical_event=event.critical,
            rolling_anchor_ack_mean=rolling_anchor_ack_mean,
            rolling_anchor_ack_std=rolling_anchor_ack_std,
            rolling_cpu_mean=rolling_cpu_mean,
            rolling_cpu_std=rolling_cpu_std,
            rolling_input_queue_mean=rolling_input_queue_mean,
            rolling_input_queue_std=rolling_input_queue_std,
            rolling_data_mean=rolling_data_mean,
            rolling_data_std=rolling_data_std,
            anomaly_score=max(
                _anomaly_score(event.anchor_ack_latency, anchor_ack_window),
                _anomaly_score(event.cpu_load, cpu_window),
                _anomaly_score(rolling_input_queue_fill, input_queue_window),
                _anomaly_score(event.data_value, data_window),
            ),
            criticality_level=event.criticality_level,
        )
        state = EpochState(epoch_event_count=len(epoch_events), current_target=current_target)
        decision = policy.evaluate(state, telemetry)
        if collect_trace:
            trace.append(
                {
                    "time": event.arrival_time,
                    "policy": _policy_name(policy),
                    "arrival_rate": event.arrival_rate,
                    "anchor_ack_latency": event.anchor_ack_latency,
                    "cpu_load": event.cpu_load,
                    "input_queue_fill": rolling_input_queue_fill,
                    "epoch_event_count": len(epoch_events),
                    "current_target": current_target,
                    "next_target": decision.next_target,
                    "anomaly_score": telemetry.anomaly_score,
                    "should_close": decision.should_close,
                }
            )
        current_target = decision.next_target
        if decision.should_close:
            close_epoch(event.arrival_time)

        anchor_ack_history.append(event.anchor_ack_latency)
        cpu_history.append(event.cpu_load)
        input_queue_history.append(rolling_input_queue_fill)
        data_history.append(event.data_value)

    if epoch_events:
        tail_time = event_stream[-1].arrival_time if event_stream else scenario.duration
        close_epoch(tail_time)

    avg_commit_latency = statistics.mean(commit_latencies) if commit_latencies else 0.0
    avg_proof_hashes = (
        statistics.mean(size for commit in commits for size in commit.proof_sizes) if commits else 0.0
    )
    total_signature_time = sum(signature_times)
    avg_signature_time = statistics.mean(signature_times) if signature_times else 0.0
    metrics = RunMetrics(
        avg_commit_latency=avg_commit_latency,
        p95_commit_latency=_p95(commit_latencies),
        max_commit_latency=max(commit_latencies) if commit_latencies else 0.0,
        commit_frequency=len(commits) / max(scenario.duration, 1e-9),
        max_queue_depth=max(queue_depths) if queue_depths else 0,
        p95_queue_depth=_p95([float(depth) for depth in queue_depths]),
        throughput=len(event_stream) / max(scenario.duration, 1e-9),
        queue_over_capacity_count=max(0, len([depth for depth in queue_depths if depth > scenario.queue_capacity])),
        avg_proof_hashes=avg_proof_hashes,
        avg_proof_bytes=avg_proof_hashes * 32.0,
        signature_count=len(signature_times),
        avg_signature_time=avg_signature_time,
        total_signature_time=total_signature_time,
        signature_time_per_second=total_signature_time / max(scenario.duration, 1e-9),
    )
    return (
        SimulationResult(
            scenario=scenario.name,
            policy=_policy_name(policy),
            metrics=metrics,
            commits=tuple(commits),
        ),
        trace,
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
                "root_signature": commit.root_signature.hex(),
                "signature_time": commit.signature_time,
                "proof_sizes": commit.proof_sizes,
            }
            for commit in result.commits
        ],
    }
    return json.dumps(payload, indent=2)
