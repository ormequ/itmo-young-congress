# Адаптивное формирование эпох Merkle-дерева в IoT-системах

Python-проект для адаптивного формирования эпох Merkle-дерева в IoT-системах.

## Быстрый старт

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m itmo_young_congress demo-run-scenario --config configs/steady.json --policy adaptive --seed 1 --output-dir artifacts/steady
PYTHONPATH=src python3 -m itmo_young_congress demo-run-batch --config configs/burst.json --seeds 1,2,3 --output-dir artifacts/burst-batch
PYTHONPATH=src python3 -m itmo_young_congress demo-build-report --summary artifacts/burst-batch/batch_summary.json --output-dir artifacts/burst-report
PYTHONPATH=src python3 -m itmo_young_congress demo-stress-test --config configs/burst.json --arrival-rates 2,4,6,8,10,12 --seeds 1,2,3 --commit-latency-limit 5.0 --input-queue-fill-limit 0.9 --output-dir artifacts/stress/burst
PYTHONPATH=src python3 -m itmo_young_congress demo-stress-capacity --config configs/combined-stress.json --policies adaptive,fixed-small,fixed-nominal,fixed-large --arrival-rates 4,6,8,10,12,14 --seeds 1,2,3 --output artifacts/stress_capacity.json
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
  input_queue_cap = base_target * max(policy_input_queue_fill_min_scale, 1 - input_queue_fill)
  scaled_target = min(scaled_target, input_queue_cap)
```

Если объем накопленных payload приближается к бюджету памяти открытой эпохи, target тоже уменьшается:

```text
memory_pressure = epoch_payload_bytes / epoch_buffer_budget_bytes

if memory_pressure > policy_memory_pressure_trigger:
  memory_cap = base_target * max(policy_memory_pressure_min_scale, 1 - memory_pressure)
  scaled_target = min(scaled_target, memory_cap)
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
При этом `input_queue_fill` и `memory_pressure` применяются как верхние ограничения на target, поэтому anchor-backpressure не может отменить сжатие эпохи при заполнении входной очереди или буфера памяти.

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
- достигнуто `max_epoch_duration_seconds`;
- достигнуто `max_epoch_events`;
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
source_priority = clamp(source_priority, 0.5, 2.0)
effective_criticality_level = min(1.0, criticality_level * source_priority)
```

Это позволяет отличать одинаковые значения телеметрии от разных потоков: событие от источника аварийной защиты может закрыть эпоху раньше, чем событие такой же формы от диагностического потока.
Рекомендуемая шкала:

- `0.5` - низкоприоритетный диагностический поток;
- `1.0` - обычный источник;
- `1.5` - важный технологический источник;
- `2.0` - критичный источник.

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
| `SOURCE_PRIORITY_MIN` | `0.5` | минимальный вес источника |
| `SOURCE_PRIORITY_MAX` | `2.0` | максимальный вес источника |
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
- `configs/memory-pressure.json`
- `configs/anchor-backpressure.json`

`memory-pressure` изолирует рост `epoch_payload_bytes / memory_pressure`: задержка внешней фиксации и очередь остаются умеренными, а размер payload в сегментах увеличивается.
`anchor-backpressure` изолирует рост `pending_anchor_count`: payload не раздувается, но `anchor_ack_latency` временно становится большим, из-за чего внешняя фиксация не успевает подтверждать закрытые эпохи.

## Графики для статьи

Все PNG-графики из этого раздела строятся с англоязычными подписями и рассчитаны на вставку в англоязычную статью в IEEE-style оформлении.

`scripts/plot_results.py batch` строит обзорные рисунки по `batch_summary.json`:

- `commit_latency_overview.png` - показывает, что adaptive policy управляет `commit_latency` как freshness/security-метрикой;
- `cost_and_stability_overview.png` - показывает цену фиксации через `commit_frequency`, `p95_queue_depth` и `queue_over_capacity_count`;
- `cost_and_stability_full.png` - расширенная версия с дополнительными cost-метриками;
- `memory_pressure_overview.png` - показывает, что `memory_pressure` ограничивает payload открытой эпохи; payload выводится в KiB;
- `anchor_backpressure_ablation.png` - сравнивает `Adaptive full`, `Adaptive w/o anchor BP`, `Fixed-small` и `Fixed-nominal`; здесь `BP` означает `backpressure`.
- `anchor_backpressure_overview.png` и `anchor_backpressure_full.png` сохраняются как вспомогательные агрегированные графики, но для статьи лучше использовать timeline-график реакции ниже.
- старые `avg_commit_latency.png`, `max_commit_latency.png`, `commit_frequency.png`, `p95_queue_depth.png`, `avg_proof_bytes.png`, `tradeoff.png` также сохраняются.

`scripts/plot_results.py timeline` строит:

- `target_timeline.png`;
- `telemetry_timeline.png`;
- `adaptation_timeline.png` с `arrival_rate`, `anchor_ack_latency`, `next_target`, `input_queue_fill`, `memory_pressure`, `pending_anchor_count` и маркерами `should_close`.
- `backpressure_response_timeline.png` - основной график для anchor backpressure: показывает, как рост `anchor_ack_latency` и `pending_anchor_count` приводит к увеличению adaptive target epoch size и снижению частоты новых root commits.

Для `combined-stress` возможно, что adaptive policy показывает больший `pending_anchor_count`, чем фиксированные политики.
Это ожидаемое поведение, если hard-close и cap-ограничения сохраняют свежесть фиксации при ресурсном давлении: политика закрывает эпохи ради freshness/security, но тем самым временно усиливает anchor backpressure.
В статье это можно формулировать так:

```text
Under combined stress, adaptive policy may produce more pending anchors because hard-close and cap constraints preserve freshness under resource pressure. This illustrates the trade-off between integrity freshness and anchor backpressure.

Adaptive full reduces pending anchors and commit frequency compared with Adaptive w/o anchor BP, at the cost of moderately higher commit latency.
```

`scripts/plot_results.py stress` принимает результат `demo-stress-capacity` и строит:

- `stress_capacity.png`;
- `stress_summary_table.png`.

Safe throughput считается безопасным, если одновременно выполняются условия:

- `p95_commit_latency <= commit-latency-limit`;
- `p95_queue_depth <= queue_capacity * input-queue-fill-limit`;
- `queue_over_capacity_count == 0`;
- `max_pending_anchor_count <= max_pending_anchors`, если в сценарии задан конечный лимит.

Пример полного запуска для статьи:

```bash
mkdir -p artifacts/article/plots

PYTHONPATH=src python3 -m itmo_young_congress demo-run-batch \
  --config configs/steady.json,configs/burst.json,configs/storage-degradation.json,configs/cpu-pressure.json,configs/queue-saturation.json,configs/combined-stress.json,configs/critical-event-injection.json,configs/memory-pressure.json,configs/anchor-backpressure.json \
  --seeds 1,2,3 \
  --output-dir artifacts/article/batch

python3 scripts/plot_results.py batch \
  --summary artifacts/article/batch/batch_summary.json \
  --output-dir artifacts/article/plots

PYTHONPATH=src python3 -m itmo_young_congress demo-stress-capacity \
  --config configs/combined-stress.json \
  --policies adaptive,fixed-small,fixed-nominal,fixed-large \
  --arrival-rates 4,6,8,10,12,14,16 \
  --seeds 1,2,3 \
  --commit-latency-limit 5.0 \
  --input-queue-fill-limit 0.9 \
  --output artifacts/article/stress_capacity.json

python3 scripts/plot_results.py stress \
  --summary artifacts/article/stress_capacity.json \
  --output-dir artifacts/article/plots

PYTHONPATH=src python3 -m itmo_young_congress demo-stress-response \
  --config configs/combined-stress.json \
  --policies adaptive,fixed-nominal,fixed-small \
  --seed 1 \
  --output artifacts/article/combined_trace.json

python3 scripts/plot_results.py timeline \
  --summary artifacts/article/combined_trace.json \
  --output-dir artifacts/article/plots

PYTHONPATH=src python3 -m itmo_young_congress demo-stress-response \
  --config configs/anchor-backpressure.json \
  --policies adaptive,fixed-nominal \
  --seed 1 \
  --output artifacts/article/backpressure_trace.json

python3 scripts/plot_results.py timeline \
  --summary artifacts/article/backpressure_trace.json \
  --output-dir artifacts/article/plots
```
