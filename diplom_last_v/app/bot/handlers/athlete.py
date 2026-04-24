# ============================================================
# app/bot/handlers/athlete.py — Онбординг и команды спортсмена
# ============================================================
# Включает:
#   • Диалог сбора анкеты (возраст / спорт / уровень / цель / частота)
#   • Кнопки главного меню: План, Самочувствие, Питание
# ============================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.keyboards import athlete_main_kb
from app.bot.states import AthleteOnboarding, DailyPoll
from app.bot.utils import chunk_text
from app.core.agent import run_agent
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import (
    add_plan,
    get_athlete_by_user_id,
    get_coach_config,
    update_athlete_profile,
)

router = Router(name="athlete")


# ══════════════════════════════════════════════════════════════
# Онбординг (анкета)
# ══════════════════════════════════════════════════════════════
SPORTS = ["Бег", "Плавание", "Велоспорт", "Футбол",
          "Баскетбол", "Тяжёлая атлетика", "Теннис", "Другое"]
LEVELS = ["Начинающий", "Любитель", "Полупрофессионал", "Профессионал"]
GOALS = ["Похудение", "Набор мышечной массы", "Выносливость",
         "Подготовка к соревнованиям", "Общая физическая форма"]


def _choice_kb(items: list[str], prefix: str) -> InlineKeyboardMarkup:
    """Вертикальная inline-клавиатура выбора из фиксированного списка."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=item, callback_data=f"{prefix}:{item}")]
            for item in items
        ]
    )


@router.message(AthleteOnboarding.waiting_age)
async def ob_age(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (10 <= int(text) <= 80):
        await message.answer("Нужно число от 10 до 80. Попробуй снова.")
        return
    await state.update_data(age=int(text))
    await message.answer("Выбери вид спорта:", reply_markup=_choice_kb(SPORTS, "sport"))
    await state.set_state(AthleteOnboarding.waiting_sport)


@router.callback_query(AthleteOnboarding.waiting_sport, F.data.startswith("sport:"))
async def ob_sport(cb, state: FSMContext) -> None:
    sport = cb.data.split(":", 1)[1]
    await state.update_data(sport=sport)
    await cb.message.edit_text(f"Вид спорта: <b>{sport}</b>")
    await cb.message.answer("Твой уровень?", reply_markup=_choice_kb(LEVELS, "level"))
    await state.set_state(AthleteOnboarding.waiting_level)
    await cb.answer()


@router.callback_query(AthleteOnboarding.waiting_level, F.data.startswith("level:"))
async def ob_level(cb, state: FSMContext) -> None:
    level = cb.data.split(":", 1)[1]
    await state.update_data(level=level)
    await cb.message.edit_text(f"Уровень: <b>{level}</b>")
    await cb.message.answer("Какая у тебя цель?", reply_markup=_choice_kb(GOALS, "goal"))
    await state.set_state(AthleteOnboarding.waiting_goal)
    await cb.answer()


@router.callback_query(AthleteOnboarding.waiting_goal, F.data.startswith("goal:"))
async def ob_goal(cb, state: FSMContext) -> None:
    goal = cb.data.split(":", 1)[1]
    await state.update_data(goal=goal)
    await cb.message.edit_text(f"Цель: <b>{goal}</b>")
    await cb.message.answer("Сколько тренировок в неделю планируешь? (1–7)")
    await state.set_state(AthleteOnboarding.waiting_sessions)
    await cb.answer()


@router.message(AthleteOnboarding.waiting_sessions)
async def ob_sessions(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 7):
        await message.answer("Нужно число 1–7.")
        return
    sessions = int(text)
    data = await state.get_data()

    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        if athlete is None:
            await message.answer("Ошибка: профиль спортсмена не найден. Нажми /start.")
            await state.clear()
            return
        await update_athlete_profile(
            s,
            athlete.id,
            age=data.get("age"),
            sport=data.get("sport"),
            level=data.get("level"),
            goal=data.get("goal"),
            sessions_per_week=sessions,
        )

    await state.clear()
    await message.answer(
        "Отлично, анкета сохранена! 💪\n"
        "Используй меню ниже или напиши любое сообщение — я отвечу как тренер.",
        reply_markup=athlete_main_kb(),
    )


# ══════════════════════════════════════════════════════════════
# Меню: кнопки -> команды
# ══════════════════════════════════════════════════════════════
@router.message(F.text == "📋 План")
async def btn_plan(message: Message, user: User) -> None:
    await _plan_flow(message, user, weeks=1)


@router.message(Command("plan"))
async def cmd_plan(message: Message, user: User) -> None:
    # /plan 2 → 2 недели
    parts = (message.text or "").split()
    weeks = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    await _plan_flow(message, user, weeks=max(1, min(4, weeks)))


async def _plan_flow(message: Message, user: User, weeks: int) -> None:
    if not user or user.role != Role.ATHLETE or user.athlete is None:
        await message.answer("Команда доступна только спортсменам (/start).")
        return
    athlete = user.athlete
    if not athlete.sport:
        await message.answer("Сначала заполни анкету. /start")
        return

    await message.answer("⏳ Формирую план…")
    brand, base_program = "AI Coach", None
    async with get_session() as s:
        if athlete.coach_id:
            cfg = await get_coach_config(s, athlete.coach_id)
            if cfg:
                brand, base_program = cfg.brand_name, cfg.base_program

    prompt = f"Составь план тренировок на {weeks} нед. Сформируй инструментом generate_training_plan."
    response = await run_agent(
        prompt,
        athlete={
            "name": athlete.name,
            "age": athlete.age,
            "sport": athlete.sport,
            "level": athlete.level,
            "goal": athlete.goal,
            "sessions_per_week": athlete.sessions_per_week,
        },
        brand_name=brand,
        base_program=base_program,
    )

    # Сохраняем план в БД
    async with get_session() as s:
        await add_plan(
            s, athlete.id,
            title=f"План на {weeks} нед.",
            content=response,
            weeks=weeks,
        )

    for part in chunk_text(response):
        await message.answer(part)


# ── Питание ──────────────────────────────────────────────────
@router.message(F.text == "🍎 Питание")
@router.message(Command("nutrition"))
async def cmd_nutrition(message: Message, user: User) -> None:
    if not user or user.role != Role.ATHLETE or user.athlete is None:
        await message.answer("Команда доступна спортсменам.")
        return
    athlete = user.athlete
    await message.answer("⏳ Готовлю рекомендации по питанию…")
    brand, base_program = "AI Coach", None
    async with get_session() as s:
        if athlete.coach_id:
            cfg = await get_coach_config(s, athlete.coach_id)
            if cfg:
                brand, base_program = cfg.brand_name, cfg.base_program

    response = await run_agent(
        "Дай рекомендации по питанию через инструмент nutrition_recommendation для тренировочного дня.",
        athlete={
            "name": athlete.name,
            "age": athlete.age,
            "sport": athlete.sport,
            "level": athlete.level,
            "goal": athlete.goal,
            "sessions_per_week": athlete.sessions_per_week,
        },
        brand_name=brand,
        base_program=base_program,
    )
    for part in chunk_text(response):
        await message.answer(part)


# ── Самочувствие (быстрый вход в опрос) ──────────────────────
@router.message(F.text == "💪 Самочувствие")
@router.message(Command("checkin"))
async def cmd_checkin(message: Message, state: FSMContext, user: User) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Команда доступна спортсменам.")
        return
    from app.bot.keyboards import scale_kb

    await message.answer(
        "Оцени усталость (1 — бодрость, 10 — истощение):",
        reply_markup=scale_kb("fatigue"),
    )
    await state.set_state(DailyPoll.waiting_fatigue)
