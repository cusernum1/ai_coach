# app/bot/handlers/common.py — /start, /help, /profile

## За что отвечает файл

Обрабатывает три базовые команды, доступные **всем** пользователям независимо от роли:
- `/start` — приветствие и выбор роли
- `/help` — список доступных команд
- `/profile` — просмотр своего профиля

## Код с объяснениями

### Создание роутера

```python
router = Router(name="common")
```
Каждый файл обработчиков создаёт свой `Router`. Все роутеры потом объединяются в `handlers/__init__.py`. `name="common"` — для отладки.

---

### Обработчик `/start`

```python
@router.message(CommandStart())
async def cmd_start(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
```
- `@router.message(CommandStart())` — фильтр: срабатывает только на команду `/start`
- `user: User | None` — объект пользователя из БД (подставлен мидлварой, может быть `None`)
- `state: FSMContext` — объект для работы с FSM
- `await state.clear()` — сбрасываем любое незавершённое состояние (напр. прерванную анкету)

```python
    if user is None:
        await message.answer("Произошла ошибка. Попробуйте снова.")
        return
```
Защита от неожиданного `None`. Обычно не происходит, но лучше проверить.

```python
    brand = config.BOT_NAME
    welcome = f"Привет! Я — <b>{brand}</b>."
    async with get_session() as s:
        fresh = await get_user_with_profile(s, user.telegram_id)
```
Загружаем пользователя заново из БД внутри новой сессии. Это нужно чтобы получить актуальные связи (`coach`, `athlete`).

```python
        if fresh and fresh.role == Role.COACH:
            await message.answer(
                f"С возвращением, тренер <b>{fresh.full_name or 'coach'}</b>! ...",
                reply_markup=coach_main_kb(),
            )
            return
```
Если пользователь уже тренер — показываем его меню и выходим (`return`).

```python
        if fresh and fresh.role == Role.ATHLETE:
            if fresh.athlete and fresh.athlete.coach_id:
                cfg = await get_coach_config(s, fresh.athlete.coach_id)
                if cfg:
                    welcome = f"Привет! Я — <b>{cfg.brand_name}</b>.\n\n{cfg.welcome_message}"
            await message.answer(welcome, reply_markup=athlete_main_kb())
            return
```
Если спортсмен — берём приветствие из настроек тренера (бренд-нейм). Персонализация!

```python
    # Роль ещё не выбрана
    await message.answer(
        welcome + "\n\nВыбери, кто ты:",
        reply_markup=role_choice_kb(),
    )
```
Новый пользователь (роль `UNKNOWN`) — предлагаем выбрать кто он.

---

### Обработчики выбора роли

```python
@router.callback_query(F.data == "role:coach")
async def on_role_coach(cb: CallbackQuery, user: User) -> None:
```
`@router.callback_query` — срабатывает на нажатие inline-кнопки. `F.data == "role:coach"` — фильтр по данным кнопки.

```python
    async with get_session() as s:
        fresh = await get_user_with_profile(s, user.telegram_id)
        await set_role(s, fresh, Role.COACH)
    await cb.message.answer("...", reply_markup=coach_main_kb())
    await cb.answer()
```
- Устанавливаем роль COACH в БД
- Отправляем подтверждение с меню тренера
- `await cb.answer()` — обязательно! Убирает «часики» у нажатой кнопки

```python
@router.callback_query(F.data == "role:athlete")
async def on_role_athlete(cb: CallbackQuery, user: User, state: FSMContext) -> None:
    async with get_session() as s:
        await set_role(s, fresh, Role.ATHLETE)
        if fresh.athlete:
            await attach_athlete_to_default_coach(s, fresh.athlete)

    await cb.message.answer("Отлично! Давай соберу твою анкету...\n\nСколько тебе лет? (число 10–80)")
    await state.set_state(AthleteOnboarding.waiting_age)
```
После выбора роли спортсмена — сразу переходим в состояние `waiting_age` и начинаем анкету.

---

### Обработчик `/help`

```python
@router.message(Command("help"))
async def cmd_help(message: Message, user: User | None) -> None:
    common_cmds = (
        "/start — перезапустить бота\n"
        "/help — эта справка\n"
        "/profile — твой профиль\n"
    )
    if user and user.role == Role.COACH:
        extra = "\n<b>Команды тренера:</b>\n/settings...\n/athletes..."
        await message.answer(common_cmds + extra)
        return
    if user and user.role == Role.ATHLETE:
        extra = "\n<b>Команды спортсмена:</b>\n/plan...\n/log..."
        await message.answer(common_cmds + extra)
        return
    await message.answer(common_cmds + "\nСначала выбери роль через /start.")
```
Показывает разные команды в зависимости от роли пользователя.

---

### Обработчик `/profile`

```python
@router.message(Command("profile"))
async def cmd_profile(message: Message, user: User | None) -> None:
    ...
    lines = [
        f"<b>Имя:</b> {user.full_name or '—'}",
        f"<b>Username:</b> @{user.username}" if user.username else "",
        f"<b>Роль:</b> {role}",
    ]
    if user.athlete:
        a = user.athlete
        lines += [
            f"Возраст: {a.age or '—'}",
            f"Вид спорта: {a.sport or '—'}",
            ...
        ]
    await message.answer("\n".join(l for l in lines if l))
```
Формируем текст профиля из полей объекта `user`. `or '—'` — если поле пустое, показываем прочерк. `if l` — пропускаем пустые строки.

## Ключевые паттерны

- `return` после `await message.answer()` — важно! Без `return` выполнение продолжится.
- `await cb.answer()` — обязательно для callback_query, иначе Telegram ждёт подтверждения.
- `F.data == "role:coach"` — фильтр aiogram для callback_data.
