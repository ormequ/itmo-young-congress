from __future__ import annotations

import asyncio
from typing import Dict, List

from domain import ScenarioConfig
from simulator import generate_events


async def run_demo_gateway(scenario: ScenarioConfig, seed: int = 1) -> Dict[str, int]:
    queue: asyncio.Queue = asyncio.Queue()
    consumed: List[int] = []

    async def producer() -> None:
        for event in generate_events(scenario, seed):
            await queue.put(event)
        await queue.put(None)

    async def consumer() -> None:
        while True:
            event = await queue.get()
            if event is None:
                break
            consumed.append(event.event_id)

    await asyncio.gather(producer(), consumer())
    return {"events_processed": len(consumed), "epochs_closed": 1 if consumed else 0}
