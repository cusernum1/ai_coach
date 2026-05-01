# app/scheduler/jobs.py — Задачи по расписанию

## За что отвечает файл

Планировщик **APScheduler** выполняет задачи автоматически без участия пользователя:
- **Ежедневно** в заданное время — утренний опрос спортсменов
- **По понедельникам** в 9:00 — еженедельная сводка тренеру
- **Каждые 6 часов** — синхронизация активностей из Strava

## Код с объяснениями

### Утренний опрос

```python
async def daily_poll_job(bot: Bot) -> None:
    logger.info("daily_poll_job fired")
    async with get_session() as s:
        athletes = await list_athletes(s)
    
    for a in athletes:
        # Проверяем: включены ли опросы у тренера
        async with get_session() as s:
            cfg = await get_coach_config(s, a.coach_id) if a.coach_id else None
        if cfg and not cfg.polls_enabled:
            continue
        
        if not a.user or not a.user.telegram_id:
            continue
        
        try:
            await bot.send_message(
                a.user.telegram_id,
                "🌅 Доброе утро! Как ты сегодня?\n"
                "Оцени усталость (1 — бодрость, 10 — истощение):",
                reply_markup=scale_kb("fatigue"),
            )
        except Exception as e:
            logger.warning(f"daily_poll: cannot notify {a.user.telegram_id}: {e}")
```
- Сессию открываем **дважды**: сначала получаем спортсменов, потом для каждого — конфиг тренера. Отдельные сессии — это нормально, каждая операция независима.
- `try/except` — если бот заблокирован у одного пользователя, не останавливаем всю рассылку.
- Кнопки `scale_kb("fatigue")` — первый вопрос опроса. При нажатии сработает `handlers/poll.py`.

---

### Еженедельная сводка

```python
async def weekly_summary_job(bot: Bot) -> None:
    async with get_session() as s:
        athletes = await list_athletes(s)
    
    coaches: dict[int, int] = {}
    for a in athletes:
        if a.coach_id:
            coaches.setdefault(a.coach_id, 0)
            coaches[a.coach_id] += 1
```
`setdefault(key, default)` — если ключа нет, устанавливает значение по умолчанию и возвращает его. Считаем сколько спортсменов у каждого тренера.

```python
    async with get_session() as s:
        for coach_id in coaches:
            stats = await coach_dashboard_stats(s, coach_id)
            # Находим Telegram тренера через JOIN
            from app.db.models import Coach, User
            from sqlalchemy import select
            q = select(User).join(Coach, Coach.user_id == User.id).where(Coach.id == coach_id)
            user = (await s.execute(q)).scalar_one_or_none()
            if user and user.telegram_id:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"📊 Итоги недели:\n"
                        f"Спортсменов: {stats['athletes']}\n"
                        f"Активных подписок: {stats['active_subscriptions']}\n"
                        f"Оборот: {stats['revenue_minor_units'] / 100:.2f} {config.PAYMENTS_CURRENCY}",
                    )
                except Exception as e:
                    logger.warning(...)
```
Импорт моделей **внутри функции** (`from app.db.models import ...`) — это нормально для избежания циклических импортов.

---

### Синхронизация Strava

```python
async def strava_sync_job(bot: Bot) -> None:
    async with get_session() as s:
        athletes = await list_athletes(s)
    total = 0
    for a in athletes:
        if not a.user or not a.user.telegram_id:
            continue
        try:
            total += await sync_to_training_logs(a.user.telegram_id)
        except Exception as e:
            logger.warning(f"strava_sync for tg={a.user.telegram_id} failed: {e}")
    logger.info(f"strava_sync_job: total added={total}")
```
Для каждого спортсмена пытаемся синхронизировать. Если у кого-то нет токена Strava — `sync_to_training_logs()` вернёт 0, не падает.

---

### Создание планировщика

```python
def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.SCHEDULER_TIMEZONE)
    
    # Разбираем "08:00" → hour=8, minute=0
    try:
        hour, minute = map(int, config.DAILY_POLL_TIME.split(":"))
    except Exception:
        hour, minute = 8, 0
    
    scheduler.add_job(
        daily_poll_job,
        CronTrigger(hour=hour, minute=minute),
        args=[bot],
        id="daily_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        weekly_summary_job,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        args=[bot],
        id="weekly_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        strava_sync_job,
        CronTrigger(hour="*/6"),  # каждые 6 часов: 0:00, 6:00, 12:00, 18:00
        args=[bot],
        id="strava_sync",
        replace_existing=True,
    )
    return scheduler
```
- `AsyncIOScheduler` — работает в том же event loop что и бот
- `CronTrigger` — расписание в стиле cron
- `hour="*/6"` — cron-синтаксис «каждые 6 часов»
- `args=[bot]` — передаём объект бота в задачу (чтобы отправлять сообщения)
- `replace_existing=True` — при перезапуске не дублировать задачи
- `id="daily_poll"` — уникальный идентификатор задачи

## Ключевые термины

- **APScheduler** — библиотека для планирования задач в Python
- **AsyncIOScheduler** — работает в asyncio event loop (не в отдельном потоке)
- **CronTrigger** — расписание в cron-синтаксисе (`час/минута/день_недели`)
- **Cron** — классический Unix-формат расписания (`*/6` = каждые 6 единиц)
