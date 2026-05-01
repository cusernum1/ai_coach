# app/bot/states.py — Состояния FSM (конечного автомата)

## За что отвечает файл

Когда боту нужно задать пользователю несколько вопросов подряд (например, собрать анкету: возраст → спорт → уровень → цель), нужно «запомнить», на каком вопросе мы остановились. Для этого используется **FSM (Finite State Machine)** — конечный автомат.

Этот файл описывает **все состояния** многошаговых диалогов в боте.

## Код с объяснениями

```python
from aiogram.fsm.state import State, StatesGroup
```
Импортируем строительные блоки FSM из aiogram.

---

### OnBoarding спортсмена

```python
class AthleteOnboarding(StatesGroup):
    """Онбординг спортсмена: сбор анкеты."""
    waiting_age = State()
    waiting_sport = State()
    waiting_level = State()
    waiting_goal = State()
    waiting_sessions = State()
```
Это диалог сбора анкеты нового спортсмена. 5 шагов:
1. `waiting_age` — ждём возраст (число)
2. `waiting_sport` — ждём выбор вида спорта (inline-кнопки)
3. `waiting_level` — ждём уровень подготовки
4. `waiting_goal` — ждём цель тренировок
5. `waiting_sessions` — ждём количество тренировок в неделю

**Как работает:** когда пользователь нажал «Я спортсмен», мы вызываем `state.set_state(AthleteOnboarding.waiting_age)`. Теперь следующее сообщение от этого пользователя попадёт в обработчик с фильтром `AthleteOnboarding.waiting_age` в `handlers/athlete.py`.

---

### Ежедневный опрос

```python
class DailyPoll(StatesGroup):
    """Ежедневный опрос: усталость + сон + заметки."""
    waiting_fatigue = State()
    waiting_sleep = State()
    waiting_notes = State()
```
3 шага утреннего опроса:
1. `waiting_fatigue` — оценка усталости 1-10
2. `waiting_sleep` — оценка сна 1-10
3. `waiting_notes` — текстовая заметка (жалобы, боли)

---

### Журнал тренировок

```python
class TrainingLogFlow(StatesGroup):
    """Добавление записи в журнал тренировок."""
    waiting_name = State()
    waiting_status = State()
    waiting_rpe = State()
    waiting_notes = State()
```
4 шага при записи тренировки:
1. `waiting_name` — название тренировки (текст)
2. `waiting_status` — выполнено/частично/пропущено (inline-кнопки)
3. `waiting_rpe` — воспринимаемое усилие 1-10
4. `waiting_notes` — заметка

---

### Настройки тренера

```python
class CoachSettings(StatesGroup):
    """Тренер меняет настройку через чат."""
    waiting_value = State()
```
Одно состояние — тренер нажал кнопку «изменить поле» и теперь ждём его ввода. Какое именно поле редактируется — хранится отдельно в `state.data["field"]`.

---

## Схема переходов состояний (на примере онбординга)

```
Пользователь нажал «Я спортсмен»
    ↓
set_state(AthleteOnboarding.waiting_age)
    ↓
Пользователь пишет «23»
    → обработчик ob_age() → проверяет, сохраняет
    → set_state(waiting_sport)
    ↓
Пользователь выбирает «Бег»
    → обработчик ob_sport()
    → set_state(waiting_level)
    ↓
... и так далее ...
    ↓
После waiting_sessions → state.clear() → диалог завершён
```

## Ключевые термины

- **FSM (Finite State Machine)** — конечный автомат. В каждый момент пользователь находится в одном из заданных состояний.
- **StatesGroup** — группа состояний одного диалога.
- **State()** — одно состояние (один «шаг» диалога).
- **`state.set_state()`** — перевести пользователя в следующее состояние.
- **`state.clear()`** — завершить диалог, убрать состояние.
- **`MemoryStorage`** — хранит текущее состояние каждого пользователя в оперативной памяти.
