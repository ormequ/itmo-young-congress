import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_plot_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "plot_results.py"
    spec = importlib.util.spec_from_file_location("plot_results", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PlotResultsTests(unittest.TestCase):
    def test_build_batch_plots_writes_png_files(self) -> None:
        plot_results = _load_plot_module()
        rows = [
            {
                "scenario": "steady",
                "seed": 1,
                "policy": "adaptive",
                "avg_vulnerability_window": 1.2,
                "max_vulnerability_window": 2.0,
                "commit_frequency": 0.5,
                "max_queue_depth": 5,
                "throughput": 4.0,
                "avg_proof_bytes": 64.0,
            },
            {
                "scenario": "steady",
                "seed": 1,
                "policy": "fixed-nominal",
                "avg_vulnerability_window": 1.8,
                "max_vulnerability_window": 2.5,
                "commit_frequency": 0.4,
                "max_queue_depth": 8,
                "throughput": 4.0,
                "avg_proof_bytes": 96.0,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary_path = tmp / "batch_summary.json"
            summary_path.write_text(json.dumps(rows), encoding="utf-8")

            output_dir = tmp / "plots"
            plot_results.build_batch_plots(summary_path, output_dir)

            self.assertTrue((output_dir / "avg_window.png").exists())
            self.assertTrue((output_dir / "max_window.png").exists())
            self.assertTrue((output_dir / "commit_frequency.png").exists())
            self.assertTrue((output_dir / "max_queue_depth.png").exists())
            self.assertTrue((output_dir / "avg_proof_bytes.png").exists())
            self.assertTrue((output_dir / "tradeoff.png").exists())

    def test_build_stress_plots_writes_png_files(self) -> None:
        plot_results = _load_plot_module()
        summary = {
            "adaptive": {
                "safe_throughput": 12.0,
                "avg_vulnerability_window": 2.0,
                "max_vulnerability_window": 4.0,
                "commit_frequency_at_safe_throughput": 1.2,
                "max_queue_depth_at_safe_throughput": 8.0,
                "avg_proof_bytes_at_safe_throughput": 96.0,
            },
            "fixed-small": {
                "safe_throughput": 10.0,
                "avg_vulnerability_window": 1.8,
                "max_vulnerability_window": 3.5,
                "commit_frequency_at_safe_throughput": 2.3,
                "max_queue_depth_at_safe_throughput": 4.0,
                "avg_proof_bytes_at_safe_throughput": 64.0,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            stress_path = tmp / "stress_summary.json"
            stress_path.write_text(json.dumps(summary), encoding="utf-8")

            output_dir = tmp / "plots"
            plot_results.build_stress_plots(stress_path, output_dir)

            self.assertTrue((output_dir / "safe_throughput.png").exists())
            self.assertTrue((output_dir / "stress_commit_frequency.png").exists())
            self.assertTrue((output_dir / "stress_max_window.png").exists())
            self.assertTrue((output_dir / "stress_avg_proof_bytes.png").exists())


if __name__ == "__main__":
    unittest.main()
