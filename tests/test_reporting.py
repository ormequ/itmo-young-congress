import json
import tempfile
import unittest
from pathlib import Path

from domain import ArrivalSegment, ScenarioConfig
from policies import AdaptiveEpochPolicy, FixedEpochPolicy
from reporting import build_report, run_batch


class ReportingTests(unittest.TestCase):
    def test_batch_and_report_create_expected_outputs(self) -> None:
        scenario = ScenarioConfig(
            name="steady",
            duration=3.0,
            queue_capacity=20,
            target_window=2.0,
            segments=(ArrivalSegment(duration=3.0, rate=5.0, ack_latency=1.0),),
        )
        policies = {
            "fixed-nominal": FixedEpochPolicy(epoch_size=10, min_epoch=2, max_epoch=12),
            "adaptive": AdaptiveEpochPolicy(
                target_window=2.0,
                min_epoch=2,
                max_epoch=12,
                change_threshold=0.1,
                ack_target=1.0,
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            summary_path = run_batch([scenario], policies, seeds=[1, 2], output_dir=output_dir)
            report_dir = build_report(summary_path, output_dir / "report")

            self.assertTrue(summary_path.exists())
            self.assertTrue((report_dir / "summary.csv").exists())
            self.assertTrue((report_dir / "summary.md").exists())
            self.assertTrue((report_dir / "avg_window.svg").exists())

            rows = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
