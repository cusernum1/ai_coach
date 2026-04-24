# ============================================================
# app/bot/middlewares.py — Middlewares: пользователь/роль, логгинг
# ============================================================
# UserContextMiddleware:
#   • на каждом апдейте делает get_or_create_user в БД
#   • кладёт в handler data["user"] (ORM User с coach/athlete)
#   • автоматически назначает роль COACH первому админу
#     (ADMIN_TELEGRAM_ID из .env).
# ============================================================

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as AiogramUser
from loguru import logger

from app.config import config
from app.db import get_session
from app.db.models import Role
from app.db.repo import (
    attach_athlete_to_default_coach,
    get_or_create_user,
    get_user_with_profile,
    set_role,
)


class UserContextMiddleware(BaseMiddleware):
    """Подмешивает в handler-data ORM-объект User (со связями)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: AiogramUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async with get_session() as s:
            # быстрый upsert (имя/юзернейм)
            await get_or_create_user(
                s,
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )

            # автоматически назначаем роль COACH админу из .env
            user = await get_user_with_profile(s, tg_user.id)
            if (
                user is not None
                and user.role == Role.UNKNOWN
                and config.ADMIN_TELEGRAM_ID
                and tg_user.id == config.ADMIN_TELEGRAM_ID
            ):
                logger.info(f"Auto-assigning COACH role to admin {tg_user.id}")
                await set_role(s, user, Role.COACH)
                user = await get_user_with_profile(s, tg_user.id)

            # Если спортсмен без тренера — привязываем к дефолтному
            if user is not None and user.role == Role.ATHLETE and user.athlete and user.athlete.coach_id is None:
                await attach_athlete_to_default_coach(s, user.athlete)
                user = await get_user_with_profile(s, tg_user.id)

            data["user"] = user

        return await handler(event, data)
