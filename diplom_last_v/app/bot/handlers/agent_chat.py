# ============================================================
# app/bot/handlers/agent_chat.py — свободный диалог с LLM-агентом
# ============================================================
# Ловит любые текстовые сообщения, не попавшие в другие хэндлеры.
# Имеет простую in-memory память по chat_id (последние N сообщений).
# ============================================================

from __future__ import annotations

from collections import defaultdict
from typing import Deque, Dict
from collections import deque

from aiogram import Router
from aiogram.types import Message

from app.bot.utils import chunk_text
from app.config import config
from app.core.agent import run_agent
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import get_coach_brand

router = Router(name="agent_chat")


# ── Простая память диалогов (per-chat) ───────────────────────
_HISTORY: Dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=config.CHAT_MEMORY_SIZE * 2))


@router.message()
async def on_free_text(message: Message, user: User | None) -> None:
    # Игнорируем служебные (команды уже обработаны выше, фото и т.п.)
    if not message.text:
        return
    text = message.text.strip()
    if not text:
        return
    if user is None:
        await message.answer("Сначала /start.")
        return

    # Агент работает только для спортсменов (у тренера — настроечное меню)
    if user.role != Role.ATHLETE or user.athlete is None or not user.athlete.sport:
        await message.answer(
            "Сначала заполни анкету (/start) — и задавай вопросы."
        )
        return

    athlete = user.athlete
    async with get_session() as s:
        brand, base_program = await get_coach_brand(s, athlete.coach_id)

    # Индикатор «печатает…» через отправку «думаю» заглушки:
    thinking = await message.answer("💭 думаю…")

    # История
    history = list(_HISTORY[message.chat.id])
    history.append({"role": "user", "content": text})

    response = await run_agent(
        text,
        athlete={
            "name": athlete.name,
            "age": athlete.age,
            "sport": athlete.sport,
            "level": athlete.level,
            "goal": athlete.goal,
            "sessions_per_week": athlete.sessions_per_week,
        },
        chat_history=history,
        brand_name=brand,
        base_program=base_program,
    )

    # Сохраняем в память
    _HISTORY[message.chat.id].append({"role": "user", "content": text})
    _HISTORY[message.chat.id].append({"role": "assistant", "content": response})

    # Удаляем заглушку «думаю»
    try:
        await thinking.delete()
    except Exception:  # noqa: BLE001
        pass

    for part in chunk_text(response):
        await message.answer(part)
