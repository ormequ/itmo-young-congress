import json
import tempfile
import unittest
from pathlib import Path

from cli import main
from crypto import build_merkle_tree


class CliTests(unittest.TestCase):
    def test_run_scenario_and_build_report_commands(self) -> None:
        scenario = {
            "name": "steady",
            "duration": 3.0,
            "queue_capacity": 20,
            "target_window": 2.0,
            "segments": [{"duration": 3.0, "rate": 5.0, "ack_latency": 1.0}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / "scenario.json"
            config_path.write_text(json.dumps(scenario), encoding="utf-8")

            exit_code = main(
                [
                    "demo-run-scenario",
                    "--config",
                    str(config_path),
                    "--policy",
                    "adaptive",
                    "--seed",
                    "1",
                    "--output-dir",
                    str(tmp / "single"),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp / "single" / "result.json").exists())

            exit_code = main(
                [
                    "demo-run-batch",
                    "--config",
                    str(config_path),
                    "--seeds",
                    "1,2",
                    "--output-dir",
                    str(tmp / "batch"),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp / "batch" / "batch_summary.json").exists())

            exit_code = main(
                [
                    "demo-build-report",
                    "--summary",
                    str(tmp / "batch" / "batch_summary.json"),
                    "--output-dir",
                    str(tmp / "report"),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp / "report" / "summary.md").exists())

    def test_verify_proof_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            tree = build_merkle_tree([b"alpha", b"beta", b"gamma"])
            payload = {
                "leaf": "62657461",
                "root": tree.root.hex(),
                "proof": [
                    {"hash": sibling.hex(), "left": left}
                    for sibling, left in tree.proof_for(1)
                ],
            }
            proof_path = tmp / "proof.json"
            proof_path.write_text(json.dumps(payload), encoding="utf-8")

            exit_code = main(["verify-proof", "--input", str(proof_path)])

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
