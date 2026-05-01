# app/bot/handlers/poll.py — Ежедневный опрос самочувствия

## За что отвечает файл

Реализует 3-шаговый ежедневный опрос:
1. Оцени **усталость** (1-10)
2. Оцени **качество сна** (1-10)
3. Напиши **заметку** (или `/skip`)

Опрос запускается двумя способами:
- Планировщиком (`scheduler/jobs.py`) каждое утро
- Вручную кнопкой «💪 Самочувствие» (запускает из `handlers/athlete.py`)

## Код с объяснениями

### Шаг 1: Усталость

```python
@router.callback_query(F.data.startswith("fatigue:"))
async def poll_fatigue(cb: CallbackQuery, state: FSMContext) -> None:
    # Без фильтра состояния!
    value = int(cb.data.split(":")[1])
    await state.update_data(fatigue=value)
    await cb.message.edit_text(f"Усталость: <b>{value}/10</b>")
    await cb.message.answer("Оцени качество сна (1-10):", reply_markup=scale_kb("sleep"))
    await state.set_state(DailyPoll.waiting_sleep)
    await cb.answer()
```
Важный момент: у этого handler **нет фильтра состояния** — в отличие от следующих шагов. Почему? Потому что опрос приходит от планировщика, который не устанавливает FSM-состояние. Когда пользователь нажимает первую кнопку — мы сами его переводим в состояние `waiting_sleep`.

- `cb.data.split(":")[1]` → `"fatigue:7"` → `"7"` → `int("7")` → `7`
- `edit_text()` — редактируем сообщение с кнопками, чтобы показать выбранное значение

---

### Шаг 2: Сон

```python
@router.callback_query(DailyPoll.waiting_sleep, F.data.startswith("sleep:"))
async def poll_sleep(cb: CallbackQuery, state: FSMContext) -> None:
    value = int(cb.data.split(":")[1])
    await state.update_data(sleep=value)
    await cb.message.edit_text(f"Сон: <b>{value}/10</b>")
    await cb.message.answer(
        "Хочешь оставить заметку? Напиши или /skip.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(DailyPoll.waiting_notes)
```
Здесь уже есть фильтр `DailyPoll.waiting_sleep` — только для пользователей в этом состоянии.

`ReplyKeyboardRemove()` — убирает reply-клавиатуру, чтобы пользователь мог ввести текст.

---

### Шаг 3: Заметка + сохранение в БД

```python
@router.message(DailyPoll.waiting_notes)
async def poll_notes(message: Message, state: FSMContext, user: User) -> None:
    notes = "" if (message.text or "").strip() in ("/skip", "-") else (message.text or "").strip()
    data = await state.get_data()
    fatigue, sleep = int(data["fatigue"]), int(data["sleep"])
    await state.clear()
```
Если пользователь написал `/skip` или `-` — сохраняем пустую заметку.

```python
    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        
        # Запись в таблицу sessions (физиологическое состояние)
        await add_session_record(
            s, athlete.id,
            fatigue=fatigue, sleep_quality=sleep,
            results="", pain=notes,
        )
        
        # Запись в таблицу polls + poll_answers
        poll = await create_poll(s, athlete.id, kind="daily")
        await save_poll_answers(s, poll.id, {
            "Усталость (1-10)": str(fatigue),
            "Сон (1-10)": str(sleep),
            "Заметки": notes or "—",
        })
```
Данные сохраняются в **две таблицы**:
- `sessions` — физиологические показатели для метрик
- `polls` + `poll_answers` — для истории опросов

```python
    score = wellness_score(fatigue, sleep)
    label = wellness_label(score)
    await message.answer(
        f"Спасибо! Wellness Score: <b>{score:.0f}/100</b> — {label}.\n"
        f"Усталость {fatigue}/10, сон {sleep}/10.",
        reply_markup=athlete_main_kb(),
    )
```
Считаем Wellness Score и сразу показываем спортсмену результат.

`{score:.0f}` — форматирование числа без знаков после запятой (`.0f` = 0 знаков после запятой, `f` = float).

---

### Обработчик `/skip`

```python
@router.message(F.text == "/skip", DailyPoll.waiting_notes)
async def poll_skip(message: Message, state: FSMContext, user: User) -> None:
    # Дублируем ветку выше с пустой заметкой
    data = await state.get_data()
    fatigue, sleep = int(data["fatigue"]), int(data["sleep"])
    await state.clear()
    ...
```
Отдельный handler для `/skip` — на самом деле `poll_notes` тоже обрабатывает `/skip` через `notes = ""`. Этот handler — избыточная защита на случай если `/skip` придёт без предыдущих шагов.

## Схема потока данных

```
Планировщик/кнопка
    ↓ отправляет scale_kb("fatigue")
Пользователь нажимает 7
    ↓ poll_fatigue: state.update_data(fatigue=7)
    ↓ state.set_state(waiting_sleep)
    ↓ отправляет scale_kb("sleep")
Пользователь нажимает 8
    ↓ poll_sleep: state.update_data(sleep=8)
    ↓ state.set_state(waiting_notes)
Пользователь пишет "болит спина"
    ↓ poll_notes: data = {fatigue:7, sleep:8}
    ↓ add_session_record() + create_poll() + save_poll_answers()
    ↓ wellness_score(7, 8) = 35 → "🟠 Среднее"
    ↓ "Wellness Score: 35/100 — Среднее"
```
