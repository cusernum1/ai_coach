# app/main.py — Главная точка входа

## Назначение файла
Запускает три компонента одновременно: Telegram-бот, FastAPI веб-сервер, планировщик задач.

---

## Построчный разбор

```python
from __future__ import annotations
```
**Строка 1.** Специальный импорт из будущих версий Python. Разрешает использовать современные аннотации типов (`X | None` вместо `Optional[X]`). Ставится первой строкой — обязательное условие.

---

```python
import asyncio
```
**Строка 3.** Стандартная библиотека Python для асинхронного программирования. Без неё невозможно запустить несколько корутин параллельно в одном процессе.

---

```python
import os
```
**Строка 4.** Стандартная библиотека для работы с операционной системой — создание папок, чтение переменных окружения и т.д.

---

```python
import signal
```
**Строка 5.** Стандартная библиотека для перехвата сигналов ОС. Нужна чтобы корректно останавливать бота при нажатии Ctrl+C или команде `kill`.

---

```python
import uvicorn
```
**Строка 7.** Внешняя библиотека — ASGI-сервер. Запускает FastAPI-приложение. Аналог gunicorn, но асинхронный.

---

```python
from loguru import logger
```
**Строка 8.** Внешняя библиотека для красивого логирования. `logger` — готовый объект, через него пишем: `logger.info(...)`, `logger.error(...)`.

---

```python
from app.bot.main import build_bot, build_dispatcher, run_bot
```
**Строка 10.** Импортируем три функции из нашего модуля `app/bot/main.py`:
- `build_bot()` — создаёт объект Bot с токеном
- `build_dispatcher()` — создаёт Dispatcher с роутерами
- `run_bot()` — запускает long polling

---

```python
from app.config import config
```
**Строка 11.** Импортируем **глобальный синглтон** конфигурации. Один объект `config` на всё приложение — в нём все настройки из `.env`.

---

```python
from app.db import init_db
```
**Строка 12.** Функция создания таблиц в БД при первом запуске.

---

```python
from app.scheduler.jobs import build_scheduler
```
**Строка 13.** Функция создания планировщика задач (APScheduler).

---

```python
os.makedirs(config.LOG_DIR, exist_ok=True)
```
**Строка 17.** Создаём папку `logs/` для файлов логов.
- `config.LOG_DIR` = `"logs"` — путь из конфига
- `exist_ok=True` — не бросать ошибку если папка уже существует

---

```python
logger.add(
    f"{config.LOG_DIR}/app_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)
```
**Строки 18-23.** Добавляем вывод логов в файл.
- `f"...app_{{time}}.log"` — `{{time}}` (двойные фигурные скобки) экранирует фигурные скобки в f-строке, loguru подставит дату: `app_2024-01-15_10-30.log`
- `rotation="1 MB"` — создавать новый файл когда текущий достигнет 1 мегабайта
- `retention="7 days"` — удалять файлы старше 7 дней
- `level="INFO"` — писать только сообщения уровня INFO и выше (не DEBUG)

---

```python
async def _run_webapp() -> None:
```
**Строка 26.** Определяем **асинхронную** функцию (prefix `async`). Возвращает `None` (ничего). Нижнее подчёркивание `_` в начале — соглашение: функция «приватная», используется только внутри этого модуля.

---

```python
    """Запуск FastAPI через uvicorn (в текущем event loop)."""
```
**Строка 27.** Строка документации (docstring). Объясняет что делает функция.

---

```python
    from app.webapp.server import app as fastapi_app
```
**Строка 28.** Импорт **внутри функции** (ленивый импорт). FastAPI-приложение импортируется только когда функция вызывается, а не при запуске модуля. `as fastapi_app` — даём псевдоним чтобы не конфликтовало с другими переменными `app`.

---

```python
    uv_config = uvicorn.Config(
        fastapi_app,
        host=config.WEBAPP_HOST,
        port=config.WEBAPP_PORT,
        log_level=config.LOG_LEVEL.lower(),
        loop="asyncio",
        access_log=False,
    )
```
**Строки 30-37.** Создаём конфигурацию uvicorn-сервера:
- `fastapi_app` — наше FastAPI-приложение
- `host="0.0.0.0"` — слушать на всех сетевых интерфейсах (не только localhost)
- `port=8080` — порт из конфига
- `.lower()` — uvicorn ожидает строчные буквы: `"info"`, а не `"INFO"`
- `loop="asyncio"` — **критично**: использовать тот же event loop что и бот, а не создавать новый
- `access_log=False` — не логировать каждый HTTP-запрос (чтобы не засорять логи)

---

```python
    server = uvicorn.Server(uv_config)
```
**Строка 38.** Создаём объект сервера с нашей конфигурацией.

---

```python
    logger.info(f"FastAPI starting on http://{config.WEBAPP_HOST}:{config.WEBAPP_PORT}")
```
**Строка 39.** Пишем в лог адрес где будет доступен веб-дашборд.

---

```python
    await server.serve()
```
**Строка 40.** Запускаем сервер. `await` — ждём завершения (это бесконечный цикл, завершится только при остановке приложения).

---

```python
async def main() -> None:
```
**Строка 43.** Главная асинхронная функция. Возвращает `None`.

---

```python
    # 1) Инициализация БД (create_all — для учебного MVP вместо Alembic)
    await init_db()
```
**Строки 44-45.** `await` — ждём создания таблиц в БД. Это первое что делаем при старте. Если БД недоступна — упадём здесь с понятной ошибкой.

---

```python
    # 2) Aiogram — бот и диспетчер
    bot = build_bot()
    dp = build_dispatcher()
```
**Строки 47-49.** Создаём объект бота (с токеном из `.env`) и диспетчер (с роутерами и middleware). **Не синхронные**, не `await` — это обычные функции, они не делают сетевых запросов.

---

```python
    # 3) Планировщик — подхватывает bot для рассылок
    scheduler = build_scheduler(bot)
```
**Строки 51-52.** Создаём планировщик. Передаём `bot` — планировщику нужен объект бота чтобы отправлять сообщения по расписанию.

---

```python
    tasks = {
        asyncio.create_task(run_bot(bot, dp), name="bot"),
        asyncio.create_task(_run_webapp(), name="webapp"),
    }
```
**Строки 54-57.** Создаём два **asyncio Task** (задачи) и кладём в множество `{}`:
- `asyncio.create_task(корутина)` — планирует выполнение корутины, не блокирует текущий код
- `name="bot"` — имя для логов и отладки
- `run_bot` и `_run_webapp` будут выполняться **параллельно** в одном event loop

---

```python
    scheduler.start()
    logger.info("Scheduler started")
```
**Строки 58-59.** Запускаем планировщик. `.start()` — обычный (не async) метод APScheduler. Планировщик использует тот же event loop через специальный механизм APScheduler.

---

```python
    stop_event = asyncio.Event()
```
**Строка 62.** `asyncio.Event` — флаг-семафор. Создаём в состоянии «не установлен». Кто угодно может вызвать `stop_event.set()` чтобы сигнализировать «пора останавливаться», а `stop_event.wait()` ждёт пока флаг не установят.

---

```python
    def _handle_stop(*_: object) -> None:
        logger.info("Stop signal received")
        stop_event.set()
```
**Строки 64-66.** Функция-обработчик сигнала остановки. `*_` — принимает любые позиционные аргументы и игнорирует их (signal handler получает номер сигнала, нам он не нужен). При вызове — устанавливает `stop_event`.

---

```python
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_stop)
            except NotImplementedError:
                # Windows не поддерживает — пропускаем
                pass
    except RuntimeError:
        pass
```
**Строки 68-75.**
- `asyncio.get_running_loop()` — получаем текущий event loop
- `signal.SIGINT` — сигнал Ctrl+C
- `signal.SIGTERM` — сигнал от `kill PID` или docker stop
- `loop.add_signal_handler(sig, _handle_stop)` — при получении сигнала вызвать `_handle_stop`
- `NotImplementedError` — Windows не поддерживает `add_signal_handler`, пропускаем
- Внешний `RuntimeError` — на случай если нет running loop

---

```python
    done, pending = await asyncio.wait(
        {*tasks, asyncio.create_task(stop_event.wait(), name="stop_event")},
        return_when=asyncio.FIRST_COMPLETED,
    )
```
**Строки 78-81.** Ждём завершения **хоть одного** из:
- `{*tasks}` — задачи бота и веб-сервера (распаковываем наше множество)
- `asyncio.create_task(stop_event.wait())` — задача ожидания сигнала остановки
- `return_when=asyncio.FIRST_COMPLETED` — вернуться когда **первая** задача завершится (не ждать все)
- Возвращает два множества: `done` — завершённые, `pending` — ещё работают

---

```python
    for t in done:
        if t.exception():
            logger.error(f"Task {t.get_name()} crashed: {t.exception()}")
```
**Строки 82-84.** Проверяем: не упала ли какая-то завершённая задача с ошибкой. `t.exception()` — возвращает исключение или `None`.

---

```python
    scheduler.shutdown(wait=False)
```
**Строка 87.** Останавливаем планировщик. `wait=False` — не ждать завершения текущих задач, останавливаем немедленно.

---

```python
    for t in pending:
        t.cancel()
```
**Строки 88-89.** Отменяем все ещё работающие задачи (бот и/или веб-сервер). `.cancel()` посылает `CancelledError` внутрь корутины.

---

```python
    await bot.session.close()
```
**Строка 90.** Закрываем HTTP-сессию бота (aiogram держит соединение с Telegram). Нужно закрыть явно, иначе Python выдаст предупреждение об утечке ресурса.

---

```python
    logger.info("Bye.")
```
**Строка 91.** Финальное сообщение в лог. Подтверждение корректного завершения.

---

```python
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
```
**Строки 94-97.**
- `if __name__ == "__main__"` — этот блок выполняется только при прямом запуске `python -m app.main`, но не при импорте
- `asyncio.run(main())` — создаёт новый event loop и запускает `main()` в нём
- `except KeyboardInterrupt: pass` — подавляем вывод `^C` в консоль при Ctrl+C (мы уже обработали его через `_handle_stop`)
