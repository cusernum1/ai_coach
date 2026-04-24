# ============================================================
# app/bot/handlers/common.py — /start, /help, выбор роли
# ============================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    athlete_main_kb,
    coach_main_kb,
    role_choice_kb,
)
from app.bot.states import AthleteOnboarding
from app.config import config
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import (
    attach_athlete_to_default_coach,
    get_coach_config,
    get_user_with_profile,
    set_role,
)

router = Router(name="common")


# ── /start ───────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()

    if user is None:
        await message.answer("Произошла ошибка. Попробуйте снова.")
        return

    # Приветствие с брендом тренера (берём настройки default-тренера)
    brand = config.BOT_NAME
    welcome = f"Привет! Я — <b>{brand}</b>."
    async with get_session() as s:
        fresh = await get_user_with_profile(s, user.telegram_id)
        if fresh and fresh.role == Role.COACH:
            await message.answer(
                f"С возвращением, тренер <b>{fresh.full_name or 'coach'}</b>! "
                f"Используй меню ниже для управления ботом.",
                reply_markup=coach_main_kb(),
            )
            return

        if fresh and fresh.role == Role.ATHLETE:
            # Приветствие берём из настроек тренера, если есть
            if fresh.athlete and fresh.athlete.coach_id:
                cfg = await get_coach_config(s, fresh.athlete.coach_id)
                if cfg:
                    welcome = f"Привет! Я — <b>{cfg.brand_name}</b>.\n\n{cfg.welcome_message}"
            await message.answer(welcome, reply_markup=athlete_main_kb())
            return

    # Роль ещё не выбрана
    await message.answer(
        welcome + "\n\nВыбери, кто ты:",
        reply_markup=role_choice_kb(),
    )


# ── Выбор роли ───────────────────────────────────────────────
@router.callback_query(F.data == "role:coach")
async def on_role_coach(cb: CallbackQuery, user: User) -> None:
    async with get_session() as s:
        fresh = await get_user_with_profile(s, user.telegram_id)
        if fresh is None:
            await cb.answer("Ошибка")
            return
        await set_role(s, fresh, Role.COACH)
    await cb.message.answer(
        "Отлично! Ты в роли <b>тренера</b>. "
        "Через /settings можно настроить бренд и базовую программу, "
        "а через /athletes — увидеть спортсменов.",
        reply_markup=coach_main_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "role:athlete")
async def on_role_athlete(cb: CallbackQuery, user: User, state: FSMContext) -> None:
    async with get_session() as s:
        fresh = await get_user_with_profile(s, user.telegram_id)
        if fresh is None:
            await cb.answer("Ошибка")
            return
        await set_role(s, fresh, Role.ATHLETE)
        if fresh.athlete:
            await attach_athlete_to_default_coach(s, fresh.athlete)

    await cb.message.answer(
        "Отлично! Давай соберу твою анкету спортсмена.\n\n"
        "Сколько тебе лет? (число 10–80)"
    )
    await state.set_state(AthleteOnboarding.waiting_age)
    await cb.answer()


# ── /help ────────────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(message: Message, user: User | None) -> None:
    common_cmds = (
        "/start — перезапустить бота\n"
        "/help — эта справка\n"
        "/profile — твой профиль\n"
    )
    if user and user.role == Role.COACH:
        extra = (
            "\n<b>Команды тренера:</b>\n"
            "/settings — настройки бота (бренд, программа, цена)\n"
            "/athletes — список спортсменов\n"
            "/stats — агрегаты для дашборда\n"
            "/broadcast <текст> — рассылка всем спортсменам\n"
            "/setprice <копейки> — установить цену подписки\n"
            "/dashboard — ссылка на веб-дашборд\n"
        )
        await message.answer(common_cmds + extra)
        return
    if user and user.role == Role.ATHLETE:
        extra = (
            "\n<b>Команды спортсмена:</b>\n"
            "/plan [недель] — сформировать план\n"
            "/log — записать тренировку\n"
            "/checkin — опрос самочувствия\n"
            "/subscribe — оплатить подписку\n"
            "/strava — подключить Strava\n"
            "/nutrition — рекомендации по питанию\n"
            "\nЛюбое сообщение = вопрос к ИИ-тренеру."
        )
        await message.answer(common_cmds + extra)
        return
    await message.answer(common_cmds + "\nСначала выбери роль через /start.")


# ── /profile ─────────────────────────────────────────────────
@router.message(Command("profile"))
async def cmd_profile(message: Message, user: User | None) -> None:
    if user is None:
        await message.answer("Сначала /start.")
        return
    role = user.role.value if user.role else "unknown"
    lines = [
        f"<b>Имя:</b> {user.full_name or '—'}",
        f"<b>Username:</b> @{user.username}" if user.username else "",
        f"<b>Роль:</b> {role}",
    ]
    if user.athlete:
        a = user.athlete
        lines += [
            "",
            f"<b>Анкета спортсмена</b>",
            f"Возраст: {a.age or '—'}",
            f"Вид спорта: {a.sport or '—'}",
            f"Уровень: {a.level or '—'}",
            f"Цель: {a.goal or '—'}",
            f"Тренировок/нед.: {a.sessions_per_week or '—'}",
            f"Подписка: {'активна' if a.subscription_active else 'нет'}",
        ]
    await message.answer("\n".join(l for l in lines if l))
