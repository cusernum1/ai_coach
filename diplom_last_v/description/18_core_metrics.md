# app/core/metrics.py — Спортивные метрики (чистая математика)

## За что отвечает файл

Все формулы расчёта спортивных показателей. Файл **не обращается к БД** — только чистые математические функции. Данные передаются снаружи, функции только считают. Это позволяет легко тестировать их без базы данных.

## Код с объяснениями

### `wellness_score()` — Индекс самочувствия

```python
def wellness_score(fatigue: int, sleep: int) -> float:
    """
    Интегральный показатель самочувствия (0–100).
    Формула: (10 - fatigue) × 5 + sleep × 5.
    """
    fatigue = max(1, min(10, int(fatigue)))
    sleep = max(1, min(10, int(sleep)))
    return float((10 - fatigue) * 5 + sleep * 5)
```
`max(1, min(10, fatigue))` — зажимаем значение в диапазон [1, 10]. Защита от некорректного ввода.

**Формула:** `(10 - усталость) × 5 + сон × 5`
- При усталости=1, сне=10: `(10-1)×5 + 10×5 = 45 + 50 = 95` — отлично
- При усталости=10, сне=1: `(10-10)×5 + 1×5 = 0 + 5 = 5` — плохо
- Диапазон: 5 до 95 (теоретически 0-100)

---

### `wellness_label()` — Текстовая метка

```python
def wellness_label(score: float) -> str:
    if score >= 70:
        return "🟢 Отличное"
    if score >= 50:
        return "🟡 Хорошее"
    if score >= 30:
        return "🟠 Среднее"
    return "🔴 Плохое"
```
Интерпретация числа в текст. Используется в сообщении после опроса.

---

### `training_load()` — Тренировочная нагрузка

```python
def training_load(rpe_values: Iterable[int]) -> float:
    """
    Суммарная нагрузка за период (сумма RPE-значений).
    """
    return float(sum(int(v) for v in rpe_values if v))
```
Простейшая метрика: сумма всех RPE за период. Чем больше — тем выше нагрузка.

В полноценной спортивной науке используется `Foster's sRPE = RPE × длительность`, но для диплома упрощено до суммы RPE.

---

### `acwr()` — Коэффициент острой/хронической нагрузки

```python
def acwr(recent_7: list[int], recent_28: list[int]) -> float | None:
    """
    ACWR = среднее за 7 дней / среднее за 28 дней.
    """
    if not recent_7 or not recent_28:
        return None
    avg_7 = sum(recent_7) / len(recent_7)
    avg_28 = sum(recent_28) / len(recent_28)
    if avg_28 == 0:
        return None
    return round(avg_7 / avg_28, 2)
```
**ACWR (Acute:Chronic Workload Ratio)** — научная метрика риска травм (Gabbett, 2016):
- `acute` (острая) — нагрузка за последние 7 дней (что делаешь сейчас)
- `chronic` (хроническая) — нагрузка за последние 28 дней (к чему организм привык)
- `ACWR = acute / chronic`

`return None` если нет данных — честнее чем возвращать 0.

---

### `acwr_zone()` — Зона риска

```python
def acwr_zone(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.8:
        return "Недотренированность"
    if value <= 1.3:
        return "🟢 Оптимальная"
    if value <= 1.5:
        return "🟡 Внимание"
    return "🔴 Высокий риск травмы"
```
Классификация по Gabbett (2016):
- **< 0.8** — нагрузка слишком мала, форма деградирует
- **0.8-1.3** — оптимальная зона
- **1.3-1.5** — нужно внимание
- **> 1.5** — высокий риск перетренировки и травмы

---

### `training_monotony()` — Монотонность нагрузки

```python
def training_monotony(rpe_values: list[int]) -> float | None:
    """
    Training Monotony (Foster): среднее RPE / стандартное отклонение.
    """
    if len(rpe_values) < 2:
        return None
    mean = sum(rpe_values) / len(rpe_values)
    variance = sum((v - mean) ** 2 for v in rpe_values) / len(rpe_values)
    std = variance ** 0.5
    if std == 0:
        return None
    return round(mean / std, 2)
```
**Монотонность** — насколько однообразна нагрузка. Высокое значение → каждый день примерно одинаково → риск перетренированности.

Формула:
1. `mean` — среднее RPE
2. `variance` — дисперсия (среднее квадратов отклонений)
3. `std = √variance` — стандартное отклонение
4. `monotony = mean / std`

`std == 0` → все значения одинаковые → деление на ноль → возвращаем `None`.

## Почему это в отдельном файле

Принцип **разделения ответственности**: формулы не должны знать про Telegram, базу данных или HTTP. Они просто принимают числа и возвращают числа. Это:
1. Легко тестируется (без мока БД — см. `tests/test_core_metrics.py`)
2. Можно использовать и в боте, и в веб-дашборде
3. Легко понять и изменить математику независимо от остального кода

## Ключевые термины для защиты

- **ACWR** — Acute:Chronic Workload Ratio, коэффициент острой/хронической нагрузки
- **RPE** — Rate of Perceived Exertion, субъективная оценка усилия
- **Стандартное отклонение** — мера разброса значений вокруг среднего
- **Монотонность нагрузки** — Foster's Training Monotony
