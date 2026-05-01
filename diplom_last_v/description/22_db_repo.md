# app/db/repo.py — Репозитории (CRUD-операции)

## За что отвечает файл

**Repository pattern** — все запросы к БД собраны в одном месте. Handlers и веб-приложение не пишут SQL напрямую — они вызывают функции из этого файла. Это разделение упрощает тестирование и поддержку.

Все функции принимают `session: AsyncSession` и выполняют запросы через него.

## Код с объяснениями

### Users & Roles

```python
async def get_or_create_user(session, telegram_id, username=None, full_name=None) -> User:
    q = select(User).where(User.telegram_id == telegram_id)
    user = (await session.execute(q)).scalar_one_or_none()
    if user:
        # Обновляем имя/username если изменились в Telegram
        if username and user.username != username:
            user.username = username
            await session.flush()
        return user
    
    user = User(telegram_id=telegram_id, username=username, full_name=full_name, role=Role.UNKNOWN)
    session.add(user)
    await session.flush()
    return user
```
- `select(User).where(...)` — SELECT запрос с условием
- `scalar_one_or_none()` — возвращает один объект или `None` (не бросает ошибку если не найдено)
- `session.add(user)` — добавляет объект в сессию (INSERT при flush/commit)
- `session.flush()` — отправляет изменения в БД в рамках текущей транзакции (без commit)

```python
async def set_role(session, user, role) -> None:
    user.role = role
    await session.flush()
    
    if role == Role.COACH and user.coach is None:
        coach = Coach(user_id=user.id, display_name=user.full_name or "Тренер")
        session.add(coach)
        await session.flush()
        session.add(CoachConfig(coach_id=coach.id))  # дефолтный конфиг
        await session.flush()
    
    if role == Role.ATHLETE and user.athlete is None:
        session.add(Athlete(user_id=user.id, name=user.full_name or "Спортсмен"))
        await session.flush()
```
При установке роли автоматически создаём связанный профиль. Один вызов = всё в одной транзакции.

```python
async def get_user_with_profile(session, telegram_id) -> Optional[User]:
    q = (
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(
            selectinload(User.coach).selectinload(Coach.config),
            selectinload(User.athlete).selectinload(Athlete.coach),
            selectinload(User.strava_token),
        )
    )
```
`selectinload()` — стратегия загрузки связанных объектов. Без неё SQLAlchemy загрузил бы `user.coach` отдельным запросом при первом обращении (lazy load). При асинхронном коде это проблема — запрос происходит вне контекста сессии.

`selectinload` загружает всё сразу одним дополнительным SELECT: `SELECT * FROM coaches WHERE user_id IN (...)`.

---

### Coach / Config

```python
async def get_coach_brand(session, coach_id) -> tuple[str, Optional[str]]:
    if coach_id is None:
        return "AI Coach", None
    cfg = await get_coach_config(session, coach_id)
    if cfg is None:
        return "AI Coach", None
    return cfg.brand_name, cfg.base_program
```
Вспомогательная функция — возвращает `(brand_name, base_program)` для тренера.

- Используется во всех handler'ах которым нужны настройки тренера: `agent_chat.py`, `athlete.py`
- Убирает дублирование: раньше в каждом файле был одинаковый блок `if cfg: brand = cfg.brand_name`
- `tuple[str, Optional[str]]` — тип возврата: первый элемент всегда строка, второй может быть `None` (если нет базовой программы)
- `Optional[str]` = `str | None` — значение может быть строкой или отсутствовать

---

```python
async def update_coach_config(session, coach_id, **fields) -> CoachConfig:
    cfg = await get_coach_config(session, coach_id)
    if cfg is None:
        cfg = CoachConfig(coach_id=coach_id)
        session.add(cfg)
    for key, value in fields.items():
        if value is None:
            continue
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    await session.flush()
    return cfg
```
`**fields` — принимает любые именованные аргументы: `update_coach_config(s, id, brand_name="My Coach", subscription_price=50000)`.

`setattr(cfg, key, value)` — динамически устанавливает атрибут. Эквивалентно `cfg.brand_name = "My Coach"`, но через переменную.

---

### Athletes

```python
async def list_athletes(session, coach_id=None) -> Sequence[Athlete]:
    q = select(Athlete).options(selectinload(Athlete.user)).order_by(Athlete.id)
    if coach_id is not None:
        q = q.where(Athlete.coach_id == coach_id)
    return (await session.execute(q)).scalars().all()
```
Опциональный фильтр: без `coach_id` — все спортсмены, с `coach_id` — только у конкретного тренера.

```python
async def get_athlete_by_telegram_id(session, telegram_id) -> Optional[Athlete]:
    q = (
        select(Athlete)
        .join(User, User.id == Athlete.user_id)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(Athlete.user))
    )
```
`.join()` — SQL JOIN: связываем `athletes` с `users` чтобы фильтровать по `telegram_id`.

---

### Training Logs

```python
async def list_training_logs(session, athlete_id, days=28) -> Sequence[TrainingLog]:
    since = date.today() - timedelta(days=days)
    q = (
        select(TrainingLog)
        .where(TrainingLog.athlete_id == athlete_id, TrainingLog.log_date >= since)
        .order_by(TrainingLog.log_date.desc())
    )
```
`timedelta(days=days)` — вычитаем дни от сегодня. `>= since` — только записи не старше N дней.

---

### Payments

```python
async def activate_subscription(session, user_id, days=30) -> None:
    athlete = await get_athlete_by_user_id(session, user_id)
    if athlete is None:
        return
    until = datetime.now(timezone.utc) + timedelta(days=days)
    athlete.subscription_active = True
    athlete.subscription_until = until
    await session.flush()
```
Простая активация: устанавливаем флаг и дату окончания. Проверку истечения подписки нужно делать отдельно (в MVP не реализована).

- `datetime.now(timezone.utc)` — текущее UTC-время. **Важно:** `timezone.utc` передаётся явно, иначе Python вернёт «наивное» datetime без информации о часовом поясе. В Python 3.12 старый способ `datetime.utcnow()` помечен как **устаревший (deprecated)** — он тоже возвращает UTC, но без метки часового пояса, что может вызвать ошибки при сравнении с «осведомлёнными» datetime
- `timedelta(days=days)` — прибавляет N дней к текущей дате

---

### Dashboard Stats

```python
async def coach_dashboard_stats(session, coach_id) -> dict:
    athletes_count = (
        await session.execute(select(func.count(Athlete.id)).where(Athlete.coach_id == coach_id))
    ).scalar_one()
    
    active_subs = (
        await session.execute(
            select(func.count(Athlete.id)).where(
                Athlete.coach_id == coach_id,
                Athlete.subscription_active.is_(True),
            )
        )
    ).scalar_one()
    
    revenue_sum = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.coach_id == coach_id)
        )
    ).scalar_one()
    
    return {"athletes": athletes_count, "active_subscriptions": active_subs, "revenue_minor_units": revenue_sum}
```
- `func.count()` — SQL COUNT
- `func.sum()` — SQL SUM  
- `func.coalesce(func.sum(...), 0)` — COALESCE: если SUM вернул NULL (нет записей) → заменить на 0

## Ключевые термины

- **Repository pattern** — все запросы к БД в одном месте
- **`session.flush()`** — отправить изменения в рамках транзакции (без commit)
- **`selectinload()`** — загрузить связанные объекты одним дополнительным SELECT
- **Lazy load** — загрузка связей «по требованию» (проблема в async-коде)
- **`scalar_one_or_none()`** — вернуть один объект или None
- **`func.count()`, `func.sum()`** — агрегатные функции SQL
