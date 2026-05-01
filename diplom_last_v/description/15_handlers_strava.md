# app/bot/handlers/strava.py — Подключение Strava в боте

## За что отвечает файл

Это тонкая обёртка бота над интеграцией Strava. Бот:
1. `/strava` — генерирует ссылку авторизации в Strava
2. `/sync_strava` — вручную запускает импорт активностей

Сама OAuth-авторизация и сохранение токенов происходит в `integrations/strava.py` и `webapp/server.py` (callback).

## Код с объяснениями

### Команда `/strava` — ссылка авторизации

```python
@router.message(Command("strava"))
@router.message(F.text == "🔗 Strava")
async def cmd_strava(message: Message, user: User | None) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Команда доступна спортсменам.")
        return
    
    if not config.STRAVA_CLIENT_ID or not config.STRAVA_CLIENT_SECRET:
        await message.answer(
            "⚠️ Strava не настроена тренером. "
            "Задайте STRAVA_CLIENT_ID и STRAVA_CLIENT_SECRET в .env."
        )
        return
```
Проверяем: настроены ли ключи Strava. Без них авторизация невозможна.

```python
    url = build_authorize_url(user.telegram_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Подключить Strava", url=url)],
        ]
    )
    await message.answer(
        "Нажми кнопку, чтобы авторизоваться в Strava.\n"
        "После успешной авторизации я начну подтягивать твои активности.",
        reply_markup=kb,
    )
```
`InlineKeyboardButton(text="...", url=url)` — кнопка с **внешней ссылкой** (не callback_data, а url). При нажатии открывает браузер.

`build_authorize_url(user.telegram_id)` — строит URL авторизации Strava с `state=telegram_id`. После авторизации Strava вернёт пользователя на наш `STRAVA_REDIRECT_URI` с этим же `state`, и мы поймём чей токен сохранять.

---

### Команда `/sync_strava` — ручная синхронизация

```python
@router.message(Command("sync_strava"))
async def cmd_sync_strava(message: Message, user: User | None) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Команда доступна спортсменам.")
        return
    
    await message.answer("⏳ Синхронизация…")
    
    try:
        added = await sync_to_training_logs(user.telegram_id)
    except Exception as e:
        await message.answer(f"Ошибка синхронизации: {e}")
        return
    
    if added == 0:
        await message.answer("Новых активностей не найдено (или Strava ещё не подключена).")
    else:
        await message.answer(f"✅ Добавлено {added} активностей в журнал.")
```
Показываем «⏳», вызываем функцию синхронизации, сообщаем результат.

## Полный цикл Strava OAuth

```
1. Пользователь: /strava
2. Бот: генерирует ссылку https://www.strava.com/oauth/authorize?...&state=telegram_id
3. Пользователь нажимает кнопку → открывается браузер → авторизуется в Strava
4. Strava перенаправляет на http://наш-сервер/strava/callback?code=XXX&state=telegram_id
5. FastAPI (webapp/server.py): меняет code на access/refresh токены
6. Токены сохраняются в таблицу strava_tokens
7. Пользователь закрывает браузер, возвращается в Telegram
8. Пользователь: /sync_strava
9. Бот: тянет последние 10 активностей из Strava API
10. Записывает в таблицу training_logs (source="strava")
```
