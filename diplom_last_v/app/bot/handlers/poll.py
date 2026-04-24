# ============================================================
# app/bot/handlers/poll.py — Ежедневный опрос самочувствия
# ============================================================
# Планировщик вызывает services.send_daily_polls(), которая
# отправляет первый вопрос. Дальше — FSM DailyPoll.
# ============================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards import athlete_main_kb, scale_kb
from app.bot.states import DailyPoll
from app.core.metrics import wellness_label, wellness_score
from app.db import get_session
from app.db.models import User
from app.db.repo import (
    add_session_record,
    create_poll,
    get_athlete_by_user_id,
    save_poll_answers,
)

router = Router(name="poll")


@router.callback_query(F.data.startswith("fatigue:"))
async def poll_fatigue(cb: CallbackQuery, state: FSMContext) -> None:
    # Без фильтра состояния: приглашение на опрос могло прийти от планировщика,
    # где FSM ещё не установлен. Сразу переводим пользователя в waiting_sleep.
    value = int(cb.data.split(":")[1])
    await state.update_data(fatigue=value)
    await cb.message.edit_text(f"Усталость: <b>{value}/10</b>")
    await cb.message.answer("Оцени качество сна (1 — плохой, 10 — отличный):",
                             reply_markup=scale_kb("sleep"))
    await state.set_state(DailyPoll.waiting_sleep)
    await cb.answer()


@router.callback_query(DailyPoll.waiting_sleep, F.data.startswith("sleep:"))
async def poll_sleep(cb: CallbackQuery, state: FSMContext) -> None:
    value = int(cb.data.split(":")[1])
    await state.update_data(sleep=value)
    await cb.message.edit_text(f"Сон: <b>{value}/10</b>")
    await cb.message.answer(
        "Хочешь оставить заметку (жалобы, боли, замечания)? Напиши или /skip.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(DailyPoll.waiting_notes)
    await cb.answer()


@router.message(DailyPoll.waiting_notes)
async def poll_notes(message: Message, state: FSMContext, user: User) -> None:
    notes = "" if (message.text or "").strip() in ("/skip", "-") else (message.text or "").strip()
    data = await state.get_data()
    fatigue, sleep = int(data["fatigue"]), int(data["sleep"])
    await state.clear()

    # ── Сохраняем в БД: Session + Poll+PollAnswer ────────────
    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        if athlete is None:
            await message.answer("Нет профиля спортсмена.", reply_markup=athlete_main_kb())
            return
        await add_session_record(
            s, athlete.id,
            fatigue=fatigue, sleep_quality=sleep,
            results="", pain=notes,
        )
        poll = await create_poll(s, athlete.id, kind="daily")
        await save_poll_answers(s, poll.id, {
            "Усталость (1-10)": str(fatigue),
            "Сон (1-10)": str(sleep),
            "Заметки": notes or "—",
        })

    score = wellness_score(fatigue, sleep)
    label = wellness_label(score)
    await message.answer(
        f"Спасибо! Wellness Score: <b>{score:.0f}/100</b> — {label}.\n"
        f"Усталость {fatigue}/10, сон {sleep}/10.",
        reply_markup=athlete_main_kb(),
    )


@router.message(F.text == "/skip", DailyPoll.waiting_notes)
async def poll_skip(message: Message, state: FSMContext, user: User) -> None:
    # Дублируем ветку выше с пустой заметкой
    data = await state.get_data()
    fatigue, sleep = int(data["fatigue"]), int(data["sleep"])
    await state.clear()
    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        if athlete:
            await add_session_record(s, athlete.id, fatigue=fatigue, sleep_quality=sleep)
            poll = await create_poll(s, athlete.id, kind="daily")
            await save_poll_answers(s, poll.id, {
                "Усталость (1-10)": str(fatigue),
                "Сон (1-10)": str(sleep),
            })
    score = wellness_score(fatigue, sleep)
    await message.answer(
        f"Сохранено. Wellness Score: <b>{score:.0f}/100</b> — {wellness_label(score)}.",
        reply_markup=athlete_main_kb(),
    )
