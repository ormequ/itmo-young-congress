import unittest

from domain import EpochState, TelemetrySample
from policies import AdaptiveEpochPolicy, FixedEpochPolicy


class FixedPolicyTests(unittest.TestCase):
    def test_closes_epoch_when_fixed_size_is_reached(self) -> None:
        policy = FixedEpochPolicy(epoch_size=3)
        state = EpochState(event_count=3, current_target=3)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=10.0))

        self.assertTrue(decision.should_close)
        self.assertEqual(decision.next_target, 3)

    def test_keeps_same_target_regardless_of_telemetry(self) -> None:
        policy = FixedEpochPolicy(epoch_size=7)
        state = EpochState(event_count=1, current_target=7)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=100.0, queue_fill=0.99))

        self.assertEqual(decision.next_target, 7)


class AdaptivePolicyTests(unittest.TestCase):
    def test_scales_target_from_arrival_rate(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=8.0))

        self.assertEqual(decision.next_target, 16)
        self.assertFalse(decision.should_close)

    def test_reduces_target_when_queue_is_near_capacity(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=10)
        telemetry = TelemetrySample(arrival_rate=8.0, queue_fill=0.95)

        decision = policy.evaluate(state, telemetry)

        self.assertLess(decision.next_target, 16)

    def test_closes_epoch_early_for_critical_events(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, critical_event=True),
        )

        self.assertTrue(decision.should_close)

    def test_increases_target_when_ack_latency_degrades(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, ack_latency=3.1),
        )

        self.assertGreater(decision.next_target, state.current_target)
        self.assertFalse(decision.should_close)

    def test_closes_epoch_on_rolling_anomaly(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=4, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(
                arrival_rate=8.0,
                ack_latency=1.1,
                rolling_ack_mean=1.0,
                rolling_ack_std=0.02,
                anomaly_detected=True,
            ),
        )

        self.assertTrue(decision.should_close)

    def test_closes_epoch_on_high_data_criticality(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_window_seconds=0.0,
            max_window_seconds=float("inf"),
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=2, current_target=8)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, data_criticality=0.95),
        )

        self.assertTrue(decision.should_close)

    def test_applies_window_second_bounds_as_event_limits(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=0,
            max_epoch_events=float("inf"),
            min_window_seconds=1.0,
            max_window_seconds=3.0,
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=5.0))

        self.assertEqual(decision.next_target, 10)

    def test_prefers_stricter_of_event_and_window_bounds(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch_events=8,
            max_epoch_events=12,
            min_window_seconds=1.0,
            max_window_seconds=3.0,
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=5.0))

        self.assertEqual(decision.next_target, 10)


if __name__ == "__main__":
    unittest.main()
