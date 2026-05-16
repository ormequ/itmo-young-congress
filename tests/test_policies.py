import unittest

from domain import EpochState, TelemetrySample
from policies import AdaptiveEpochPolicy, FixedEpochPolicy


class FixedPolicyTests(unittest.TestCase):
    def test_closes_epoch_when_fixed_size_is_reached(self) -> None:
        policy = FixedEpochPolicy(epoch_size=3)
        state = EpochState(epoch_event_count=3, current_target=3)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=10.0))

        self.assertTrue(decision.should_close)
        self.assertEqual(decision.next_target, 3)

    def test_keeps_same_target_regardless_of_telemetry(self) -> None:
        policy = FixedEpochPolicy(epoch_size=7)
        state = EpochState(epoch_event_count=1, current_target=7)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=100.0, input_queue_fill=0.99))

        self.assertEqual(decision.next_target, 7)


class AdaptivePolicyTests(unittest.TestCase):
    def test_scales_target_from_arrival_rate(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=8.0))

        self.assertEqual(decision.next_target, 16)
        self.assertFalse(decision.should_close)

    def test_reduces_target_when_queue_is_near_capacity(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=10)
        telemetry = TelemetrySample(arrival_rate=8.0, input_queue_fill=0.95)

        decision = policy.evaluate(state, telemetry)

        self.assertLess(decision.next_target, 16)

    def test_memory_pressure_reduces_target_and_closes_at_budget(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            epoch_buffer_budget_bytes=1_000,
        )
        state = EpochState(epoch_event_count=1, current_target=10, epoch_payload_bytes=850)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, epoch_payload_bytes=850, memory_pressure=0.85),
        )

        self.assertLess(decision.next_target, 16)
        self.assertFalse(decision.should_close)

        close_decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, epoch_payload_bytes=1_000, memory_pressure=1.0),
        )

        self.assertTrue(close_decision.should_close)

    def test_closes_epoch_early_for_critical_events(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, critical_event=True),
        )

        self.assertTrue(decision.should_close)

    def test_increases_target_when_anchor_ack_latency_degrades(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, anchor_ack_latency=3.1),
        )

        self.assertGreater(decision.next_target, state.current_target)
        self.assertFalse(decision.should_close)

    def test_increases_target_when_pending_anchors_exceed_limit(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=30,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            max_pending_anchors=2,
        )
        state = EpochState(epoch_event_count=1, current_target=16)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, pending_anchor_count=4),
        )

        self.assertGreater(decision.next_target, state.current_target)
        self.assertFalse(decision.should_close)

    def test_memory_pressure_caps_target_even_with_anchor_backpressure(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=40,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            max_pending_anchors=1,
        )
        state = EpochState(epoch_event_count=1, current_target=16)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, pending_anchor_count=10, memory_pressure=0.85),
        )

        self.assertLessEqual(decision.next_target, 4)
        self.assertFalse(decision.should_close)

    def test_source_priority_amplifies_anomaly_and_criticality(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            anomaly_score_threshold=3.0,
            criticality_threshold=0.9,
        )
        state = EpochState(epoch_event_count=1, current_target=10)

        low_priority = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, anomaly_score=2.0, criticality_level=0.5, source_priority=1.0),
        )
        high_priority = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, anomaly_score=2.0, criticality_level=0.5, source_priority=2.0),
        )

        self.assertFalse(low_priority.should_close)
        self.assertTrue(high_priority.should_close)

    def test_source_priority_is_clamped_to_supported_range(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
            anomaly_score_threshold=3.0,
        )
        state = EpochState(epoch_event_count=1, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, anomaly_score=1.4, source_priority=10.0),
        )

        self.assertFalse(decision.should_close)

    def test_closes_epoch_on_high_anomaly_score(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=4, current_target=10)

        decision = policy.evaluate(
            state,
            TelemetrySample(
                arrival_rate=8.0,
                anchor_ack_latency=1.1,
                rolling_anchor_ack_mean=1.0,
                rolling_anchor_ack_std=0.02,
                anomaly_score=3.0,
            ),
        )

        self.assertTrue(decision.should_close)

    def test_closes_epoch_on_high_criticality_level(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=2,
            max_epoch_events=20,
            min_epoch_duration_seconds=0.0,
            max_epoch_duration_seconds=float("inf"),
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=2, current_target=8)

        decision = policy.evaluate(
            state,
            TelemetrySample(arrival_rate=8.0, criticality_level=0.95),
        )

        self.assertTrue(decision.should_close)

    def test_applies_epoch_duration_bounds_as_event_limits(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=0,
            max_epoch_events=float("inf"),
            min_epoch_duration_seconds=1.0,
            max_epoch_duration_seconds=3.0,
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=5.0))

        self.assertEqual(decision.next_target, 10)

    def test_prefers_stricter_of_event_and_duration_bounds(self) -> None:
        policy = AdaptiveEpochPolicy(
            target_commit_latency=2.0,
            min_epoch_events=8,
            max_epoch_events=12,
            min_epoch_duration_seconds=1.0,
            max_epoch_duration_seconds=3.0,
            change_threshold=0.1,
            anchor_ack_target=1.0,
        )
        state = EpochState(epoch_event_count=1, current_target=2)

        decision = policy.evaluate(state, TelemetrySample(arrival_rate=5.0))

        self.assertEqual(decision.next_target, 10)


if __name__ == "__main__":
    unittest.main()
