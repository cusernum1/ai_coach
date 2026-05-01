# app/bot/handlers/coach.py — Команды тренера

## За что отвечает файл

Все возможности тренера через бот:
- `/settings` — настройки бота (бренд, программа, цена, время опроса)
- `/athletes` — список спортсменов
- `/stats` — статистика
- `/payments` — история оплат
- `/broadcast` — рассылка всем спортсменам
- `/base` — быстрая установка базовой программы
- `/setprice` — установить цену подписки
- `/dashboard` — ссылка на веб-дашборд

## Код с объяснениями

### Вспомогательная функция проверки роли

```python
def _is_coach(user: User | None) -> bool:
    return bool(user and user.role == Role.COACH and user.coach)
```
Проверяем три условия: пользователь существует, роль COACH, и у него есть профиль тренера в БД. Используется в начале каждого handler'а.

---

### Словарь меток настроек

```python
SETTING_LABELS = {
    "brand_name": "название бота",
    "logo_url": "URL логотипа",
    "welcome_message": "приветственное сообщение",
    "base_program": "базовая программа",
    "subscription_price": "цена подписки (в копейках, напр. 99900 = 999₽)",
    "daily_poll_time": "время ежедневного опроса (HH:MM)",
}
```
Словарь: `"field_name"` → человекочитаемое название. Используется в подсказках и подтверждениях.

---

### `/settings` — текущие настройки + кнопки изменения

```python
@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки бота")
async def cmd_settings(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Команда доступна только тренеру.")
        return
    cfg = user.coach.config
    text = (
        "<b>Текущие настройки:</b>\n"
        f"🏷 Название: {cfg.brand_name}\n"
        f"💰 Цена: {money(cfg.subscription_price, config.PAYMENTS_CURRENCY)}\n"
        ...
    )
    await message.answer(text, reply_markup=coach_settings_kb())
```
Показывает текущие значения и кнопки для изменения каждого поля.

---

### Обработчик нажатия кнопки настройки

```python
@router.callback_query(F.data.startswith("set:"))
async def on_set_field(cb: CallbackQuery, state: FSMContext, user: User) -> None:
    field = cb.data.split(":", 1)[1]   # "set:brand_name" → "brand_name"
    if field not in SETTING_LABELS:
        await cb.answer("Неизвестное поле")
        return
    await state.set_state(CoachSettings.waiting_value)
    await state.update_data(field=field)
    await cb.message.answer(
        f"Введи новое значение — <i>{SETTING_LABELS[field]}</i>:\n"
        "Чтобы отменить — отправь /cancel."
    )
```
При нажатии кнопки (например «🏷 Название») — переходим в состояние ожидания ввода, сохраняем какое поле редактируем.

---

### Сохранение настройки

```python
@router.message(CoachSettings.waiting_value)
async def save_setting(message: Message, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    field = data.get("field")
    value = (message.text or "").strip()
    
    # Валидация по типу поля
    if field == "subscription_price":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("Нужно положительное число в копейках.")
            return
        value_cast = int(value)
    elif field == "daily_poll_time":
        import re
        if not re.fullmatch(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            await message.answer("Неверный формат. Пример: 08:30")
            return
        value_cast = value
    else:
        value_cast = value
    
    async with get_session() as s:
        await update_coach_config(s, user.coach.id, **{field: value_cast})
    
    await state.clear()
    await message.answer(f"✅ Сохранено поле «{SETTING_LABELS[field]}».", reply_markup=coach_main_kb())
```
- `**{field: value_cast}` — распаковка словаря в именованные аргументы. Если `field="brand_name"`, это эквивалентно `update_coach_config(s, id, brand_name=value_cast)`.
- `re.fullmatch(r"^([01]\d|2[0-3]):[0-5]\d$", value)` — регулярное выражение проверяет формат `HH:MM`.

---

### Рассылка

```python
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, user: User | None, bot: Bot) -> None:
    text = (message.text or "").partition(" ")[2].strip()
    # "/broadcast Привет всем!" → partition(" ") → ("/broadcast", " ", "Привет всем!")
    # [2] → "Привет всем!"
    
    async with get_session() as s:
        rows = await list_athletes(s, coach_id=user.coach.id)
    
    sent, failed = 0, 0
    for a in rows:
        try:
            await bot.send_message(a.user.telegram_id, f"📣 <b>От тренера:</b>\n\n{text}")
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"broadcast failed to {a.id}: {e}")
    
    await message.answer(f"Рассылка: отправлено {sent}, ошибок {failed}.")
```
Отправляем сообщение каждому спортсмену. Ошибки (пользователь заблокировал бота) не останавливают рассылку — просто считаем.

---

### Дашборд

```python
@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message, user: User | None) -> None:
    url = f"{config.WEBAPP_PUBLIC_URL}/coach?tid={user.telegram_id}"
    await message.answer(f"📊 Дашборд тренера: {url}")
```
Генерирует ссылку с `?tid=telegram_id` — по ней FastAPI-сервер идентифицирует тренера (MVP, без настоящей аутентификации).

## Ключевые паттерны

- `bot: Bot` в параметрах handler — aiogram автоматически подставляет объект бота
- `str.partition(" ")` — делит строку на 3 части по первому вхождению символа
- `**{field: value_cast}` — динамические именованные аргументы
- `try/except` в рассылке — продолжаем даже если отправка одному пользователю не удалась
