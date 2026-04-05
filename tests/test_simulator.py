import unittest

from itmo_young_congress.domain import ArrivalSegment, Event, ScenarioConfig
from itmo_young_congress.policies import AdaptiveEpochPolicy, FixedEpochPolicy
from itmo_young_congress.simulator import generate_events, run_simulation


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
        policy = FixedEpochPolicy(epoch_size=2, min_epoch=1, max_epoch=10)

        result = run_simulation(scenario, policy, events=events)

        self.assertAlmostEqual(result.metrics.avg_vulnerability_window, 2.1, places=1)
        self.assertAlmostEqual(result.metrics.max_vulnerability_window, 2.2, places=1)

    def test_adaptive_policy_early_close_improves_peak_window_for_critical_event(self) -> None:
        scenario = ScenarioConfig(
            name="critical",
            duration=3.0,
            queue_capacity=20,
            target_window=2.0,
            segments=(ArrivalSegment(duration=3.0, rate=5.0, ack_latency=1.0, critical_every=3),),
        )
        adaptive = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch=2,
            max_epoch=12,
            ema_alpha=0.2,
            change_threshold=0.1,
            ack_target=1.0,
        )
        fixed = FixedEpochPolicy(epoch_size=10, min_epoch=2, max_epoch=12)

        events = [
            Event(1, 0.0, b"a", 1.0, 0.2, 0.1, False, 5.0),
            Event(2, 0.2, b"b", 1.0, 0.2, 0.1, False, 5.0),
            Event(3, 0.4, b"c", 1.0, 0.2, 0.1, True, 5.0),
            Event(4, 1.2, b"d", 1.0, 0.2, 0.1, False, 5.0),
        ]

        adaptive_result = run_simulation(scenario, adaptive, events=events)
        fixed_result = run_simulation(scenario, fixed, events=events)

        self.assertLess(
            adaptive_result.metrics.max_vulnerability_window,
            fixed_result.metrics.max_vulnerability_window,
        )


if __name__ == "__main__":
    unittest.main()
