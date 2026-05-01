# app/bot/middlewares.py — Мидлвара: контекст пользователя

## Назначение файла
Выполняется перед **каждым** обработчиком сообщений. Находит или создаёт пользователя в БД, автоматически назначает роль COACH первому администратору, кладёт ORM-объект `user` в словарь данных обработчика.

---

## Построчный разбор

```python
from __future__ import annotations
```
Разрешает современные аннотации типов.

---

```python
from typing import Any, Awaitable, Callable, Dict
```
Импорт типов для аннотаций:
- `Any` — любой тип (когда точный тип неизвестен)
- `Awaitable` — объект который можно ожидать через `await`
- `Callable` — вызываемый объект (функция)
- `Dict` — словарь (старый синтаксис, в Python 3.9+ можно просто `dict`)

---

```python
from aiogram import BaseMiddleware
```
Базовый класс мидлвары из aiogram. Наш класс будет его наследником.

---

```python
from aiogram.types import TelegramObject, User as AiogramUser
```
- `TelegramObject` — базовый класс для всех объектов Telegram (сообщение, нажатие кнопки и т.д.)
- `User as AiogramUser` — **переименовываем** при импорте! В aiogram тоже есть класс `User` (Telegram-пользователь), но у нас в БД тоже есть класс `User` (наша модель). Переименовываем telegram-шный в `AiogramUser` чтобы не было конфликта.

---

```python
from loguru import logger
```
Для записи в лог события автоматического назначения роли.

---

```python
from app.config import config
```
Нам нужен `config.ADMIN_TELEGRAM_ID` — ID администратора из `.env`.

---

```python
from app.db import get_session
```
Контекстный менеджер для работы с БД.

---

```python
from app.db.models import Role
```
Перечисление ролей: `Role.COACH`, `Role.ATHLETE`, `Role.UNKNOWN`.

---

```python
from app.db.repo import (
    attach_athlete_to_default_coach,
    get_or_create_user,
    get_user_with_profile,
    set_role,
)
```
Четыре функции из репозитория:
- `get_or_create_user` — найти или создать пользователя в БД
- `get_user_with_profile` — загрузить пользователя с профилями (coach/athlete)
- `set_role` — назначить роль и создать профиль
- `attach_athlete_to_default_coach` — привязать спортсмена к тренеру

---

```python
class UserContextMiddleware(BaseMiddleware):
```
Определяем класс мидлвары. Наследуется от `BaseMiddleware` — это обязательное требование aiogram.

---

```python
    """Подмешивает в handler-data ORM-объект User (со связями)."""
```
Документация класса.

---

```python
    async def __call__(
```
`__call__` — специальный метод Python. Позволяет вызывать объект как функцию: `middleware(handler, event, data)`. aiogram вызывает мидлвары именно через этот метод.

---

```python
        self,
```
Ссылка на экземпляр класса — стандартный первый параметр методов в Python.

---

```python
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
```
Следующий обработчик в цепочке. Тип сложный: это функция (`Callable`) которая принимает `TelegramObject` и `Dict` и возвращает `Awaitable`. По сути — следующая мидлвара или финальный handler.

---

```python
        event: TelegramObject,
```
Текущее обновление от Telegram (сообщение, нажатие кнопки, предзапрос оплаты и т.д.).

---

```python
        data: Dict[str, Any],
```
Словарь данных который передаётся от мидлвары к мидлваре и в конечном итоге в handler. Мы добавим в него `data["user"]`.

---

```python
    ) -> Any:
```
Возвращаемый тип — `Any` (что вернёт финальный handler).

---

```python
        tg_user: AiogramUser | None = data.get("event_from_user")
```
Получаем Telegram-пользователя из словаря данных. aiogram автоматически кладёт его туда под ключом `"event_from_user"`.
- `AiogramUser | None` — может быть `None` для системных событий
- `.get("event_from_user")` — безопасное получение из словаря (не бросает `KeyError`)

---

```python
        if tg_user is None:
            return await handler(event, data)
```
Если пользователя нет (системное событие) — сразу передаём управление дальше, ничего не делаем. `return` здесь важен — выходим из метода.

---

```python
        async with get_session() as s:
```
Открываем сессию БД. Всё что внутри этого блока будет в одной транзакции.

---

```python
            await get_or_create_user(
                s,
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )
```
Ищем пользователя по `telegram_id`. Если не нашли — создаём нового с ролью `UNKNOWN`. Если нашли — обновляем имя (могло измениться в Telegram). `await` — асинхронный запрос к БД.

---

```python
            user = await get_user_with_profile(s, tg_user.id)
```
Загружаем пользователя со **всеми связанными объектами**: `user.coach`, `user.coach.config`, `user.athlete`, `user.strava_token`. `selectinload` в репозитории делает это одним дополнительным SQL-запросом.

---

```python
            if (
                user is not None
```
Начало условия. Проверяем что пользователь существует в БД.

---

```python
                and user.role == Role.UNKNOWN
```
Роль ещё не выбрана — это новый пользователь или пользователь без роли.

---

```python
                and config.ADMIN_TELEGRAM_ID
```
В `.env` задан `ADMIN_TELEGRAM_ID`. `config.ADMIN_TELEGRAM_ID` — это число. В Python `0` и `None` считаются `False`, а любое ненулевое число — `True`. Значит если переменная не задана (равна 0) — условие `False`.

---

```python
                and tg_user.id == config.ADMIN_TELEGRAM_ID
```
Текущий пользователь — именно тот администратор, чей ID указан в `.env`.

---

```python
            ):
                logger.info(f"Auto-assigning COACH role to admin {tg_user.id}")
```
Все четыре условия выполнены — логируем событие.

---

```python
                await set_role(s, user, Role.COACH)
```
Назначаем роль COACH. `set_role` также автоматически создаёт объект `Coach` и `CoachConfig` с дефолтными настройками.

---

```python
                user = await get_user_with_profile(s, tg_user.id)
```
Перезагружаем пользователя — теперь у него есть `user.coach` и `user.coach.config`. Старый объект `user` их не имел.

---

```python
            if user is not None and user.role == Role.ATHLETE and user.athlete and user.athlete.coach_id is None:
```
Второе условие: пользователь — спортсмен (`Role.ATHLETE`), у него есть профиль (`user.athlete`), но он ещё не привязан к тренеру (`coach_id is None`).

---

```python
                await attach_athlete_to_default_coach(s, user.athlete)
```
Привязываем к первому тренеру в системе (MVP-решение: берём тренера с наименьшим `id`).

---

```python
                user = await get_user_with_profile(s, tg_user.id)
```
Снова перезагружаем — теперь `user.athlete.coach_id` заполнен.

---

```python
            data["user"] = user
```
**Ключевая строка.** Кладём ORM-объект в словарь данных. Теперь любой handler объявленный как `async def handler(message: Message, user: User)` автоматически получит этот объект. aiogram умеет инжектировать из `data` по имени параметра.

---

```python
        return await handler(event, data)
```
**Обязательная строка.** Передаём управление следующему обработчику в цепочке (следующей мидлваре или финальному handler). Без этого сообщение никогда не обработается. `return` возвращает результат handler'а вызывающему коду.
