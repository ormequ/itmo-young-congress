import unittest

from domain import ArrivalSegment, Event, ScenarioConfig
from crypto import create_ecdsa_signer, verify_root_signature
from policies import AdaptiveEpochPolicy, FixedEpochPolicy
from simulator import generate_events, run_simulation, run_simulation_trace


class GeneratorTests(unittest.TestCase):
    def test_event_generation_is_reproducible_for_seed(self) -> None:
        scenario = ScenarioConfig(
            name="steady",
            duration=5.0,
            queue_capacity=20,
            target_commit_latency=2.0,
            segments=(ArrivalSegment(duration=5.0, rate=4.0),),
        )

        events_a = generate_events(scenario, seed=7)
        events_b = generate_events(scenario, seed=7)

        self.assertEqual(events_a, events_b)


class SimulatorTests(unittest.TestCase):
    def test_trace_records_target_updates_and_epoch_closures(self) -> None:
        scenario = ScenarioConfig(
            name="burst",
            duration=4.0,
            queue_capacity=16,
            target_commit_latency=2.0,
            segments=(
                ArrivalSegment(duration=2.0, rate=3.0, anchor_ack_latency=1.0),
                ArrivalSegment(duration=2.0, rate=8.0, anchor_ack_latency=1.0),
            ),
        )
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=0,
            max_epoch_events=float("inf"),
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )

        trace = run_simulation_trace(scenario, adaptive, seed=3)

        self.assertGreaterEqual(len(trace), 2)
        self.assertTrue(any(point["should_close"] for point in trace))
        self.assertGreater(len({point["next_target"] for point in trace}), 1)

    def test_fixed_policy_uses_anchor_ack_latency_as_commit_latency(self) -> None:
        scenario = ScenarioConfig(
            name="steady",
            duration=1.0,
            queue_capacity=20,
            target_commit_latency=1.0,
            segments=(ArrivalSegment(duration=1.0, rate=3.0, anchor_ack_latency=2.0),),
        )
        events = [
            Event(1, 0.0, b"a", 2.0, 0.2, 0.1, False, 3.0),
            Event(2, 0.2, b"b", 2.0, 0.2, 0.1, False, 3.0),
        ]
        policy = FixedEpochPolicy(epoch_size=2)

        result = run_simulation(scenario, policy, events=events)

        self.assertAlmostEqual(result.metrics.avg_commit_latency, 2.1, places=1)
        self.assertAlmostEqual(result.metrics.max_commit_latency, 2.2, places=1)

    def test_closed_epoch_contains_root_signature_metrics(self) -> None:
        scenario = ScenarioConfig(
            name="signed-root",
            duration=1.0,
            queue_capacity=20,
            target_commit_latency=1.0,
            segments=(ArrivalSegment(duration=1.0, rate=3.0, anchor_ack_latency=1.0),),
        )
        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 3.0),
            Event(2, 0.2, b"b", 1.0, 0.2, 0.1, False, 3.0),
        ]
        signer = create_ecdsa_signer()

        result = run_simulation(scenario, FixedEpochPolicy(epoch_size=2), events=events, signer=signer)

        self.assertEqual(result.metrics.signature_count, 1)
        self.assertGreater(result.metrics.avg_signature_time, 0.0)
        self.assertGreater(result.metrics.total_signature_time, 0.0)
        self.assertTrue(
            verify_root_signature(
                signer.public_key,
                result.commits[0].root,
                result.commits[0].root_signature,
            )
        )

    def test_memory_budget_closes_epoch_by_payload_bytes(self) -> None:
        scenario = ScenarioConfig(
            name="memory-budget",
            duration=2.0,
            queue_capacity=20,
            target_commit_latency=10.0,
            segments=(ArrivalSegment(duration=2.0, rate=5.0, anchor_ack_latency=1.0),),
        )
        events = [
            Event(1, 0.0, b"a" * 600, 1.0, 0.2, 0.1, False, 5.0),
            Event(2, 0.1, b"b" * 500, 1.0, 0.2, 0.1, False, 5.0),
            Event(3, 0.2, b"c" * 100, 1.0, 0.2, 0.1, False, 5.0),
        ]
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=10.0,
            min_epoch_events=1,
            max_epoch_events=100,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            epoch_buffer_budget_bytes=1_000,
        )

        result = run_simulation(scenario, adaptive, events=events)

        self.assertEqual([commit.event_ids for commit in result.commits], [(1, 2), (3,)])
        self.assertEqual(result.metrics.max_epoch_payload_bytes, 1_100)
        self.assertEqual(result.metrics.p95_epoch_payload_bytes, 1_100)

    def test_adaptive_policy_closes_early_for_critical_event(self) -> None:
        scenario = ScenarioConfig(
            name="critical",
            duration=3.0,
            queue_capacity=20,
            target_commit_latency=2.0,
            segments=(ArrivalSegment(duration=3.0, rate=5.0, anchor_ack_latency=1.0, critical_every=3),),
        )
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=12,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        fixed = FixedEpochPolicy(epoch_size=10)

        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 5.0),
            Event(2, 0.2, b"b", 1.0, 0.2, 0.1, False, 5.0),
            Event(3, 0.4, b"c", 1.0, 0.2, 0.1, True, 5.0),
            Event(4, 1.2, b"d", 1.0, 0.2, 0.1, False, 5.0),
        ]

        adaptive_result = run_simulation(scenario, adaptive, events=events)

        self.assertGreaterEqual(len(adaptive_result.commits), 2)
        self.assertLessEqual(adaptive_result.metrics.max_commit_latency, 2.0)

    def test_adaptive_policy_closes_on_anomalous_storage_spike(self) -> None:
        scenario = ScenarioConfig(
            name="anomaly-spike",
            duration=5.0,
            queue_capacity=20,
            target_commit_latency=2.0,
            telemetry_window_size=3,
            anomaly_score_threshold=2.5,
            segments=(ArrivalSegment(duration=5.0, rate=5.0, anchor_ack_latency=1.0),),
        )
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=12,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        fixed = FixedEpochPolicy(epoch_size=10)
        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1),
            Event(2, 0.2, b"b", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1),
            Event(3, 0.4, b"c", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1),
            Event(4, 0.6, b"d", 4.5, 0.2, 0.1, False, 5.0, 5.0, 0.1),
            Event(5, 0.8, b"e", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1),
        ]

        adaptive_result = run_simulation(scenario, adaptive, events=events)

        self.assertGreaterEqual(len(adaptive_result.commits), 2)
        self.assertLessEqual(adaptive_result.metrics.max_commit_latency, 5.0)

    def test_trace_and_metrics_include_anchor_backpressure(self) -> None:
        scenario = ScenarioConfig(
            name="anchor-backpressure",
            duration=2.0,
            queue_capacity=20,
            target_commit_latency=0.2,
            max_pending_anchors=1,
            segments=(ArrivalSegment(duration=2.0, rate=10.0, anchor_ack_latency=2.0),),
        )
        events = [
            Event(1, 0.0, b"a", 2.0, 0.2, 0.1, False, 10.0),
            Event(2, 0.1, b"b", 2.0, 0.2, 0.1, False, 10.0),
            Event(3, 0.2, b"c", 2.0, 0.2, 0.1, False, 10.0),
            Event(4, 0.3, b"d", 2.0, 0.2, 0.1, False, 10.0),
        ]
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=0.2,
            min_epoch_events=1,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            max_pending_anchors=1,
        )

        trace = run_simulation_trace(scenario, adaptive, events=events)
        result = run_simulation(scenario, adaptive, events=events)

        self.assertTrue(any(point["pending_anchor_count"] > 0 for point in trace))
        self.assertGreater(result.metrics.max_pending_anchor_count, 0)

    def test_source_priority_is_recorded_and_affects_epoch_closure(self) -> None:
        scenario = ScenarioConfig(
            name="priority",
            duration=2.0,
            queue_capacity=20,
            target_commit_latency=10.0,
            anomaly_score_threshold=3.0,
            criticality_threshold=0.9,
            segments=(ArrivalSegment(duration=2.0, rate=5.0, anchor_ack_latency=1.0, source_priority=2.0),),
        )
        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.4, source_priority=1.0),
            Event(2, 0.1, b"b", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.5, source_priority=2.0),
            Event(3, 0.2, b"c", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1, source_priority=1.0),
        ]
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=10.0,
            min_epoch_events=1,
            max_epoch_events=100,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            criticality_threshold=0.9,
        )

        trace = run_simulation_trace(scenario, adaptive, events=events)
        result = run_simulation(scenario, adaptive, events=events)

        self.assertEqual(trace[1]["source_priority"], 2.0)
        self.assertEqual(trace[1]["effective_criticality_level"], 1.0)
        self.assertTrue(trace[1]["should_close"])
        self.assertEqual(result.commits[0].event_ids, (1, 2))

    def test_source_priority_is_clamped_in_trace_and_closure_logic(self) -> None:
        scenario = ScenarioConfig(
            name="priority-clamp",
            duration=2.0,
            queue_capacity=20,
            target_commit_latency=10.0,
            anomaly_score_threshold=3.0,
            segments=(ArrivalSegment(duration=2.0, rate=5.0, anchor_ack_latency=1.0),),
        )
        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 5.0, 10.0, 0.1, source_priority=10.0),
            Event(2, 0.1, b"b", 1.0, 0.2, 0.1, False, 5.0, 1.0, 0.1, source_priority=1.0),
        ]
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=10.0,
            min_epoch_events=1,
            max_epoch_events=100,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            anomaly_score_threshold=3.0,
        )

        trace = run_simulation_trace(scenario, adaptive, events=events)

        self.assertEqual(trace[0]["source_priority"], 2.0)
        self.assertFalse(trace[0]["should_close"])

    def test_max_epoch_duration_closes_epoch_by_elapsed_time(self) -> None:
        scenario = ScenarioConfig(
            name="duration-limit",
            duration=3.0,
            queue_capacity=20,
            target_commit_latency=10.0,
            segments=(ArrivalSegment(duration=3.0, rate=10.0, anchor_ack_latency=1.0),),
        )
        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 10.0),
            Event(2, 0.4, b"b", 1.0, 0.2, 0.1, False, 10.0),
            Event(3, 1.1, b"c", 1.0, 0.2, 0.1, False, 10.0),
            Event(4, 1.2, b"d", 1.0, 0.2, 0.1, False, 10.0),
        ]
        adaptive = AdaptiveEpochPolicy(
            target_commit_latency=10.0,
            min_epoch_events=1,
            max_epoch_events=100,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=1.0,
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )

        trace = run_simulation_trace(scenario, adaptive, events=events)
        result = run_simulation(scenario, adaptive, events=events)

        self.assertTrue(trace[2]["max_epoch_duration_reached"])
        self.assertEqual(result.commits[0].event_ids, (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
