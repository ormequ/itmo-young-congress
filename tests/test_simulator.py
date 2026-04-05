import unittest

from domain import ArrivalSegment, Event, ScenarioConfig
from policies import AdaptiveEpochPolicy, FixedEpochPolicy
from simulator import generate_events, run_simulation


class GeneratorTests(unittest.TestCase):
    def test_event_generation_is_reproducible_for_seed(self) -> None:
        scenario = ScenarioConfig(
            name="steady",
            duration=5.0,
            queue_capacity=20,
            target_window=2.0,
            segments=(ArrivalSegment(duration=5.0, rate=4.0),),
        )

        events_a = generate_events(scenario, seed=7)
        events_b = generate_events(scenario, seed=7)

        self.assertEqual(events_a, events_b)


class SimulatorTests(unittest.TestCase):
    def test_fixed_policy_uses_ack_latency_as_vulnerability_window(self) -> None:
        scenario = ScenarioConfig(
            name="steady",
            duration=1.0,
            queue_capacity=20,
            target_window=1.0,
            segments=(ArrivalSegment(duration=1.0, rate=3.0, ack_latency=2.0),),
        )
        events = [
            Event(1, 0.0, b"a", 2.0, 0.2, 0.1, False, 3.0),
            Event(2, 0.2, b"b", 2.0, 0.2, 0.1, False, 3.0),
        ]
        policy = FixedEpochPolicy(epoch_size=2)

        result = run_simulation(scenario, policy, events=events)

        self.assertAlmostEqual(result.metrics.avg_vulnerability_window, 2.1, places=1)
        self.assertAlmostEqual(result.metrics.max_vulnerability_window, 2.2, places=1)

    def test_adaptive_policy_closes_early_for_critical_event(self) -> None:
        scenario = ScenarioConfig(
            name="critical",
            duration=3.0,
            queue_capacity=20,
            target_window=2.0,
            segments=(ArrivalSegment(duration=3.0, rate=5.0, ack_latency=1.0, critical_every=3),),
        )
        adaptive = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=12,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
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
        self.assertLessEqual(adaptive_result.metrics.max_vulnerability_window, 2.0)

    def test_adaptive_policy_closes_on_anomalous_storage_spike(self) -> None:
        scenario = ScenarioConfig(
            name="anomaly-spike",
            duration=5.0,
            queue_capacity=20,
            target_window=2.0,
            telemetry_window_size=3,
            anomaly_sigma_threshold=2.5,
            segments=(ArrivalSegment(duration=5.0, rate=5.0, ack_latency=1.0),),
        )
        adaptive = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=12,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
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
        self.assertLessEqual(adaptive_result.metrics.max_vulnerability_window, 5.0)


if __name__ == "__main__":
    unittest.main()
