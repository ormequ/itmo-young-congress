# Адаптивное формирование эпох Merkle-дерева в IoT-системах

Python-проект для адаптивного формирования эпох Merkle-дерева в IoT-системах.

## Быстрый старт

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m itmo_young_congress demo-run-scenario --config configs/steady.json --policy adaptive --seed 1 --output-dir artifacts/steady
PYTHONPATH=src python3 -m itmo_young_congress demo-run-batch --config configs/burst.json --seeds 1,2,3 --output-dir artifacts/burst-batch
PYTHONPATH=src python3 -m itmo_young_congress demo-build-report --summary artifacts/burst-batch/batch_summary.json --output-dir artifacts/burst-report
PYTHONPATH=src python3 -m itmo_young_congress demo-stress-test --config configs/burst.json --arrival-rates 2,4,6,8,10,12 --seeds 1,2,3 --window-limit 5.0 --queue-fill-limit 0.9 --output-dir artifacts/stress/burst
PYTHONPATH=src python3 -m itmo_young_congress demo-gateway --config configs/critical-event-injection.json --seed 2 --output artifacts/demo.json
```

## Политики эпох

Перед псевдокодом используются следующие обозначения:

- `arrival_rate` — текущая интенсивность входного потока, то есть сколько событий поступает в среднем за секунду.
- `target_window` — желаемая длительность открытой эпохи в секундах.
- `ack_latency` — время подтверждения записи эпохи во внешнее хранилище.
- `ack_target` — нормальное ожидаемое время такого подтверждения.
- `cpu_load` — текущая загрузка вычислительного узла, на котором выполняется алгоритм.
- `queue_fill` — степень заполнения очереди входящих событий.
- `base_target` — базовый размер эпохи в событиях, рассчитанный из входного потока.
- `scaled_target` — размер эпохи после поправок по телеметрии.
- `min_epoch_events` и `max_epoch_events` — нижняя и верхняя границы эпохи по числу событий.
- `min_window_seconds` и `max_window_seconds` — нижняя и верхняя границы по длительности открытой эпохи.
- `min_epoch` и `max_epoch` — итоговые границы эпохи после объединения ограничений по событиям и времени.
- `current_target` — текущий размер эпохи до пересчета.
- `candidate` — новый кандидатный размер эпохи.
- `policy_change_threshold` — минимальное относительное изменение размера эпохи, при котором политика действительно перенастраивается.
- `data_criticality` — оценка критичности текущих данных.
- `criticality_threshold` — порог, после которого данные считаются критичными.
- `event_count` — число событий, уже накопленных в текущей эпохе.

### Фиксированная политика

Для фиксированной политики размер эпохи задается заранее и не меняется в ходе прогона:

```text
target_fixed = epoch_size
```

Эпоха закрывается, когда число событий в ней достигает `target_fixed`.

### Адаптивная политика

Адаптивная политика сначала оценивает базовый размер эпохи по интенсивности входного потока:

```text
base_target = round(arrival_rate * target_window)
```

Дальше этот размер модифицируется телеметрией:

```text
scaled_target = base_target
```

Если подтверждение записи стало медленнее нормы:

```text
scaled_target *= 1 + min(
  (ack_latency / ack_target - 1) * policy_ack_latency_scale,
  policy_ack_latency_cap
)
```

Если выросла загрузка CPU:

```text
if cpu_load > policy_cpu_load_trigger:
  scaled_target *= 1 + min(
    (cpu_load - policy_cpu_load_trigger) / policy_cpu_load_scale,
    policy_cpu_load_cap
  )
```

Если очередь близка к насыщению, target наоборот уменьшается:

```text
if queue_fill > policy_queue_fill_trigger:
  scaled_target *= max(policy_queue_fill_min_scale, 1 - queue_fill)
```

После этого новый target ограничивается диапазоном:

```text
candidate = clamp(round(scaled_target), min_epoch, max_epoch)
```

Здесь:
- `min_epoch` это максимум из `min_epoch_events` и ограничения, полученного из `min_window_seconds`;
- `max_epoch` это минимум из `max_epoch_events` и ограничения, полученного из `max_window_seconds`.

Эти дополнительные ограничения применяются только к адаптивной политике.
Фиксированная политика всегда использует ровно заданный `epoch_size`.

Чтобы политика не дрожала на малом шуме, применяется гистерезис:

```text
delta_ratio = abs(candidate - current_target) / max(1, current_target)
next_target = candidate if delta_ratio > policy_change_threshold else current_target
```

### Досрочное закрытие эпохи

Адаптивная политика может закрыть эпоху раньше заполнения, если выполняется хотя бы одно условие:

- пришло критичное событие;
- детектор аномалий по скользящему окну пометил телеметрию как аномальную;
- `data_criticality >= criticality_threshold`;
- `queue_fill >= policy_queue_close_threshold`;
- `cpu_load >= policy_cpu_close_threshold`;
- `ack_latency >= policy_ack_close_multiplier * ack_target`.

Итоговое правило:

```text
should_close = early_close_condition or event_count >= next_target
```

## Детектирование аномалий по скользящему окну

Для `ack_latency`, `cpu_load`, `queue_fill` и `data_value` хранится окно последних `telemetry_window_size` значений.

По окну считаются:

```text
mean = average(window)
std = pstdev(window)
```

Новое значение считается аномалией, если:

```text
abs(value - mean) > anomaly_sigma_threshold * std
```

Если `std` почти нулевое, любое ненулевое отклонение от среднего тоже считается аномалией.

## Метрики

Основные метрики безопасности:

- `avg_vulnerability_window`
- `p95_vulnerability_window`
- `max_vulnerability_window`

Дополнительные метрики накладных расходов:

- `commit_frequency`
- `max_queue_depth`
- `p95_queue_depth`
- `throughput`
- `lost_events`
- `avg_proof_hashes`
- `avg_proof_bytes`

Смысл окна уязвимости:

```text
vulnerability_window = commit_time - event.arrival_time
```

## Основные параметры

Это верхнеуровневые параметры, которыми обычно имеет смысл управлять при исследовании.

| env | значение по умолчанию | смысл |
| --- | ---: | --- |
| `IYC_TELEMETRY_WINDOW_SIZE` | `5` | размер окна для детектирования аномалий |
| `IYC_ANOMALY_SIGMA_THRESHOLD` | `3.0` | порог аномалии в единицах стандартного отклонения |
| `IYC_CRITICALITY_THRESHOLD` | `0.95` | критичность, при которой адаптивная политика закрывает эпоху немедленно |
| `IYC_MIN_EPOCH_EVENTS` | `0` | минимальное число событий в эпохе, если ограничение нужно |
| `IYC_MAX_EPOCH_EVENTS` | `inf` | максимальное число событий в эпохе, если ограничение нужно |
| `IYC_MIN_WINDOW_SECONDS` | `0` | минимальная длительность открытой эпохи в секундах |
| `IYC_MAX_WINDOW_SECONDS` | `inf` | максимальная длительность открытой эпохи в секундах |
| `IYC_POLICY_CHANGE_THRESHOLD` | `0.15` | минимальное относительное изменение `target` для перенастройки |
| `IYC_POLICY_ACK_TARGET` | `1.0` | нормальная задержка подтверждения записи |

## Дополнительные параметры

Это коэффициенты более низкого уровня. Обычно они нужны для тонкого тюнинга, а не для первого запуска.

| env | значение по умолчанию | смысл |
| --- | ---: | --- |
| `IYC_POLICY_ACK_LATENCY_SCALE` | `0.15` | сила реакции на ухудшение `ack_latency` |
| `IYC_POLICY_ACK_LATENCY_CAP` | `0.20` | максимум увеличения `target` из-за `ack_latency` |
| `IYC_POLICY_CPU_LOAD_TRIGGER` | `0.8` | порог, после которого CPU влияет на `target` |
| `IYC_POLICY_CPU_LOAD_SCALE` | `0.3` | чувствительность к загрузке CPU после порога |
| `IYC_POLICY_CPU_LOAD_CAP` | `0.10` | максимум увеличения `target` из-за CPU |
| `IYC_POLICY_QUEUE_FILL_TRIGGER` | `0.8` | порог, после которого очередь начинает уменьшать `target` |
| `IYC_POLICY_QUEUE_FILL_MIN_SCALE` | `0.25` | минимальный коэффициент уменьшения при высокой очереди |
| `IYC_POLICY_QUEUE_CLOSE_THRESHOLD` | `0.9` | жесткий порог раннего закрытия по очереди |
| `IYC_POLICY_CPU_CLOSE_THRESHOLD` | `0.95` | жесткий порог раннего закрытия по CPU |
| `IYC_POLICY_ACK_CLOSE_MULTIPLIER` | `2.5` | жесткий порог раннего закрытия по `ack_latency` |
| `IYC_SEGMENT_ACK_LATENCY` | `1.0` | значение `ack_latency` по умолчанию для сегмента без явного поля |
| `IYC_SEGMENT_CPU_LOAD` | `0.2` | значение `cpu_load` по умолчанию для сегмента без явного поля |
| `IYC_SEGMENT_QUEUE_FILL` | `0.1` | значение `queue_fill` по умолчанию для сегмента без явного поля |
| `IYC_SIMULATOR_DATA_VALUE` | `1.0` | масштаб синтетического `data_value` |
| `IYC_SIMULATOR_CRITICALITY_DEFAULT` | `0.1` | критичность обычного синтетического события |
| `IYC_SIMULATOR_CRITICALITY_CRITICAL` | `1.0` | критичность синтетического критичного события |

## Пример ограничений

Пусть текущий поток равен `5` событий в секунду.

Если заданы:
- `min_epoch_events = 3`
- `max_epoch_events = 50`
- `min_window_seconds = 2`
- `max_window_seconds = 6`

то временные ограничения переводятся так:
- минимальная временная граница: `2 * 5 = 10` событий;
- максимальная временная граница: `6 * 5 = 30` событий.

Итоговый рабочий диапазон эпохи:
- нижняя граница: `max(3, 10) = 10`;
- верхняя граница: `min(50, 30) = 30`.

То есть policy сможет выбрать только размер эпохи от `10` до `30` событий.

## Значения по умолчанию

Значения по умолчанию подобраны с приоритетом безопасности.

Их смысл:
- реакция на `ack_latency` и `cpu_load` ограничена, чтобы рост нагрузки не приводил к чрезмерному раздуванию эпох;
- `policy_change_threshold` подавляет мелкие перестройки размера эпохи;
- `criticality_threshold` и пороги `early close` делают политику чувствительной к критичным данным и явным аномалиям;
- ограничения `min_epoch_events`, `max_epoch_events`, `min_window_seconds`, `max_window_seconds` по умолчанию не сужают диапазон и включаются только при явной настройке.

При необходимости эти параметры можно изменить через env-переменные под конкретный экспериментальный сценарий.

## Сценарии

- `configs/steady.json`
- `configs/burst.json`
- `configs/storage-degradation.json`
- `configs/cpu-pressure.json`
- `configs/queue-saturation.json`
- `configs/combined-stress.json`
- `configs/critical-event-injection.json`
