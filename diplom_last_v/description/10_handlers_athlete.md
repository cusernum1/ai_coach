# app/bot/handlers/athlete.py — Онбординг и команды спортсмена

## За что отвечает файл

Обрабатывает весь «путь спортсмена»:
1. **Анкета** (онбординг): возраст → спорт → уровень → цель → кол-во тренировок
2. **Кнопки главного меню**: 📋 План, 🍎 Питание, 💪 Самочувствие
3. **Команды**: `/plan`, `/nutrition`, `/checkin`

## Код с объяснениями

### Константы — варианты ответов

```python
SPORTS = ["Бег", "Плавание", "Велоспорт", "Футбол",
          "Баскетбол", "Тяжёлая атлетика", "Теннис", "Другое"]
LEVELS = ["Начинающий", "Любитель", "Полупрофессионал", "Профессионал"]
GOALS = ["Похудение", "Набор мышечной массы", "Выносливость",
         "Подготовка к соревнованиям", "Общая физическая форма"]
```
Заранее определённые списки вариантов для inline-кнопок анкеты.

### Вспомогательная функция клавиатуры

```python
def _choice_kb(items: list[str], prefix: str) -> InlineKeyboardMarkup:
    """Вертикальная inline-клавиатура выбора из фиксированного списка."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=item, callback_data=f"{prefix}:{item}")]
            for item in items
        ]
    )
```
Генерирует вертикальный список кнопок из переданного списка. `callback_data=f"{prefix}:{item}"` → например `"sport:Бег"`.

---

### Шаги онбординга

#### Шаг 1: Возраст

```python
@router.message(AthleteOnboarding.waiting_age)
async def ob_age(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (10 <= int(text) <= 80):
        await message.answer("Нужно число от 10 до 80. Попробуй снова.")
        return
    await state.update_data(age=int(text))
    await message.answer("Выбери вид спорта:", reply_markup=_choice_kb(SPORTS, "sport"))
    await state.set_state(AthleteOnboarding.waiting_sport)
```
- `AthleteOnboarding.waiting_age` — фильтр: обрабатываем только пока пользователь в этом состоянии
- `text.isdigit()` — проверяем что введено число
- `10 <= int(text) <= 80` — проверяем диапазон (валидация)
- `state.update_data(age=...)` — сохраняем возраст в FSM-хранилище
- `state.set_state(waiting_sport)` — переходим к следующему шагу

#### Шаги 2-4: Спорт, Уровень, Цель

```python
@router.callback_query(AthleteOnboarding.waiting_sport, F.data.startswith("sport:"))
async def ob_sport(cb: CallbackQuery, state: FSMContext) -> None:
    sport = cb.data.split(":", 1)[1]
    await state.update_data(sport=sport)
    await cb.message.edit_text(f"Вид спорта: <b>{sport}</b>")
    await cb.message.answer("Твой уровень?", reply_markup=_choice_kb(LEVELS, "level"))
    await state.set_state(AthleteOnboarding.waiting_level)
    await cb.answer()

@router.callback_query(AthleteOnboarding.waiting_level, F.data.startswith("level:"))
async def ob_level(cb: CallbackQuery, state: FSMContext) -> None:
    level = cb.data.split(":", 1)[1]
    await state.update_data(level=level)
    await cb.message.edit_text(f"Уровень: <b>{level}</b>")
    await cb.message.answer("Какая у тебя цель?", reply_markup=_choice_kb(GOALS, "goal"))
    await state.set_state(AthleteOnboarding.waiting_goal)
    await cb.answer()

@router.callback_query(AthleteOnboarding.waiting_goal, F.data.startswith("goal:"))
async def ob_goal(cb: CallbackQuery, state: FSMContext) -> None:
    goal = cb.data.split(":", 1)[1]
    await state.update_data(goal=goal)
    await cb.message.edit_text(f"Цель: <b>{goal}</b>")
    await cb.message.answer("Сколько тренировок в неделю планируешь? (1–7)")
    await state.set_state(AthleteOnboarding.waiting_sessions)
    await cb.answer()
```
- `cb: CallbackQuery` — явный тип аргумента. `CallbackQuery` — это объект нажатия inline-кнопки в Telegram (в отличие от `Message` — обычного текстового сообщения)
- `F.data.startswith("sport:")` — фильтр: только кнопки с префиксом `"sport:"`
- `cb.data.split(":", 1)[1]` — берём часть после двоеточия: `"sport:Бег"` → `"Бег"`. Число `1` — ограничение: максимум 1 разбиение (защита если значение содержит `:`)
- `cb.message.edit_text(...)` — редактируем предыдущее сообщение (убираем кнопки, показываем выбор)
- `await cb.answer()` — обязательный вызов! Без него у пользователя в Telegram кружится «загрузка» на кнопке вечно. Отвечает серверу Telegram «ок, нажатие получено»

#### Шаг 5: Количество тренировок + сохранение

```python
@router.message(AthleteOnboarding.waiting_sessions)
async def ob_sessions(message: Message, state: FSMContext, user: User) -> None:
    sessions = int(text)
    data = await state.get_data()   # получаем всё накопленное: age, sport, level, goal
    
    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        await update_athlete_profile(
            s, athlete.id,
            age=data.get("age"),
            sport=data.get("sport"),
            level=data.get("level"),
            goal=data.get("goal"),
            sessions_per_week=sessions,
        )
    
    await state.clear()
    await message.answer("Отлично, анкета сохранена! 💪\n...", reply_markup=athlete_main_kb())
```
- `state.get_data()` — получаем все сохранённые шаги (age, sport, level, goal)
- Сохраняем всё в БД одним вызовом `update_athlete_profile()`
- `state.clear()` — завершаем диалог онбординга

---

### Команда `/plan`

```python
@router.message(F.text == "📋 План")
async def btn_plan(message: Message, user: User) -> None:
    await _plan_flow(message, user, weeks=1)

@router.message(Command("plan"))
async def cmd_plan(message: Message, user: User) -> None:
    parts = (message.text or "").split()
    weeks = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    await _plan_flow(message, user, weeks=max(1, min(4, weeks)))
```
Два обработчика ведут в одну функцию `_plan_flow()`. `/plan 2` → на 2 недели.

```python
async def _plan_flow(message, user, weeks):
    ...
    await message.answer("⏳ Формирую план…")
    
    response = await run_agent(
        f"Составь план тренировок на {weeks} нед.",
        athlete={...профиль спортсмена...},
        brand_name=brand,
        base_program=base_program,
    )
    
    # Сохраняем план в БД
    async with get_session() as s:
        await add_plan(s, athlete.id, title=..., content=response, weeks=weeks)
    
    for part in chunk_text(response):
        await message.answer(part)
```
1. Показываем «⏳ подождите»
2. Вызываем LLM-агент → он генерирует план
3. Сохраняем план в таблицу `plans`
4. Разбиваем на куски и отправляем

---

### Питание и Самочувствие

```python
@router.message(F.text == "🍎 Питание")
@router.message(Command("nutrition"))
async def cmd_nutrition(message, user):
    ...
    response = await run_agent("Дай рекомендации по питанию...", athlete={...})
```
Аналогично плану, но другой инструмент агента (`nutrition_recommendation`).

```python
@router.message(F.text == "💪 Самочувствие")
@router.message(Command("checkin"))
async def cmd_checkin(message, state, user):
    from app.bot.keyboards import scale_kb
    await message.answer("Оцени усталость (1-10):", reply_markup=scale_kb("fatigue"))
    await state.set_state(DailyPoll.waiting_fatigue)
```
Вход в ежедневный опрос — переходим в состояние `waiting_fatigue`, дальше обрабатывает `handlers/poll.py`.

## Паттерны в файле

- **Двойная декорация** `@router.message(F.text == "📋 План")` + `@router.message(Command("plan"))` — один handler на два разных триггера
- **FSM через state.update_data()** — накапливаем данные по шагам, в конце сохраняем всё сразу
- **Разделение логики**: handler → `_plan_flow()` — вынесено в отдельную функцию для переиспользования
