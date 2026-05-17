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
    def test_display_mappings_use_russian_labels(self) -> None:
        plot_results = _load_plot_module()
        self.assertEqual(plot_results._short_scenario_name("storage-degradation"), "Storage degradation")
        self.assertEqual(plot_results._short_scenario_name("anchor-backpressure"), "Anchor backpressure")
        self.assertEqual(plot_results._short_scenario_name("queue-saturation"), "Queue saturation")
        self.assertEqual(plot_results._short_scenario_name("steady"), "Steady state")
        self.assertEqual(plot_results.POLICY_LABELS["adaptive"], "Adaptive")
        self.assertEqual(plot_results.POLICY_LABELS["fixed-small"], "Fixed-small")
        self.assertEqual(
            plot_results.ABLATION_POLICY_LABELS["adaptive-no-pending-anchors"],
            "Adaptive w/o anchor BP",
        )

    def test_backpressure_response_uses_article_labels(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "scripts" / "plot_results.py").read_text(encoding="utf-8")
        self.assertIn("Local commit frequency, 1/s", source)
        self.assertIn("Adaptive w/o anchor BP", source)
        self.assertNotIn("Adaptive without anchor backpressure", source)

    def test_cost_overview_uses_compact_article_panels(self) -> None:
        plot_results = _load_plot_module()

        self.assertEqual(
            plot_results.COST_OVERVIEW_SCENARIOS,
            ["burst", "anchor-backpressure", "memory-pressure", "queue-saturation", "combined-stress"],
        )
        self.assertEqual(
            plot_results.COST_OVERVIEW_PANELS,
            [
                ("commit_frequency", "Commit frequency, 1/s"),
                ("queue_over_capacity_count", "Queue over-capacity count"),
            ],
        )

    def test_commit_latency_overview_uses_tail_latency_panels(self) -> None:
        plot_results = _load_plot_module()

        self.assertEqual(
            plot_results.COMMIT_LATENCY_OVERVIEW_SCENARIOS,
            ["anchor-backpressure", "burst", "memory-pressure", "queue-saturation", "combined-stress", "steady"],
        )
        self.assertEqual(
            plot_results.COMMIT_LATENCY_OVERVIEW_PANELS,
            [
                ("p95_commit_latency", "P95 commit latency, s"),
                ("max_commit_latency", "Max commit latency, s"),
            ],
        )

    def test_plot_script_contains_no_cyrillic_plot_text(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "scripts" / "plot_results.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"[А-Яа-яЁё]")

    def test_payload_metrics_are_converted_to_kib_for_plots(self) -> None:
        plot_results = _load_plot_module()
        rows = [{"scenario": "memory-pressure", "policy": "adaptive", "max_epoch_payload_bytes": 2048}]

        values = plot_results._metric_values(rows, ["memory-pressure"], "adaptive", "max_epoch_payload_kib")

        self.assertEqual(values, [2.0])

    def test_build_batch_plots_writes_png_files(self) -> None:
        plot_results = _load_plot_module()
        rows = [
            {
                "scenario": "steady",
                "seed": 1,
                "policy": "adaptive",
                "avg_commit_latency": 1.2,
                "p95_commit_latency": 1.6,
                "max_commit_latency": 2.0,
                "target_commit_latency": 2.0,
                "commit_frequency": 0.5,
                "max_queue_depth": 5,
                "p95_queue_depth": 4.0,
                "queue_over_capacity_count": 0,
                "max_epoch_payload_bytes": 120,
                "p95_epoch_payload_bytes": 110.0,
                "max_pending_anchor_count": 1,
                "p95_pending_anchor_count": 0.5,
                "throughput": 4.0,
                "avg_proof_bytes": 64.0,
                "signature_time_per_second": 0.2,
            },
            {
                "scenario": "steady",
                "seed": 1,
                "policy": "fixed-nominal",
                "avg_commit_latency": 1.8,
                "p95_commit_latency": 2.1,
                "max_commit_latency": 2.5,
                "target_commit_latency": 2.0,
                "commit_frequency": 0.4,
                "max_queue_depth": 8,
                "p95_queue_depth": 6.0,
                "queue_over_capacity_count": 1,
                "max_epoch_payload_bytes": 260,
                "p95_epoch_payload_bytes": 240.0,
                "max_pending_anchor_count": 2,
                "p95_pending_anchor_count": 1.0,
                "throughput": 4.0,
                "avg_proof_bytes": 96.0,
                "signature_time_per_second": 0.1,
            },
            {
                "scenario": "anchor-backpressure",
                "seed": 1,
                "policy": "adaptive",
                "avg_commit_latency": 1.6,
                "p95_commit_latency": 2.0,
                "max_commit_latency": 2.8,
                "target_commit_latency": 1.0,
                "commit_frequency": 0.7,
                "max_queue_depth": 6,
                "p95_queue_depth": 4.0,
                "queue_over_capacity_count": 0,
                "max_epoch_payload_bytes": 120,
                "p95_epoch_payload_bytes": 110.0,
                "max_pending_anchor_count": 2,
                "p95_pending_anchor_count": 1.0,
                "throughput": 8.0,
                "avg_proof_bytes": 64.0,
                "signature_time_per_second": 0.2,
            },
            {
                "scenario": "anchor-backpressure",
                "seed": 1,
                "policy": "adaptive-no-pending-anchors",
                "avg_commit_latency": 1.4,
                "p95_commit_latency": 1.8,
                "max_commit_latency": 2.6,
                "target_commit_latency": 1.0,
                "commit_frequency": 1.1,
                "max_queue_depth": 5,
                "p95_queue_depth": 3.0,
                "queue_over_capacity_count": 0,
                "max_epoch_payload_bytes": 100,
                "p95_epoch_payload_bytes": 90.0,
                "max_pending_anchor_count": 4,
                "p95_pending_anchor_count": 3.0,
                "throughput": 8.0,
                "avg_proof_bytes": 64.0,
                "signature_time_per_second": 0.2,
            },
            {
                "scenario": "anchor-backpressure",
                "seed": 1,
                "policy": "fixed-small",
                "avg_commit_latency": 1.2,
                "p95_commit_latency": 1.5,
                "max_commit_latency": 2.0,
                "target_commit_latency": 1.0,
                "commit_frequency": 1.4,
                "max_queue_depth": 4,
                "p95_queue_depth": 3.0,
                "queue_over_capacity_count": 0,
                "max_epoch_payload_bytes": 100,
                "p95_epoch_payload_bytes": 90.0,
                "max_pending_anchor_count": 5,
                "p95_pending_anchor_count": 4.0,
                "throughput": 8.0,
                "avg_proof_bytes": 64.0,
                "signature_time_per_second": 0.2,
            },
            {
                "scenario": "anchor-backpressure",
                "seed": 1,
                "policy": "fixed-nominal",
                "avg_commit_latency": 2.0,
                "p95_commit_latency": 2.6,
                "max_commit_latency": 3.2,
                "target_commit_latency": 1.0,
                "commit_frequency": 0.5,
                "max_queue_depth": 8,
                "p95_queue_depth": 6.0,
                "queue_over_capacity_count": 0,
                "max_epoch_payload_bytes": 200,
                "p95_epoch_payload_bytes": 180.0,
                "max_pending_anchor_count": 1,
                "p95_pending_anchor_count": 1.0,
                "throughput": 8.0,
                "avg_proof_bytes": 96.0,
                "signature_time_per_second": 0.1,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary_path = tmp / "batch_summary.json"
            summary_path.write_text(json.dumps(rows), encoding="utf-8")

            output_dir = tmp / "plots"
            plot_results.build_batch_plots(summary_path, output_dir)

            self.assertTrue((output_dir / "avg_commit_latency.png").exists())
            self.assertTrue((output_dir / "max_commit_latency.png").exists())
            self.assertTrue((output_dir / "commit_frequency.png").exists())
            self.assertTrue((output_dir / "p95_queue_depth.png").exists())
            self.assertTrue((output_dir / "avg_proof_bytes.png").exists())
            self.assertTrue((output_dir / "tradeoff.png").exists())
            self.assertTrue((output_dir / "commit_latency_overview.png").exists())
            self.assertTrue((output_dir / "commit_latency_full.png").exists())
            self.assertTrue((output_dir / "cost_and_stability_overview.png").exists())
            self.assertTrue((output_dir / "cost_and_stability_full.png").exists())
            self.assertTrue((output_dir / "memory_pressure_overview.png").exists())
            self.assertTrue((output_dir / "anchor_backpressure_overview.png").exists())
            self.assertTrue((output_dir / "anchor_backpressure_full.png").exists())
            self.assertTrue((output_dir / "anchor_backpressure_ablation.png").exists())

    def test_build_combined_stress_table_writes_markdown_and_csv(self) -> None:
        plot_results = _load_plot_module()
        rows = []
        for seed in range(1, 4):
            for policy in ["adaptive", "fixed-small", "fixed-nominal", "fixed-large"]:
                rows.append(
                    {
                        "scenario": "combined-stress",
                        "seed": seed,
                        "policy": policy,
                        "avg_commit_latency": float(seed),
                        "p95_commit_latency": float(seed + 1),
                        "max_commit_latency": float(seed + 2),
                        "commit_frequency": float(seed + 3),
                        "p95_epoch_payload_bytes": float(1024 * seed),
                        "p95_pending_anchor_count": float(seed + 4),
                        "p95_queue_depth": float(seed + 5),
                        "queue_over_capacity_count": seed,
                    }
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary_path = tmp / "batch_summary.json"
            summary_path.write_text(json.dumps(rows), encoding="utf-8")
            output_dir = tmp / "plots"

            plot_results.build_combined_stress_table(summary_path, output_dir)

            self.assertTrue((output_dir / "combined_stress_table.md").exists())
            self.assertTrue((output_dir / "combined_stress_table.csv").exists())
            self.assertFalse((output_dir / "combined_stress_table.png").exists())
            markdown = (output_dir / "combined_stress_table.md").read_text(encoding="utf-8")
            self.assertIn("mean +/- std", markdown)
            self.assertIn("P95 payload, KiB", markdown)
            self.assertIn("P95 queue depth", markdown)
            self.assertNotIn("Avg latency", markdown)
            self.assertNotIn("Max latency", markdown)
            self.assertNotIn("P95 pending anchors", markdown)

    def test_build_close_reason_counts_writes_markdown_and_csv(self) -> None:
        plot_results = _load_plot_module()
        trace = {
            "scenario": "combined-stress",
            "policies": {
                "adaptive": [
                    {"should_close": True, "close_reasons": ["target_reached", "memory_pressure"]},
                    {"should_close": True, "close_reasons": ["input_queue_pressure"]},
                    {"should_close": False, "close_reasons": []},
                ],
                "fixed-nominal": [
                    {"should_close": True, "close_reasons": ["target_reached"]},
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            trace_path = tmp / "combined_trace.json"
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            output_dir = tmp / "plots"

            plot_results.build_close_reason_counts(trace_path, output_dir)

            markdown = (output_dir / "close_reason_counts_combined_stress.md").read_text(encoding="utf-8")
            self.assertTrue((output_dir / "close_reason_counts_combined_stress.csv").exists())
            self.assertIn("memory_pressure", markdown)
            self.assertIn("input_queue_pressure", markdown)
            self.assertIn("| target_reached | 1 |", markdown)

    def test_aggregate_batch_rows_includes_article_metrics(self) -> None:
        plot_results = _load_plot_module()
        rows = [
            {
                "scenario": "memory-pressure",
                "seed": 1,
                "policy": "adaptive",
                "avg_commit_latency": 1.0,
                "p95_commit_latency": 1.4,
                "max_commit_latency": 2.0,
                "target_commit_latency": 2.0,
                "commit_frequency": 0.5,
                "max_queue_depth": 3,
                "p95_queue_depth": 2.0,
                "queue_over_capacity_count": 1,
                "max_epoch_payload_bytes": 512,
                "p95_epoch_payload_bytes": 500.0,
                "max_pending_anchor_count": 2,
                "p95_pending_anchor_count": 1.0,
                "avg_proof_bytes": 64.0,
                "signature_time_per_second": 0.15,
            },
            {
                "scenario": "memory-pressure",
                "seed": 2,
                "policy": "adaptive",
                "avg_commit_latency": 3.0,
                "p95_commit_latency": 4.6,
                "max_commit_latency": 7.0,
                "target_commit_latency": 2.0,
                "commit_frequency": 0.7,
                "max_queue_depth": 5,
                "p95_queue_depth": 4.0,
                "queue_over_capacity_count": 2,
                "max_epoch_payload_bytes": 768,
                "p95_epoch_payload_bytes": 700.0,
                "max_pending_anchor_count": 4,
                "p95_pending_anchor_count": 3.0,
                "avg_proof_bytes": 96.0,
                "signature_time_per_second": 0.25,
            },
        ]

        summary = plot_results._aggregate_batch_rows(rows)

        self.assertEqual(len(summary), 1)
        row = summary[0]
        self.assertEqual(row["queue_over_capacity_count"], 3)
        self.assertEqual(row["max_epoch_payload_bytes"], 768)
        self.assertEqual(row["p95_epoch_payload_bytes"], 600.0)
        self.assertEqual(row["max_pending_anchor_count"], 4)
        self.assertEqual(row["p95_pending_anchor_count"], 2.0)
        self.assertEqual(row["signature_time_per_second"], 0.2)
        self.assertEqual(row["target_commit_latency"], 2.0)

    def test_build_stress_plots_writes_png_files(self) -> None:
        plot_results = _load_plot_module()
        summary = {
            "adaptive": {
                "safe_throughput": 12.0,
                "avg_commit_latency": 2.0,
                "max_commit_latency": 4.0,
                "commit_frequency_at_safe_throughput": 1.2,
                "max_queue_depth_at_safe_throughput": 8.0,
                "avg_proof_bytes_at_safe_throughput": 96.0,
            },
            "fixed-small": {
                "safe_throughput": 10.0,
                "avg_commit_latency": 1.8,
                "max_commit_latency": 3.5,
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
            self.assertTrue((output_dir / "stress_max_commit_latency.png").exists())
            self.assertTrue((output_dir / "stress_avg_proof_bytes.png").exists())

    def test_build_timeline_plots_writes_png_files(self) -> None:
        plot_results = _load_plot_module()
        trace = {
            "scenario": "burst",
            "points": [
                {
                    "time": 0.2,
                    "policy": "adaptive",
                    "arrival_rate": 3.0,
                    "anchor_ack_latency": 1.0,
                    "input_queue_fill": 0.1,
                    "memory_pressure": 0.1,
                    "pending_anchor_count": 0,
                    "max_pending_anchors": 3,
                    "epoch_event_count": 1,
                    "current_target": 2,
                    "next_target": 6,
                    "should_close": False,
                },
                {
                    "time": 1.4,
                    "policy": "adaptive",
                    "arrival_rate": 8.0,
                    "anchor_ack_latency": 1.0,
                    "input_queue_fill": 0.6,
                    "memory_pressure": 0.65,
                    "pending_anchor_count": 1,
                    "max_pending_anchors": 3,
                    "epoch_event_count": 2,
                    "current_target": 6,
                    "next_target": 16,
                    "should_close": False,
                },
                {
                    "time": 1.9,
                    "policy": "adaptive",
                    "arrival_rate": 8.0,
                    "anchor_ack_latency": 2.8,
                    "input_queue_fill": 0.9,
                    "memory_pressure": 1.0,
                    "pending_anchor_count": 4,
                    "max_pending_anchors": 3,
                    "epoch_event_count": 3,
                    "current_target": 16,
                    "next_target": 8,
                    "should_close": True,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            trace_path = tmp / "trace.json"
            trace_path.write_text(json.dumps(trace), encoding="utf-8")

            output_dir = tmp / "plots"
            plot_results.build_timeline_plots(trace_path, output_dir)

            self.assertTrue((output_dir / "target_timeline.png").exists())
            self.assertTrue((output_dir / "telemetry_timeline.png").exists())
            self.assertTrue((output_dir / "adaptation_timeline.png").exists())

    def test_build_timeline_plots_accepts_stress_response_payload(self) -> None:
        plot_results = _load_plot_module()
        point = {
            "time": 1.0,
            "policy": "adaptive",
            "arrival_rate": 8.0,
            "anchor_ack_latency": 2.0,
            "input_queue_fill": 0.5,
            "memory_pressure": 0.4,
            "pending_anchor_count": 1,
            "max_pending_anchors": 2,
            "epoch_event_count": 2,
            "current_target": 4,
            "next_target": 6,
            "should_close": False,
        }
        payload = {
            "scenario": "anchor-backpressure",
            "policies": {
                "adaptive": [point],
                "fixed-nominal": [{**point, "policy": "fixed", "next_target": 8}],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            trace_path = tmp / "stress_response.json"
            trace_path.write_text(json.dumps(payload), encoding="utf-8")

            output_dir = tmp / "plots"
            plot_results.build_timeline_plots(trace_path, output_dir)

            self.assertTrue((output_dir / "adaptation_timeline.png").exists())
            self.assertTrue((output_dir / "backpressure_response_timeline.png").exists())

    def test_build_stress_plots_accepts_capacity_payload(self) -> None:
        plot_results = _load_plot_module()
        payload = {
            "scenario": "combined-stress",
            "arrival_rates": [4.0, 8.0],
            "curves": {
                "adaptive": [
                    {
                        "arrival_rate": 4.0,
                        "p95_commit_latency": 1.8,
                        "max_commit_latency": 2.4,
                        "commit_frequency": 0.8,
                        "p95_queue_depth": 4.0,
                        "queue_over_capacity_count": 0,
                        "max_pending_anchor_count": 1,
                        "is_safe": True,
                    },
                    {
                        "arrival_rate": 8.0,
                        "p95_commit_latency": 3.6,
                        "max_commit_latency": 5.0,
                        "commit_frequency": 1.0,
                        "p95_queue_depth": 7.0,
                        "queue_over_capacity_count": 0,
                        "max_pending_anchor_count": 2,
                        "is_safe": True,
                    },
                ],
                "fixed-large": [
                    {
                        "arrival_rate": 4.0,
                        "p95_commit_latency": 6.0,
                        "max_commit_latency": 7.0,
                        "commit_frequency": 0.2,
                        "p95_queue_depth": 10.0,
                        "queue_over_capacity_count": 0,
                        "max_pending_anchor_count": 0,
                        "is_safe": False,
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            summary_path = tmp / "capacity_summary.json"
            summary_path.write_text(json.dumps(payload), encoding="utf-8")
            output_dir = tmp / "plots"

            plot_results.build_stress_plots(summary_path, output_dir)

            self.assertTrue((output_dir / "stress_capacity.png").exists())
            self.assertTrue((output_dir / "stress_summary_table.png").exists())


if __name__ == "__main__":
    unittest.main()
