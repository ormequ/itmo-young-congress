import json
import tempfile
import unittest
from pathlib import Path

from cli import main
from cli_common import load_scenario
from domain import ArrivalSegment, ScenarioConfig
from reporting import run_stress_test


class StressTests(unittest.TestCase):
    def test_load_scenario_reads_extended_threshold_fields(self) -> None:
        payload = {
            "name": "stress",
            "duration": 5.0,
            "queue_capacity": 20,
            "target_window": 2.0,
            "telemetry_window_size": 7,
            "anomaly_sigma_threshold": 2.2,
            "criticality_threshold": 0.8,
            "segments": [{"duration": 5.0, "rate": 4.0, "ack_latency": 1.0}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scenario.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            scenario = load_scenario(path)

        self.assertEqual(scenario.telemetry_window_size, 7)
        self.assertEqual(scenario.anomaly_sigma_threshold, 2.2)
        self.assertEqual(scenario.criticality_threshold, 0.8)

    def test_stress_test_reports_safe_throughput_per_policy(self) -> None:
        scenario = ScenarioConfig(
            name="stress",
            duration=8.0,
            queue_capacity=16,
            target_window=2.0,
            telemetry_window_size=3,
            anomaly_sigma_threshold=2.5,
            criticality_threshold=0.9,
            segments=(ArrivalSegment(duration=8.0, rate=4.0, ack_latency=1.0),),
        )

        summary = run_stress_test(
            scenario=scenario,
            arrival_rates=[2.0, 4.0, 6.0, 8.0],
            seeds=[1, 2, 3],
            window_limit=5.0,
            queue_fill_limit=0.9,
            commit_frequency_limit=2.0,
        )

        self.assertIn("adaptive", summary)
        self.assertIn("fixed-small", summary)
        self.assertIn("fixed-nominal", summary)
        self.assertIn("fixed-large", summary)
        self.assertIn("safe_throughput", summary["adaptive"])
        self.assertIn("commit_frequency_at_safe_throughput", summary["fixed-small"])
        self.assertIn("passes_constraints", summary["fixed-large"])
        self.assertIn("signature_time_per_second_at_safe_throughput", summary["adaptive"])

    def test_cli_stress_test_command_writes_summary(self) -> None:
        payload = {
            "name": "stress",
            "duration": 8.0,
            "queue_capacity": 16,
            "target_window": 2.0,
            "telemetry_window_size": 3,
            "anomaly_sigma_threshold": 2.5,
            "criticality_threshold": 0.9,
            "segments": [{"duration": 8.0, "rate": 4.0, "ack_latency": 1.0}],
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
                    "--window-limit",
                    "5.0",
                    "--queue-fill-limit",
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
