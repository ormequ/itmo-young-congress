# Адаптивное формирование эпох Merkle-дерева в IoT-системах

Python-проект для адаптивного формирования эпох Merkle-дерева в IoT-системах.

## Быстрый старт

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m itmo_young_congress demo-run-scenario --config configs/steady.json --policy adaptive --seed 1 --output-dir artifacts/steady
PYTHONPATH=src python3 -m itmo_young_congress demo-run-batch --config configs/burst.json --seeds 1,2,3 --output-dir artifacts/burst-batch
PYTHONPATH=src python3 -m itmo_young_congress demo-build-report --summary artifacts/burst-batch/batch_summary.json --output-dir artifacts/burst-report
PYTHONPATH=src python3 -m itmo_young_congress demo-stress-test --config configs/burst.json --arrival-rates 2,4,6,8,10,12 --seeds 1,2,3 --commit-latency-limit 5.0 --input-queue-fill-limit 0.9 --output-dir artifacts/stress/burst
PYTHONPATH=src python3 -m itmo_young_congress demo-gateway --config configs/critical-event-injection.json --seed 2 --output artifacts/demo.json
```

## Политики эпох

Используются следующие обозначения:

- `arrival_rate` - текущая интенсивность входного потока, то есть сколько событий поступает в среднем за секунду.
- `target_commit_latency` - целевая задержка фиксации, по которой рассчитывается базовая длительность накопления эпохи.
- `anchor_ack_latency` - время подтверждения записи эпохи во внешнее хранилище.
- `anchor_ack_target` - нормальное ожидаемое время такого подтверждения.
- `cpu_load` - текущая загрузка вычислительного узла, на котором выполняется алгоритм.
- `input_queue_fill` - степень заполнения очереди входящих событий.
- `base_target` - базовый размер эпохи в событиях, рассчитанный из входного потока.
- `scaled_target` - размер эпохи после поправок по телеметрии.
- `min_epoch_events` и `max_epoch_events` - нижняя и верхняя границы эпохи по числу событий.
- `min_epoch_duration_seconds` и `max_epoch_duration_seconds` - нижняя и верхняя границы по длительности открытой эпохи.
- `min_epoch` и `max_epoch` - итоговые границы эпохи после объединения ограничений по событиям и времени.
- `current_target` - текущий размер эпохи до пересчета.
- `candidate` - новый кандидатный размер эпохи.
- `policy_change_threshold` - минимальное относительное изменение размера эпохи, при котором политика действительно перенастраивается.
- `criticality_level` - оценка критичности текущих данных.
- `source_priority` - приоритет источника данных, например аварийная защита или обычная телеметрия.
- `effective_criticality_level` - итоговая критичность с учетом приоритета источника.
- `criticality_threshold` - порог, после которого данные считаются критичными.
- `epoch_event_count` - число событий, уже накопленных в текущей эпохе.
- `epoch_payload_bytes` - суммарный объем payload в открытой эпохе.
- `epoch_buffer_budget_bytes` - бюджет памяти шлюза, выделенный под буфер открытой эпохи.
- `memory_pressure` - доля использования бюджета памяти открытой эпохой.
- `pending_anchor_count` - число уже закрытых эпох, внешняя фиксация которых еще не подтверждена.
- `max_pending_anchors` - допустимое число неподтвержденных внешних фиксаций.

### Фиксированная политика

Для фиксированной политики размер эпохи задается заранее и не меняется в ходе прогона:

```text
target_fixed = epoch_size
```

Эпоха закрывается, когда число событий в ней достигает `target_fixed`.

### Адаптивная политика

Адаптивная политика сначала оценивает базовый размер эпохи по интенсивности входного потока:

```text
base_target = round(arrival_rate * target_commit_latency)
```

Дальше этот размер модифицируется телеметрией:

```text
scaled_target = base_target
```

Если подтверждение записи стало медленнее нормы:

```text
scaled_target *= 1 + min(
  (anchor_ack_latency / anchor_ack_target - 1) * policy_anchor_ack_latency_scale,
  policy_anchor_ack_latency_cap
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
if input_queue_fill > policy_input_queue_fill_trigger:
  scaled_target *= max(policy_input_queue_fill_min_scale, 1 - input_queue_fill)
```

Если объем накопленных payload приближается к бюджету памяти открытой эпохи, target тоже уменьшается:

```text
memory_pressure = epoch_payload_bytes / epoch_buffer_budget_bytes

if memory_pressure > policy_memory_pressure_trigger:
  scaled_target *= max(policy_memory_pressure_min_scale, 1 - memory_pressure)
```

Если внешняя система фиксации не успевает подтверждать закрытые эпохи, target увеличивается:

```text
if pending_anchor_count > max_pending_anchors:
  scaled_target *= 1 + min(
    (pending_anchor_count / max_pending_anchors - 1) * policy_pending_anchor_scale,
    policy_pending_anchor_cap
  )
```

Так в модели появляется конфликт управления: рост `input_queue_fill` заставляет закрывать эпохи чаще, а рост `pending_anchor_count` показывает backpressure внешней фиксации и заставляет закрывать их реже.

После этого новый target ограничивается диапазоном:

```text
candidate = clamp(round(scaled_target), min_epoch, max_epoch)
```

Здесь:
- `min_epoch` это максимум из `min_epoch_events` и ограничения, полученного из `min_epoch_duration_seconds`;
- `max_epoch` это минимум из `max_epoch_events` и ограничения, полученного из `max_epoch_duration_seconds`.

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
- `anomaly_score * source_priority >= anomaly_score_threshold`;
- `effective_criticality_level >= criticality_threshold`;
- `input_queue_fill >= policy_input_queue_close_threshold`;
- `memory_pressure >= 1.0`;
- `cpu_load >= policy_cpu_close_threshold`;

Итоговое правило:

```text
should_close = early_close_condition or epoch_event_count >= next_target
```

## Детектирование аномалий по скользящему окну

Для `anchor_ack_latency`, `cpu_load`, `input_queue_fill` и `data_value` хранится окно последних `telemetry_window_size` значений.

По окну считаются:

```text
mean = average(window)
std = pstdev(window)
```

Для каждого параметра рассчитывается нормированное отклонение:

```text
score = abs(value - mean) / std
```

Итоговый `anomaly_score` равен максимуму таких оценок по наблюдаемым параметрам.
Эпоха может закрываться досрочно, если:

```text
anomaly_score * source_priority >= anomaly_score_threshold
```

Если `std` почти нулевое, любое ненулевое отклонение от среднего считается сильной аномалией.

## Приоритет источника

Для промышленных сценариев у события может быть не только собственная критичность, но и приоритет источника:

```text
effective_criticality_level = min(1.0, criticality_level * source_priority)
```

Это позволяет отличать одинаковые значения телеметрии от разных потоков: событие от источника аварийной защиты может закрыть эпоху раньше, чем событие такой же формы от диагностического потока.

## Метрики

Основные метрики безопасности:

- `avg_commit_latency`
- `p95_commit_latency`
- `max_commit_latency`

Дополнительные метрики накладных расходов:

- `commit_frequency`
- `max_queue_depth`
- `p95_queue_depth`
- `throughput`
- `queue_over_capacity_count`
- `max_epoch_payload_bytes`
- `p95_epoch_payload_bytes`
- `max_pending_anchor_count`
- `p95_pending_anchor_count`
- `avg_proof_hashes`
- `avg_proof_bytes`

Смысл задержки фиксации:

```text
commit_latency = commit_time - event.arrival_time
```

## Основные параметры

Это верхнеуровневые параметры, которыми обычно имеет смысл управлять при исследовании.

| env | значение по умолчанию | смысл |
| --- | ---: | --- |
| `TELEMETRY_WINDOW_SIZE` | `5` | размер окна для детектирования аномалий |
| `ANOMALY_SCORE_THRESHOLD` | `3.0` | порог аномалии в единицах стандартного отклонения |
| `CRITICALITY_THRESHOLD` | `0.95` | критичность, при которой адаптивная политика закрывает эпоху немедленно |
| `MIN_EPOCH_EVENTS` | `0` | минимальное число событий в эпохе, если ограничение нужно |
| `MAX_EPOCH_EVENTS` | `inf` | максимальное число событий в эпохе, если ограничение нужно |
| `MIN_EPOCH_DURATION_SECONDS` | `0` | минимальная длительность открытой эпохи в секундах |
| `MAX_EPOCH_DURATION_SECONDS` | `inf` | максимальная длительность открытой эпохи в секундах |
| `EPOCH_BUFFER_BUDGET_BYTES` | `inf` | бюджет памяти под payload открытой эпохи |
| `MAX_PENDING_ANCHORS` | `inf` | допустимое число неподтвержденных внешних фиксаций |
| `POLICY_CHANGE_THRESHOLD` | `0.15` | минимальное относительное изменение `target` для перенастройки |
| `POLICY_ANCHOR_ACK_TARGET` | `1.0` | нормальная задержка подтверждения записи |

## Дополнительные параметры

Это коэффициенты более низкого уровня. Обычно они нужны для тонкого тюнинга, а не для первого запуска.

| env | значение по умолчанию | смысл |
| --- | ---: | --- |
| `POLICY_ANCHOR_ACK_LATENCY_SCALE` | `0.15` | сила реакции на ухудшение `anchor_ack_latency` |
| `POLICY_ANCHOR_ACK_LATENCY_CAP` | `0.20` | максимум увеличения `target` из-за `anchor_ack_latency` |
| `POLICY_CPU_LOAD_TRIGGER` | `0.8` | порог, после которого CPU влияет на `target` |
| `POLICY_CPU_LOAD_SCALE` | `0.3` | чувствительность к загрузке CPU после порога |
| `POLICY_CPU_LOAD_CAP` | `0.10` | максимум увеличения `target` из-за CPU |
| `POLICY_INPUT_QUEUE_FILL_TRIGGER` | `0.8` | порог, после которого очередь начинает уменьшать `target` |
| `POLICY_INPUT_QUEUE_FILL_MIN_SCALE` | `0.25` | минимальный коэффициент уменьшения при высокой очереди |
| `POLICY_INPUT_QUEUE_CLOSE_THRESHOLD` | `0.9` | жесткий порог раннего закрытия по очереди |
| `POLICY_MEMORY_PRESSURE_TRIGGER` | `0.8` | порог, после которого заполнение буфера эпохи уменьшает `target` |
| `POLICY_MEMORY_PRESSURE_MIN_SCALE` | `0.25` | минимальный коэффициент уменьшения при высоком заполнении буфера эпохи |
| `POLICY_PENDING_ANCHOR_SCALE` | `0.25` | сила реакции на превышение `max_pending_anchors` |
| `POLICY_PENDING_ANCHOR_CAP` | `0.50` | максимум увеличения `target` из-за неподтвержденных фиксаций |
| `POLICY_CPU_CLOSE_THRESHOLD` | `0.95` | жесткий порог раннего закрытия по CPU |
| `SEGMENT_ANCHOR_ACK_LATENCY` | `1.0` | значение `anchor_ack_latency` по умолчанию для сегмента без явного поля |
| `SEGMENT_CPU_LOAD` | `0.2` | значение `cpu_load` по умолчанию для сегмента без явного поля |
| `SEGMENT_INPUT_QUEUE_FILL` | `0.1` | значение `input_queue_fill` по умолчанию для сегмента без явного поля |
| `SEGMENT_SOURCE_PRIORITY` | `1.0` | приоритет источника по умолчанию для сегмента без явного поля |
| `SIMULATOR_DATA_VALUE` | `1.0` | масштаб синтетического `data_value` |
| `SIMULATOR_CRITICALITY_DEFAULT` | `0.1` | критичность обычного синтетического события |
| `SIMULATOR_CRITICALITY_CRITICAL` | `1.0` | критичность синтетического критичного события |

## Пример ограничений

Пусть текущий поток равен `5` событий в секунду.

Если заданы:
- `min_epoch_events = 3`
- `max_epoch_events = 50`
- `min_epoch_duration_seconds = 2`
- `max_epoch_duration_seconds = 6`

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
- реакция на `anchor_ack_latency` и `cpu_load` ограничена, чтобы рост нагрузки не приводил к чрезмерному раздуванию эпох;
- `policy_change_threshold` подавляет мелкие перестройки размера эпохи;
- `criticality_threshold` и пороги `early close` делают политику чувствительной к критичным данным и явным аномалиям;
- ограничения `min_epoch_events`, `max_epoch_events`, `min_epoch_duration_seconds`, `max_epoch_duration_seconds` по умолчанию не сужают диапазон и включаются только при явной настройке.

При необходимости эти параметры можно изменить через env-переменные под конкретный экспериментальный сценарий.

## Сценарии

- `configs/steady.json`
- `configs/burst.json`
- `configs/storage-degradation.json`
- `configs/cpu-pressure.json`
- `configs/queue-saturation.json`
- `configs/combined-stress.json`
- `configs/critical-event-injection.json`
