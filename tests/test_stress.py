import json
import tempfile
import unittest
from pathlib import Path

from cli import main
from cli_common import load_scenario
from domain import ArrivalSegment, ScenarioConfig
from reporting import run_stress_capacity, run_stress_response, run_stress_test


class StressTests(unittest.TestCase):
    def test_load_scenario_reads_extended_threshold_fields(self) -> None:
        payload = {
            "name": "stress",
            "duration": 5.0,
            "queue_capacity": 20,
            "target_commit_latency": 2.0,
            "telemetry_window_size": 7,
            "anomaly_score_threshold": 2.2,
            "criticality_threshold": 0.8,
            "epoch_buffer_budget_bytes": 4096,
            "max_pending_anchors": 3,
            "segments": [{"duration": 5.0, "rate": 4.0, "anchor_ack_latency": 1.0, "source_priority": 1.5}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scenario.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            scenario = load_scenario(path)

        self.assertEqual(scenario.telemetry_window_size, 7)
        self.assertEqual(scenario.anomaly_score_threshold, 2.2)
        self.assertEqual(scenario.criticality_threshold, 0.8)
        self.assertEqual(scenario.epoch_buffer_budget_bytes, 4096)
        self.assertEqual(scenario.max_pending_anchors, 3)
        self.assertEqual(scenario.segments[0].source_priority, 1.5)

    def test_stress_test_reports_safe_throughput_per_policy(self) -> None:
        scenario = ScenarioConfig(
            name="stress",
            duration=8.0,
            queue_capacity=16,
            target_commit_latency=2.0,
            telemetry_window_size=3,
            anomaly_score_threshold=2.5,
            criticality_threshold=0.9,
            segments=(ArrivalSegment(duration=8.0, rate=4.0, anchor_ack_latency=1.0),),
        )

        summary = run_stress_test(
            scenario=scenario,
            arrival_rates=[2.0, 4.0, 6.0, 8.0],
            seeds=[1, 2, 3],
            commit_latency_limit=5.0,
            input_queue_fill_limit=0.9,
            commit_frequency_limit=2.0,
        )

        self.assertIn("adaptive", summary)
        self.assertIn("fixed-small", summary)
        self.assertIn("fixed-nominal", summary)
        self.assertIn("fixed-large", summary)
        self.assertIn("safe_throughput", summary["adaptive"])
        self.assertIn("commit_frequency_at_safe_throughput", summary["fixed-small"])
        self.assertIn("p95_commit_latency", summary["adaptive"])
        self.assertIn("p95_queue_depth_at_safe_throughput", summary["adaptive"])
        self.assertIn("queue_over_capacity_count_at_safe_throughput", summary["adaptive"])
        self.assertIn("max_pending_anchor_count_at_safe_throughput", summary["adaptive"])
        self.assertIn("passes_constraints", summary["fixed-large"])
        self.assertIn("signature_time_per_second_at_safe_throughput", summary["adaptive"])

    def test_stress_response_returns_trace_per_policy(self) -> None:
        scenario = ScenarioConfig(
            name="response",
            duration=6.0,
            queue_capacity=16,
            target_commit_latency=2.0,
            telemetry_window_size=3,
            anomaly_score_threshold=2.5,
            criticality_threshold=0.9,
            segments=(
                ArrivalSegment(duration=2.0, rate=4.0, anchor_ack_latency=1.0, input_queue_fill=0.2),
                ArrivalSegment(duration=2.0, rate=8.0, anchor_ack_latency=2.0, input_queue_fill=0.95),
                ArrivalSegment(duration=2.0, rate=5.0, anchor_ack_latency=1.2, input_queue_fill=0.3),
            ),
        )

        payload = run_stress_response(scenario=scenario, policies=["adaptive", "fixed-small"], seed=2)

        self.assertEqual(payload["scenario"], "response")
        self.assertIn("adaptive", payload["policies"])
        self.assertIn("fixed-small", payload["policies"])
        self.assertTrue(payload["policies"]["adaptive"])
        self.assertIn("next_target", payload["policies"]["adaptive"][0])
        self.assertEqual(len(payload["phases"]), 3)
        self.assertEqual(payload["phases"][0]["start"], 0.0)
        self.assertIn("commit_latency_points", payload)
        self.assertIn("adaptive", payload["commit_latency_points"])
        self.assertTrue(payload["commit_latency_points"]["adaptive"])
        self.assertIn("max_commit_latency", payload["commit_latency_points"]["adaptive"][0])
        adaptive_closes = [point for point in payload["policies"]["adaptive"] if point["should_close"]]
        self.assertTrue(adaptive_closes)
        self.assertTrue(any("input_queue_pressure" in point["close_reasons"] for point in adaptive_closes))

    def test_stress_capacity_returns_curve_points_for_all_policies(self) -> None:
        scenario = ScenarioConfig(
            name="capacity",
            duration=6.0,
            queue_capacity=16,
            target_commit_latency=2.0,
            telemetry_window_size=3,
            anomaly_score_threshold=2.5,
            criticality_threshold=0.9,
            segments=(ArrivalSegment(duration=6.0, rate=4.0, anchor_ack_latency=1.0),),
        )

        payload = run_stress_capacity(
            scenario=scenario,
            arrival_rates=[2.0, 4.0, 6.0],
            seeds=[1, 2],
            policies=["adaptive", "fixed-small", "fixed-nominal", "fixed-large"],
        )

        self.assertEqual(payload["scenario"], "capacity")
        self.assertEqual(payload["arrival_rates"], [2.0, 4.0, 6.0])
        self.assertIn("adaptive", payload["curves"])
        self.assertEqual(len(payload["curves"]["adaptive"]), 3)
        self.assertIn("max_commit_latency", payload["curves"]["adaptive"][0])
        self.assertIn("p95_commit_latency", payload["curves"]["adaptive"][0])
        self.assertIn("p95_queue_depth", payload["curves"]["adaptive"][0])
        self.assertIn("queue_over_capacity_count", payload["curves"]["adaptive"][0])
        self.assertIn("max_pending_anchor_count", payload["curves"]["adaptive"][0])
        self.assertIn("is_safe", payload["curves"]["adaptive"][0])
        self.assertIn("safe_throughput", payload["policies"]["adaptive"])

    def test_stress_capacity_marks_pending_anchor_over_limit_as_unsafe(self) -> None:
        scenario = ScenarioConfig(
            name="anchor-capacity",
            duration=8.0,
            queue_capacity=32,
            target_commit_latency=1.0,
            telemetry_window_size=1,
            max_pending_anchors=0,
            segments=(ArrivalSegment(duration=8.0, rate=8.0, anchor_ack_latency=5.0),),
        )

        payload = run_stress_capacity(
            scenario=scenario,
            arrival_rates=[8.0],
            seeds=[1],
            policies=["fixed-small"],
            commit_latency_limit=100.0,
            input_queue_fill_limit=1.0,
        )

        point = payload["curves"]["fixed-small"][0]
        self.assertGreater(point["max_pending_anchor_count"], 0)
        self.assertFalse(point["is_safe"])
        self.assertEqual(payload["policies"]["fixed-small"]["safe_throughput"], 0.0)

    def test_article_scenario_configs_isolate_memory_and_anchor_pressure(self) -> None:
        root = Path(__file__).resolve().parents[1]
        memory = load_scenario(root / "configs" / "memory-pressure.json")
        anchor = load_scenario(root / "configs" / "anchor-backpressure.json")

        self.assertLess(memory.epoch_buffer_budget_bytes, float("inf"))
        self.assertTrue(all(segment.anchor_ack_latency <= 1.2 for segment in memory.segments))
        self.assertTrue(all(segment.input_queue_fill <= 0.4 for segment in memory.segments))
        self.assertTrue(any(segment.payload_size_bytes >= 256 for segment in memory.segments))
        self.assertEqual(anchor.epoch_buffer_budget_bytes, float("inf"))
        self.assertEqual(anchor.max_pending_anchors, 1)
        self.assertTrue(any(segment.anchor_ack_latency >= 4.0 for segment in anchor.segments))

    def test_cli_stress_test_command_writes_summary(self) -> None:
        payload = {
            "name": "stress",
            "duration": 8.0,
            "queue_capacity": 16,
            "target_commit_latency": 2.0,
            "telemetry_window_size": 3,
            "anomaly_score_threshold": 2.5,
            "criticality_threshold": 0.9,
            "segments": [{"duration": 8.0, "rate": 4.0, "anchor_ack_latency": 1.0}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "scenario.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            exit_code = main(
                [
                    "demo-stress-test",
                    "--config",
                    str(config_path),
                    "--arrival-rates",
                    "2,4,6",
                    "--seeds",
                    "1,2",
                    "--commit-latency-limit",
                    "5.0",
                    "--input-queue-fill-limit",
                    "0.9",
                    "--commit-frequency-limit",
                    "2.0",
                    "--output-dir",
                    str(tmp / "stress"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp / "stress" / "stress_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
