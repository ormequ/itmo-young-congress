# itmo-young-congress

Python-проект для тезиса про адаптивное формирование эпох Merkle-дерева в IoT-системах.

## Что есть

- реальные `HMAC` и `Merkle`-вычисления;
- фиксированная и адаптивная политики формирования эпох;
- дискретно-событийная симуляция с воспроизводимыми `seed`;
- batch-прогоны, SVG/CSV/Markdown-отчеты;
- smoke `asyncio` demo-контур.

## Быстрый старт

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m itmo_young_congress demo-run-scenario --config configs/steady.json --policy adaptive --seed 1 --output-dir artifacts/steady
PYTHONPATH=src python3 -m itmo_young_congress demo-run-batch --config configs/burst.json --seeds 1,2,3 --output-dir artifacts/burst-batch
PYTHONPATH=src python3 -m itmo_young_congress demo-build-report --summary artifacts/burst-batch/batch_summary.json --output-dir artifacts/burst-report
PYTHONPATH=src python3 -m itmo_young_congress demo-stress-test --config configs/burst.json --arrival-rates 2,4,6,8,10,12 --seeds 1,2,3 --window-limit 5.0 --queue-fill-limit 0.9 --output-dir artifacts/stress/burst
PYTHONPATH=src python3 -m itmo_young_congress demo-gateway --config configs/critical-event-injection.json --seed 2 --output artifacts/demo.json
```

## Сценарии

- `configs/steady.json`
- `configs/burst.json`
- `configs/storage-degradation.json`
- `configs/cpu-pressure.json`
- `configs/queue-saturation.json`
- `configs/combined-stress.json`
- `configs/critical-event-injection.json`
