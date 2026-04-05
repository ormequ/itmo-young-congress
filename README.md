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

## Политики Эпох

### Фиксированная Политика

Для фиксированной политики размер эпохи задается заранее и не меняется в ходе прогона:

$$
target_{\mathrm{fixed}} = \mathrm{clamp}(epoch\_size, min\_epoch, max\_epoch)
$$

Эпоха закрывается, когда число событий в ней достигает `target_fixed`.

Дополнительные ограничения можно задавать отдельно:
- по числу событий: `min_epoch_events`, `max_epoch_events`;
- по длительности открытого окна: `min_window_seconds`, `max_window_seconds`.

Ограничения по времени переводятся в эквивалент событий через текущий `arrival_rate`.
Если заданы оба типа ограничений:
- для нижней границы берется максимум;
- для верхней границы берется минимум.

### Адаптивная Политика

Адаптивная политика сначала оценивает базовый размер эпохи по интенсивности входного потока:

$$
base\_target = \mathrm{round}(arrival\_rate \cdot target\_window)
$$

Дальше этот размер модифицируется телеметрией:

$$
scaled\_target = base\_target
$$

Если подтверждение записи стало медленнее нормы:

$$
scaled\_target \gets scaled\_target \cdot \left(
1 + \min\left(
\left(\frac{ack\_latency}{ack\_target} - 1\right) \cdot policy\_ack\_latency\_scale,\;
policy\_ack\_latency\_cap
\right)
\right)
$$

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

$$
candidate = \mathrm{clamp}(
\mathrm{round}(scaled\_target),\;
min\_epoch,\;
max\_epoch
)
$$

Здесь:
- `min_epoch` это максимум из `min_epoch_events` и ограничения, полученного из `min_window_seconds`;
- `max_epoch` это минимум из `max_epoch_events` и ограничения, полученного из `max_window_seconds`.

Чтобы политика не дрожала на малом шуме, применяется гистерезис:

$$
\Delta = \frac{|candidate - current\_target|}{\max(1, current\_target)}
$$

$$
next\_target =
\begin{cases}
candidate, & \Delta > policy\_change\_threshold \\
current\_target, & \text{иначе}
\end{cases}
$$

### Досрочное Закрытие Эпохи

Адаптивная политика может закрыть эпоху раньше заполнения, если выполняется хотя бы одно условие:

- пришло критичное событие;
- детектор аномалий по скользящему окну пометил телеметрию как аномальную;
- `data_criticality >= criticality_threshold`;
- `queue_fill >= policy_queue_close_threshold`;
- `cpu_load >= policy_cpu_close_threshold`;
- `ack_latency >= policy_ack_close_multiplier * ack_target`.

Итоговое правило:

$$
should\_close = early\_close\_condition \lor (event\_count \ge next\_target)
$$

## Детектирование Аномалий По Скользящему Окну

Для `ack_latency`, `cpu_load`, `queue_fill` и `data_value` хранится окно последних `telemetry_window_size` значений.

По окну считаются:

$$
\mu = \mathrm{average}(window), \qquad
\sigma = \mathrm{pstdev}(window)
$$

Новое значение считается аномалией, если:

$$
|value - \mu| > anomaly\_sigma\_threshold \cdot \sigma
$$

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

$$
vulnerability\_window = commit\_time - event.arrival\_time
$$

## Основные Параметры

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

## Дополнительные Параметры

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

## Пример Ограничений

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

## Значения По Умолчанию

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
