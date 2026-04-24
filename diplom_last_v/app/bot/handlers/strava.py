# ============================================================
# app/bot/handlers/strava.py — подключение и синхронизация Strava
# ============================================================
# Сам redirect_uri обрабатывает FastAPI-приложение (см. webapp/server.py),
# а бот только выдаёт ссылку авторизации и команду /sync_strava.
# ============================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import config
from app.db.models import Role, User
from app.integrations.strava import build_authorize_url, sync_to_training_logs

router = Router(name="strava")


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


@router.message(Command("sync_strava"))
async def cmd_sync_strava(message: Message, user: User | None) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Команда доступна спортсменам.")
        return
    await message.answer("⏳ Синхронизация…")
    try:
        added = await sync_to_training_logs(user.telegram_id)
    except Exception as e:  # noqa: BLE001
        await message.answer(f"Ошибка синхронизации: {e}")
        return
    if added == 0:
        await message.answer("Новых активностей не найдено (или Strava ещё не подключена).")
    else:
        await message.answer(f"✅ Добавлено {added} активностей в журнал.")
