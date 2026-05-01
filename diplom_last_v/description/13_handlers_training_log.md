# app/bot/handlers/training_log.py — Журнал тренировок

## За что отвечает файл

Позволяет спортсмену **вручную** записать тренировку. 4-шаговый диалог:
1. Название тренировки (текст)
2. Статус выполнения (inline-кнопки: выполнено/частично/пропущено)
3. RPE — воспринимаемое усилие (шкала 1-10)
4. Заметка (текст или `/skip`)

Также умеет показывать журнал за последние 7 дней при команде `/log` без аргументов.

## Код с объяснениями

### Вход в журнал

```python
@router.message(Command("log"))
@router.message(F.text == "📓 Журнал")
async def cmd_log(message: Message, state: FSMContext, user: User | None) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Только для спортсменов.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1 and parts[0].lower() != "📓 журнал":
        async with get_session() as s:
            athlete = await get_athlete_by_user_id(s, user.id)
            logs = await list_training_logs(s, athlete.id, days=7) if athlete else []
        if logs:
            lines = ["<b>Журнал за неделю:</b>"]
            for log in logs:
                lines.append(f"• {log.log_date} — {log.day_name}: {log.status} (RPE {log.rpe})")
            await message.answer("\n".join(lines))
```
`parts = message.text.split(maxsplit=1)` — разделяем по первому пробелу:
- `/log` → `["/ log"]` — len=1, показываем историю
- `/log силовая` → `["/log", "силовая"]` — len=2, можно было бы использовать аргумент (но логика идёт дальше — всегда спрашиваем название)

```python
    await message.answer(
        "Как называлась тренировка? (или /cancel чтобы отменить)",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(TrainingLogFlow.waiting_name)
```
В любом случае начинаем диалог добавления записи.

---

### Отмена

```python
@router.message(Command("cancel"), TrainingLogFlow.waiting_name)
@router.message(Command("cancel"), TrainingLogFlow.waiting_status)
@router.message(Command("cancel"), TrainingLogFlow.waiting_rpe)
@router.message(Command("cancel"), TrainingLogFlow.waiting_notes)
async def cancel_log(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=athlete_main_kb())
```
Один обработчик `/cancel` зарегистрирован для **всех 4 состояний** через множественную декорацию. Если пользователь в любом шаге пишет `/cancel` — сбрасываем и выходим.

---

### Шаги диалога

#### Название

```python
@router.message(TrainingLogFlow.waiting_name)
async def log_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Нужно название (например: «Силовая — верх»).")
        return
    await state.update_data(day_name=name)
    await message.answer("Как выполнена?", reply_markup=training_status_kb())
    await state.set_state(TrainingLogFlow.waiting_status)
```

#### Статус (callback)

```python
@router.callback_query(TrainingLogFlow.waiting_status, F.data.startswith("log_status:"))
async def log_status(cb: CallbackQuery, state: FSMContext) -> None:
    status = cb.data.split(":", 1)[1]    # "log_status:выполнено" → "выполнено"
    await state.update_data(status=status)
    await cb.message.edit_text(f"Статус: <b>{status}</b>")
    await cb.message.answer("Оцени RPE (1–10):", reply_markup=scale_kb("rpe"))
    await state.set_state(TrainingLogFlow.waiting_rpe)
    await cb.answer()
```

#### RPE (callback)

```python
@router.callback_query(TrainingLogFlow.waiting_rpe, F.data.startswith("rpe:"))
async def log_rpe(cb: CallbackQuery, state: FSMContext) -> None:
    rpe = int(cb.data.split(":")[1])
    await state.update_data(rpe=rpe)
    await cb.message.edit_text(f"RPE: <b>{rpe}/10</b>")
    await cb.message.answer("Короткая заметка? /skip чтобы пропустить.")
    await state.set_state(TrainingLogFlow.waiting_notes)
    await cb.answer()
```

#### Заметка + сохранение в БД

```python
@router.message(TrainingLogFlow.waiting_notes)
async def log_notes(message: Message, state: FSMContext, user: User) -> None:
    notes = "" if (message.text or "").strip() in ("/skip", "-") else (message.text or "").strip()
    data = await state.get_data()
    await state.clear()

    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        await add_training_log(
            s, athlete.id,
            log_date=date.today(),
            day_name=data["day_name"],
            status=data["status"],
            rpe=int(data["rpe"]),
            notes=notes,
            source="manual",    # источник: ручной ввод (не Strava)
        )
    await message.answer("✅ Запись в журнал добавлена.", reply_markup=athlete_main_kb())
```
- `date.today()` — текущая дата (не datetime, только дата)
- `source="manual"` — отличаем ручные записи от импортированных из Strava

## Что такое RPE

**RPE (Rate of Perceived Exertion)** — шкала воспринимаемого усилия 1-10. Субъективная оценка насколько тяжёлой была тренировка. Используется в формуле ACWR (тренировочная нагрузка).
- 1-3 — очень легко
- 4-6 — умеренно
- 7-8 — тяжело
- 9-10 — максимальное усилие
