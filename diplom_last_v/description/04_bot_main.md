# app/bot/main.py — Создание бота и диспетчера

## За что отвечает файл

Здесь «собирается» Telegram-бот: создаётся объект бота с токеном, настраивается диспетчер, подключаются все обработчики сообщений и мидлвары. Запуск (polling) происходит через `run_bot()`, которую вызывает `app/main.py`.

## Код с объяснениями

### Импорты

```python
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
```
- `Bot` — объект для отправки сообщений в Telegram
- `Dispatcher` — менеджер, который знает какому обработчику передать каждое сообщение
- `DefaultBotProperties` — настройки по умолчанию для всех сообщений бота
- `ParseMode.HTML` — бот по умолчанию понимает HTML-теги (`<b>`, `<i>`) в тексте
- `MemoryStorage` — FSM-хранилище в оперативной памяти (состояния диалогов)

---

### Функция `build_bot()`

```python
def build_bot() -> Bot:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. "
            "Получите токен у @BotFather и пропишите в .env."
        )
```
Сначала проверяем — есть ли токен. Если нет — сразу падаем с понятным сообщением (fail-fast).

```python
    return Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
```
Создаём бота. `ParseMode.HTML` — все сообщения по умолчанию могут содержать HTML-теги. Например, `<b>текст</b>` будет жирным.

---

### Функция `build_dispatcher()`

```python
def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
```
Создаём диспетчер с хранилищем состояний в памяти. FSM (Finite State Machine, конечный автомат) — механизм aiogram для многошаговых диалогов. `MemoryStorage` хранит состояния в RAM — при перезапуске бота все незавершённые диалоги теряются (ограничение MVP).

```python
    mw = UserContextMiddleware()
    dp.message.middleware(mw)
    dp.callback_query.middleware(mw)
    dp.pre_checkout_query.middleware(mw)
```
Регистрируем `UserContextMiddleware` на три типа обновлений:
- `message` — обычные сообщения
- `callback_query` — нажатия inline-кнопок
- `pre_checkout_query` — предзапрос перед оплатой

Мидлвара выполняется **перед** каждым обработчиком и кладёт в него объект `user` из БД.

```python
    dp.include_router(setup_routers())
    return dp
```
Подключаем все роутеры (обработчики) одним вызовом `setup_routers()` из `handlers/__init__.py`.

---

### Функция `run_bot()`

```python
async def run_bot(bot: Bot, dp: Dispatcher) -> None:
    """Запустить long polling Telegram."""
    logger.info(f"Bot polling started as @{(await bot.me()).username}")
```
`bot.me()` — API-запрос к Telegram, получаем имя нашего бота. Логируем для подтверждения старта.

```python
    await dp.start_polling(bot, drop_pending_updates=True)
```
**Long polling** — бот регулярно спрашивает Telegram: «есть ли новые сообщения?». Это бесконечный цикл.

`drop_pending_updates=True` — при перезапуске бота игнорируем накопившиеся сообщения. Пользователю не придёт ответ на сообщение, отправленное пока бот был выключен.

## Ключевые термины

- **Long polling** — метод получения обновлений: бот периодически «опрашивает» сервера Telegram. Альтернатива — webhook (Telegram сам присылает обновления).
- **Dispatcher** — «маршрутизатор», решает какой handler обработает данное сообщение.
- **FSM (Finite State Machine)** — конечный автомат для многошаговых диалогов (анкета, опрос).
- **MemoryStorage** — состояния FSM в оперативной памяти (теряются при перезапуске).
- **Middleware** — «перехватчик» который выполняется перед каждым обработчиком.
