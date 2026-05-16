import asyncio
import unittest

from demo import run_demo_gateway
from domain import ArrivalSegment, ScenarioConfig


class DemoTests(unittest.TestCase):
    def test_demo_gateway_processes_events(self) -> None:
        scenario = ScenarioConfig(
            name="demo",
            duration=2.0,
            queue_capacity=10,
            target_commit_latency=1.0,
            segments=(ArrivalSegment(duration=2.0, rate=4.0),),
        )

        result = asyncio.run(run_demo_gateway(scenario, seed=5))

        self.assertGreater(result["events_processed"], 0)
        self.assertEqual(result["epochs_closed"], 1)


if __name__ == "__main__":
    unittest.main()
