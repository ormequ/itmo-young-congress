# Адаптивное формирование эпох Merkle-дерева в IoT-системах

## Что есть

- реальные `HMAC` и `Merkle`-вычисления;
- fixed и adaptive политики формирования эпох;
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

## Политики Эпох

### Fixed Policy

Для fixed policy размер эпохи задается заранее и не меняется в ходе прогона:

```latex
target_{mathrm{fixed}} = operatorname{clamp}(epoch_size, min_epoch, max_epoch)
```

Эпоха закрывается, когда число событий в ней достигает `target_fixed`.

### Adaptive Policy

Adaptive policy сначала оценивает базовый размер эпохи по интенсивности входного потока:

```latex
base_target = operatorname{round}(arrival_rate cdot target_window)
```

Дальше этот размер модифицируется телеметрией:

```latex
scaled_target = base_target
```

Если подтверждение записи стало медленнее нормы:

```latex
scaled_target gets scaled_target cdot left(
1 + minleft(
left(frac{ack_latency}{ack_target} - 1right) cdot policy_ack_latency_scale,;
policy_ack_latency_cap
right)
right)
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

```latex
candidate = operatorname{clamp}(
operatorname{round}(scaled_target),;
min_epoch,;
max_epoch
)
```

Чтобы policy не дрожала на малом шуме, применяется hysteresis:

```latex
Delta = frac{|candidate - current_target|}{max(1, current_target)}
```

```latex
next_target =
begin{cases}
candidate, & Delta > policy_change_threshold 
current_target, & text{иначе}
end{cases}
```

### Досрочное Закрытие Эпохи

Adaptive policy может закрыть эпоху раньше заполнения, если выполняется хотя бы одно условие:

- пришло критичное событие;
- rolling anomaly detector пометил телеметрию как аномальную;
- `data_criticality >= criticality_threshold`;
- `queue_fill >= policy_queue_close_threshold`;
- `cpu_load >= policy_cpu_close_threshold`;
- `ack_latency >= policy_ack_close_multiplier * ack_target`.

Итоговое правило:

```latex
should_close = early_close_condition lor (event_count ge next_target)
```

## Rolling Anomaly Detection

Для `ack_latency`, `cpu_load`, `queue_fill` и `data_value` хранится окно последних `telemetry_window_size` значений.

По окну считаются:

```latex
\mu = \operatorname{average}(window), \qquad
\sigma = \operatorname{pstdev}(window)
```

Новое значение считается аномалией, если:

```latex
|value - mu| > anomaly_sigma_threshold cdot sigma
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

```latex
vulnerability_window = commit_time - event.arrival_time
```

## Основные Параметры

Это верхнеуровневые параметры, которыми обычно имеет смысл управлять при исследовании.

| env | default | смысл |
| --- | ---: | --- |
| `IYC_TELEMETRY_WINDOW_SIZE` | `5` | размер окна для rolling anomaly detection |
| `IYC_ANOMALY_SIGMA_THRESHOLD` | `3.0` | порог аномалии в единицах стандартного отклонения |
| `IYC_CRITICALITY_THRESHOLD` | `0.95` | критичность, при которой adaptive закрывает эпоху немедленно |
| `IYC_POLICY_MIN_EPOCH` | `2` | минимальный размер эпохи |
| `IYC_POLICY_MAX_EPOCH_MULTIPLIER` | `4` | верхняя граница epoch size как множитель от nominal |
| `IYC_POLICY_CHANGE_THRESHOLD` | `0.15` | минимальное относительное изменение target для перенастройки |
| `IYC_POLICY_ACK_TARGET` | `1.0` | нормальная задержка подтверждения записи |

## Дополнительные Параметры

Это коэффициенты более низкого уровня. Обычно они нужны для тонкого тюнинга, а не для первого запуска.

| env | default | смысл |
| --- | ---: | --- |
| `IYC_POLICY_MAX_EPOCH_FLOOR` | `8` | нижняя граница для `max_epoch`, если nominal мал |
| `IYC_POLICY_ACK_LATENCY_SCALE` | `0.15` | сила реакции на ухудшение `ack_latency` |
| `IYC_POLICY_ACK_LATENCY_CAP` | `0.20` | максимум увеличения target из-за `ack_latency` |
| `IYC_POLICY_CPU_LOAD_TRIGGER` | `0.8` | порог, после которого CPU влияет на target |
| `IYC_POLICY_CPU_LOAD_SCALE` | `0.3` | чувствительность к CPU-load после порога |
| `IYC_POLICY_CPU_LOAD_CAP` | `0.10` | максимум увеличения target из-за CPU |
| `IYC_POLICY_QUEUE_FILL_TRIGGER` | `0.8` | порог, после которого очередь начинает уменьшать target |
| `IYC_POLICY_QUEUE_FILL_MIN_SCALE` | `0.25` | минимальный коэффициент shrink при высокой очереди |
| `IYC_POLICY_QUEUE_CLOSE_THRESHOLD` | `0.9` | hard-threshold раннего закрытия по очереди |
| `IYC_POLICY_CPU_CLOSE_THRESHOLD` | `0.95` | hard-threshold раннего закрытия по CPU |
| `IYC_POLICY_ACK_CLOSE_MULTIPLIER` | `2.5` | hard-threshold раннего закрытия по `ack_latency` |
| `IYC_SEGMENT_ACK_LATENCY` | `1.0` | fallback `ack_latency` для сегмента без явного поля |
| `IYC_SEGMENT_CPU_LOAD` | `0.2` | fallback `cpu_load` для сегмента без явного поля |
| `IYC_SEGMENT_QUEUE_FILL` | `0.1` | fallback `queue_fill` для сегмента без явного поля |
| `IYC_SIMULATOR_DATA_VALUE` | `1.0` | масштаб synthetic `data_value` |
| `IYC_SIMULATOR_CRITICALITY_DEFAULT` | `0.1` | критичность обычного synthetic события |
| `IYC_SIMULATOR_CRITICALITY_CRITICAL` | `1.0` | критичность synthetic critical event |

## Почему Обновлены Дефолты

Текущие defaults сдвинуты в сторону более безопасного поведения adaptive policy.

Что изменено относительно более раннего набора:

- ослаблена реакция на `ack_latency`, чтобы policy не раздувала эпохи слишком агрессивно;
- ослаблена реакция на `cpu_load`, чтобы high CPU не превращался в рост окна уязвимости;
- увеличен `policy_change_threshold`, чтобы убрать мелкие бессмысленные перестройки;
- повышен `criticality_threshold`, чтобы мгновенное закрытие происходило только на действительно критичных данных;
- снижен `policy_ack_close_multiplier`, чтобы при заметной деградации внешнего хранилища adaptive быстрее закрывала эпоху.

Практический эффект:

- `cpu-pressure` становится мягче по окну уязвимости;
- `storage-degradation` лучше отрабатывается за счет более раннего закрытия;
- цена улучшения в стрессовых сценариях может выражаться в большей `commit_frequency`.

Это намеренный trade-off: текущие defaults ориентированы не на минимальное число фиксаций, а на более безопасное поведение в деградирующих режимах.

## Сценарии

- `configs/steady.json`
- `configs/burst.json`
- `configs/storage-degradation.json`
- `configs/cpu-pressure.json`
- `configs/queue-saturation.json`
- `configs/combined-stress.json`
- `configs/critical-event-injection.json`
