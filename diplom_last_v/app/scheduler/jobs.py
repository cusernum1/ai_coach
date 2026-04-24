# ============================================================
# app/scheduler/jobs.py — задачи APScheduler
# ============================================================
# • daily_poll_job — каждый день в DAILY_POLL_TIME шлём
#   спортсменам утренний опрос (старт FSM DailyPoll).
# • weekly_summary_job — по воскресеньям шлём тренеру сводку.
# • strava_sync_job — раз в N часов тянем активности.
# ============================================================

from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.bot.keyboards import scale_kb
from app.config import config
from app.db import get_session
from app.db.models import Role
from app.db.repo import (
    coach_dashboard_stats,
    get_coach_config,
    list_athletes,
)
from app.integrations.strava import sync_to_training_logs


async def daily_poll_job(bot: Bot) -> None:
    """Утром каждого дня шлём спортсменам опросник."""
    logger.info("daily_poll_job fired")
    async with get_session() as s:
        athletes = await list_athletes(s)
    for a in athletes:
        # Пропускаем тех, у кого тренер выключил опросы
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
            # FSM переведёт пользователя в DailyPoll автоматически
            # после первого клика (см. poll.py). Чтобы пользователь
            # сразу попал в стейт waiting_fatigue, можно использовать
            # MemoryStorage API — но для простоты считаем, что первая
            # кнопка запускает poll.handler напрямую.
        except Exception as e:  # noqa: BLE001
            logger.warning(f"daily_poll: cannot notify {a.user.telegram_id}: {e}")


async def weekly_summary_job(bot: Bot) -> None:
    """По понедельникам утром шлём тренеру итоги недели."""
    logger.info("weekly_summary_job fired")
    async with get_session() as s:
        athletes = await list_athletes(s)
    coaches: dict[int, int] = {}
    for a in athletes:
        if a.coach_id:
            coaches.setdefault(a.coach_id, 0)
            coaches[a.coach_id] += 1
    async with get_session() as s:
        for coach_id in coaches:
            stats = await coach_dashboard_stats(s, coach_id)
            # Найдём Telegram тренера
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
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"weekly_summary fail for {user.telegram_id}: {e}")


async def strava_sync_job(bot: Bot) -> None:
    """Периодическая синхронизация активностей Strava у всех подключённых спортсменов."""
    logger.info("strava_sync_job fired")
    async with get_session() as s:
        athletes = await list_athletes(s)
    total = 0
    for a in athletes:
        if not a.user or not a.user.telegram_id:
            continue
        try:
            total += await sync_to_training_logs(a.user.telegram_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"strava_sync for tg={a.user.telegram_id} failed: {e}")
    logger.info(f"strava_sync_job: total added={total}")


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создать и настроить планировщик (без .start() — старт в main.py)."""
    scheduler = AsyncIOScheduler(timezone=config.SCHEDULER_TIMEZONE)

    # Разберём время ежедневного опроса HH:MM
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
        CronTrigger(hour="*/6"),  # каждые 6 часов
        args=[bot],
        id="strava_sync",
        replace_existing=True,
    )
    return scheduler
