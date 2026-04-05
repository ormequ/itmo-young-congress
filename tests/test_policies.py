import unittest

from itmo_young_congress.domain import EpochState, TelemetrySample
from itmo_young_congress.policies import AdaptiveEpochPolicy, FixedEpochPolicy


class FixedPolicyTests(unittest.TestCase):
    def test_closes_epoch_when_fixed_size_is_reached(self) -> None:
        policy = FixedEpochPolicy(epoch_size=3, min_epoch=1, max_epoch=10)
        state = EpochState(event_count=3, current_target=3)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=10.0))

        self.assertTrue(decision.should_close)
        self.assertEqual(decision.next_target, 3)

    def test_respects_epoch_size_bounds(self) -> None:
        policy = FixedEpochPolicy(epoch_size=100, min_epoch=2, max_epoch=4)

        self.assertEqual(policy.fixed_target, 4)


class AdaptivePolicyTests(unittest.TestCase):
    def test_scales_target_from_arrival_rate(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
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
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
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
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, critical_event=True),
        )

        self.assertTrue(decision.should_close)

    def test_closes_epoch_on_ack_latency_anomaly(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, ack_latency=3.1),
        )

        self.assertTrue(decision.should_close)

    def test_closes_epoch_on_rolling_anomaly(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_window=2.0,
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
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
            min_epoch=2,
            max_epoch=20,
            ema_alpha=0.2,
            change_threshold=0.1,
            ack_target=1.0,
        )
        state = EpochState(event_count=2, current_target=8)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, data_criticality=0.95),
        )

        self.assertTrue(decision.should_close)


if __name__ == "__main__":
    unittest.main()
