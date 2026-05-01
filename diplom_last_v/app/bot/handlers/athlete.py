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
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.keyboards import athlete_main_kb
from app.bot.pdf_utils import generate_pdf
from app.bot.states import AthleteOnboarding, DailyPoll, NutritionQuestionnaire, PlanQuestionnaire
from app.bot.utils import chunk_text
from app.core.agent import run_agent
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import (
    add_plan,
    get_athlete_by_user_id,
    get_coach_brand,
    update_athlete_nutrition,
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
async def ob_sport(cb: CallbackQuery, state: FSMContext) -> None:
    sport = cb.data.split(":", 1)[1]
    await state.update_data(sport=sport)
    await cb.message.edit_text(f"Вид спорта: <b>{sport}</b>")
    await cb.message.answer("Твой уровень?", reply_markup=_choice_kb(LEVELS, "level"))
    await state.set_state(AthleteOnboarding.waiting_level)
    await cb.answer()


@router.callback_query(AthleteOnboarding.waiting_level, F.data.startswith("level:"))
async def ob_level(cb: CallbackQuery, state: FSMContext) -> None:
    level = cb.data.split(":", 1)[1]
    await state.update_data(level=level)
    await cb.message.edit_text(f"Уровень: <b>{level}</b>")
    await cb.message.answer("Какая у тебя цель?", reply_markup=_choice_kb(GOALS, "goal"))
    await state.set_state(AthleteOnboarding.waiting_goal)
    await cb.answer()


@router.callback_query(AthleteOnboarding.waiting_goal, F.data.startswith("goal:"))
async def ob_goal(cb: CallbackQuery, state: FSMContext) -> None:
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

# ── План: шаг 1 — спросить кол-во недель ─────────────────────
@router.message(F.text == "📋 План")
@router.message(Command("plan"))
async def cmd_plan(message: Message, state: FSMContext, user: User) -> None:
    if not user or user.role != Role.ATHLETE or user.athlete is None:
        await message.answer("Команда доступна только спортсменам (/start).")
        return
    if not user.athlete.sport:
        await message.answer("Сначала заполни анкету. /start")
        return

    # /plan 2 → сразу генерируем, спрашивать не нужно
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].isdigit():
        weeks = max(1, min(4, int(parts[1])))
        await state.update_data(plan_weeks=weeks)
        await _generate_plan(message, state, user)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 неделя",  callback_data="plan_weeks:1"),
            InlineKeyboardButton(text="2 недели",  callback_data="plan_weeks:2"),
        ],
        [
            InlineKeyboardButton(text="3 недели",  callback_data="plan_weeks:3"),
            InlineKeyboardButton(text="4 недели",  callback_data="plan_weeks:4"),
        ],
    ])
    await message.answer("На сколько недель составить план?", reply_markup=kb)
    await state.set_state(PlanQuestionnaire.waiting_weeks)


# ── План: шаг 2 — выбор нажат ────────────────────────────────
@router.callback_query(PlanQuestionnaire.waiting_weeks, F.data.startswith("plan_weeks:"))
async def plan_weeks_chosen(cb: CallbackQuery, state: FSMContext, user: User) -> None:
    weeks = int(cb.data.split(":")[1])
    await cb.message.edit_text(f"Выбрано: {weeks} нед. ⏳ Формирую план…")
    await state.update_data(plan_weeks=weeks)
    await cb.answer()
    await _generate_plan(cb.message, state, user)


# ── План: генерация + отправка PDF ───────────────────────────
async def _generate_plan(message: Message, state: FSMContext, user: User) -> None:
    data = await state.get_data()
    weeks = data.get("plan_weeks", 1)
    await state.clear()

    athlete = user.athlete
    async with get_session() as s:
        brand, base_program = await get_coach_brand(s, athlete.coach_id)

    response = await run_agent(
        f"Составь план тренировок на {weeks} нед. Сформируй инструментом generate_training_plan.",
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

    async with get_session() as s:
        await add_plan(s, athlete.id, title=f"План на {weeks} нед.", content=response, weeks=weeks)

    title = f"Тренировочный план на {weeks} нед. — {athlete.name}"
    pdf = generate_pdf(title, response)
    if pdf:
        doc = BufferedInputFile(pdf, filename=f"plan_{weeks}w.pdf")
        await message.answer_document(doc, caption=f"📋 {title}")
    else:
        for part in chunk_text(response):
            await message.answer(part)


# ── Питание: шаг 1 — вход ────────────────────────────────────
@router.message(F.text == "🍎 Питание")
@router.message(Command("nutrition"))
async def cmd_nutrition(message: Message, state: FSMContext, user: User) -> None:
    if not user or user.role != Role.ATHLETE or user.athlete is None:
        await message.answer("Команда доступна спортсменам.")
        return
    if not user.athlete.sport:
        await message.answer("Сначала заполни анкету. /start")
        return
    await message.answer(
        "Для персонального плана питания мне нужны несколько данных.\n\n"
        "Сколько ты весишь? (кг, например: 75 или 82.5)"
    )
    await state.set_state(NutritionQuestionnaire.waiting_weight)


# ── Питание: шаг 2 — рост ─────────────────────────────────────
@router.message(NutritionQuestionnaire.waiting_weight)
async def nutr_weight(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        weight = float(text)
        if not (30.0 <= weight <= 250.0):
            raise ValueError
    except ValueError:
        await message.answer("Введи вес числом, например: 75 или 82.5")
        return
    await state.update_data(weight_kg=weight)
    await message.answer("Рост? (в сантиметрах, например: 178)")
    await state.set_state(NutritionQuestionnaire.waiting_height)


# ── Питание: шаг 3 — ограничения ─────────────────────────────
@router.message(NutritionQuestionnaire.waiting_height)
async def nutr_height(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (100 <= int(text) <= 250):
        await message.answer("Введи рост числом от 100 до 250 (в см), например: 178")
        return
    await state.update_data(height_cm=int(text))
    await message.answer(
        "Есть ли у тебя аллергии или непереносимость продуктов?\n"
        "(Напиши «нет» или перечисли что нельзя: глютен, лактоза, орехи…)"
    )
    await state.set_state(NutritionQuestionnaire.waiting_restrictions)


# ── Питание: шаг 4 — кол-во приёмов пищи ────────────────────
@router.message(NutritionQuestionnaire.waiting_restrictions)
async def nutr_restrictions(message: Message, state: FSMContext) -> None:
    restrictions = (message.text or "нет").strip()
    await state.update_data(dietary_restrictions=restrictions)
    await message.answer(
        "Сколько раз в день ты обычно питаешься?\n"
        "(введи число: 2, 3, 4, 5 или 6)"
    )
    await state.set_state(NutritionQuestionnaire.waiting_meals)


# ── Питание: финал — генерация плана ─────────────────────────
@router.message(NutritionQuestionnaire.waiting_meals)
async def nutr_meals(message: Message, state: FSMContext, user: User) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 8):
        await message.answer("Введи число от 1 до 8.")
        return
    meals = int(text)
    data = await state.get_data()
    await state.clear()

    athlete = user.athlete

    async with get_session() as s:
        await update_athlete_nutrition(
            s,
            athlete.id,
            weight_kg=data.get("weight_kg"),
            height_cm=data.get("height_cm"),
            dietary_restrictions=data.get("dietary_restrictions"),
            meals_per_day=meals,
        )
        brand, base_program = await get_coach_brand(s, athlete.coach_id)

    await message.answer("⏳ Готовлю персональный план питания…")

    response = await run_agent(
        "Составь персональный план питания через инструмент nutrition_recommendation для тренировочного дня.",
        athlete={
            "name": athlete.name,
            "age": athlete.age,
            "sport": athlete.sport,
            "level": athlete.level,
            "goal": athlete.goal,
            "sessions_per_week": athlete.sessions_per_week,
            "weight_kg": data.get("weight_kg"),
            "height_cm": data.get("height_cm"),
            "dietary_restrictions": data.get("dietary_restrictions"),
            "meals_per_day": meals,
        },
        brand_name=brand,
        base_program=base_program,
    )

    title = f"План питания — {athlete.name}"
    pdf = generate_pdf(title, response)
    if pdf:
        doc = BufferedInputFile(pdf, filename="nutrition_plan.pdf")
        await message.answer_document(doc, caption=f"🍎 {title}")
    else:
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
