# ============================================================
# app/bot/handlers/coach.py — Команды тренера
# ============================================================
# Тренер может настроить всё через чат: бренд, логотип, базовую
# программу, цену, расписание опросов, рассылку, дашборд.
# ============================================================

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.keyboards import coach_main_kb, coach_settings_kb
from app.bot.states import CoachSettings
from app.bot.utils import money
from app.config import config
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import (
    coach_dashboard_stats,
    get_coach_config,
    list_athletes,
    list_payments_for_coach,
    update_coach_config,
)

router = Router(name="coach")


def _is_coach(user: User | None) -> bool:
    return bool(user and user.role == Role.COACH and user.coach)


# ══════════════════════════════════════════════════════════════
# /settings — редактирование настроек
# ══════════════════════════════════════════════════════════════
SETTING_LABELS = {
    "brand_name": "название бота",
    "logo_url": "URL логотипа",
    "welcome_message": "приветственное сообщение",
    "base_program": "базовая программа",
    "subscription_price": "цена подписки (в копейках, напр. 99900 = 999₽)",
    "daily_poll_time": "время ежедневного опроса (HH:MM)",
}


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки бота")
async def cmd_settings(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Команда доступна только тренеру.")
        return
    cfg = user.coach.config  # type: ignore[union-attr]
    if cfg is None:
        await message.answer("Настройки не найдены.")
        return
    text = (
        "<b>Текущие настройки:</b>\n"
        f"🏷 Название: {cfg.brand_name}\n"
        f"🖼 Лого: {cfg.logo_url or '—'}\n"
        f"👋 Приветствие: {cfg.welcome_message[:80]}...\n"
        f"📝 Базовая программа: {cfg.base_program[:80]}...\n"
        f"💰 Цена: {money(cfg.subscription_price, config.PAYMENTS_CURRENCY)}\n"
        f"⏰ Время опроса: {cfg.daily_poll_time}\n"
        f"🔔 Опросы: {'вкл' if cfg.polls_enabled else 'выкл'}\n"
        "\nВыбери, что изменить:"
    )
    await message.answer(text, reply_markup=coach_settings_kb())


@router.callback_query(F.data == "set:polls_toggle")
async def on_polls_toggle(cb: CallbackQuery, user: User) -> None:
    if not _is_coach(user):
        await cb.answer("Недоступно")
        return
    async with get_session() as s:
        cfg = await get_coach_config(s, user.coach.id)  # type: ignore[union-attr]
        if cfg is None:
            await cb.answer("Нет настроек")
            return
        cfg.polls_enabled = not cfg.polls_enabled
    await cb.message.answer(
        f"Опросы теперь: {'🔔 включены' if cfg.polls_enabled else '🔕 выключены'}"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("set:"))
async def on_set_field(cb: CallbackQuery, state: FSMContext, user: User) -> None:
    field = cb.data.split(":", 1)[1]
    if field == "polls_toggle":
        return  # обработано выше
    if field not in SETTING_LABELS:
        await cb.answer("Неизвестное поле")
        return
    await state.set_state(CoachSettings.waiting_value)
    await state.update_data(field=field)
    await cb.message.answer(
        f"Введи новое значение — <i>{SETTING_LABELS[field]}</i>:\n\n"
        "Чтобы отменить — отправь /cancel."
    )
    await cb.answer()


@router.message(Command("cancel"), CoachSettings.waiting_value)
async def cancel_setting(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(CoachSettings.waiting_value)
async def save_setting(message: Message, state: FSMContext, user: User) -> None:
    if not _is_coach(user):
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("field")
    value = (message.text or "").strip()
    if not value:
        await message.answer("Пустое значение не принимается.")
        return

    # ── Валидация по типу поля ───────────────────────────────
    if field == "subscription_price":
        if not value.isdigit() or int(value) <= 0:
            await message.answer("Нужно положительное число в копейках.")
            return
        value_cast: int | str = int(value)
    elif field == "daily_poll_time":
        # HH:MM 00-23:00-59
        import re
        if not re.fullmatch(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            await message.answer("Неверный формат. Пример: 08:30")
            return
        value_cast = value
    else:
        value_cast = value

    async with get_session() as s:
        await update_coach_config(s, user.coach.id, **{field: value_cast})  # type: ignore[union-attr]

    await state.clear()
    await message.answer(f"✅ Сохранено поле «{SETTING_LABELS[field]}».", reply_markup=coach_main_kb())


# ══════════════════════════════════════════════════════════════
# /athletes — список спортсменов
# ══════════════════════════════════════════════════════════════
@router.message(Command("athletes"))
@router.message(F.text == "👥 Спортсмены")
async def cmd_athletes(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    async with get_session() as s:
        rows = await list_athletes(s, coach_id=user.coach.id)  # type: ignore[union-attr]
    if not rows:
        await message.answer("Пока нет ни одного спортсмена.")
        return
    lines = [f"<b>Всего: {len(rows)}</b>"]
    for a in rows:
        sub = "✅" if a.subscription_active else "—"
        lines.append(
            f"• {a.name} ({a.sport or '?'}, ур.{a.level or '?'}) · подписка {sub}"
        )
    await message.answer("\n".join(lines))


# ══════════════════════════════════════════════════════════════
# /stats — агрегаты
# ══════════════════════════════════════════════════════════════
@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    async with get_session() as s:
        stats = await coach_dashboard_stats(s, user.coach.id)  # type: ignore[union-attr]
    text = (
        "<b>Дашборд тренера</b>\n"
        f"👥 Спортсменов: {stats['athletes']}\n"
        f"✅ Активных подписок: {stats['active_subscriptions']}\n"
        f"💰 Оборот: {money(stats['revenue_minor_units'], config.PAYMENTS_CURRENCY)}\n"
    )
    await message.answer(text)


# ══════════════════════════════════════════════════════════════
# /payments — история оплат
# ══════════════════════════════════════════════════════════════
@router.message(Command("payments"))
@router.message(F.text == "💰 Оплаты")
async def cmd_payments(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    async with get_session() as s:
        payments = await list_payments_for_coach(s, user.coach.id, limit=20)  # type: ignore[union-attr]
    if not payments:
        await message.answer("Оплат пока нет.")
        return
    lines = ["<b>Последние оплаты:</b>"]
    for p in payments:
        lines.append(f"• {p.created_at:%Y-%m-%d %H:%M} — {money(p.amount, p.currency)} — {p.title}")
    await message.answer("\n".join(lines))


# ══════════════════════════════════════════════════════════════
# /broadcast <text> — рассылка всем спортсменам
# ══════════════════════════════════════════════════════════════
@router.message(Command("broadcast"))
@router.message(F.text == "📣 Рассылка")
async def cmd_broadcast(message: Message, user: User | None, bot: Bot) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Использование: <code>/broadcast текст</code>\n"
            "Текст будет отправлен всем привязанным спортсменам."
        )
        return
    async with get_session() as s:
        rows = await list_athletes(s, coach_id=user.coach.id)  # type: ignore[union-attr]
    sent, failed = 0, 0
    for a in rows:
        try:
            if a.user and a.user.telegram_id:
                await bot.send_message(a.user.telegram_id, f"📣 <b>От тренера:</b>\n\n{text}")
                sent += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"broadcast failed to {a.id}: {e}")
    await message.answer(f"Рассылка: отправлено {sent}, ошибок {failed}.")


# ══════════════════════════════════════════════════════════════
# /base — быстрая установка базовой программы
# ══════════════════════════════════════════════════════════════
@router.message(Command("base"))
@router.message(F.text == "📝 Базовая программа")
async def cmd_base(message: Message, state: FSMContext, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    await state.set_state(CoachSettings.waiting_value)
    await state.update_data(field="base_program")
    await message.answer(
        "Напиши базовую программу. Она попадёт в system-prompt агента как методика.\n"
        "Пример: «Понедельник: верх. Среда: кардио 40 мин. Пятница: ноги + кор. Вс: длинная прогулка.»"
    )


# ══════════════════════════════════════════════════════════════
# /setprice — короткая установка цены
# ══════════════════════════════════════════════════════════════
@router.message(Command("setprice"))
async def cmd_setprice(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: <code>/setprice 99900</code> (в копейках)")
        return
    value = int(parts[1])
    async with get_session() as s:
        await update_coach_config(s, user.coach.id, subscription_price=value)  # type: ignore[union-attr]
    await message.answer(f"✅ Цена подписки: {money(value, config.PAYMENTS_CURRENCY)}")


# ══════════════════════════════════════════════════════════════
# /dashboard — ссылка на веб-дашборд
# ══════════════════════════════════════════════════════════════
@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message, user: User | None) -> None:
    if not _is_coach(user):
        await message.answer("Только для тренеров.")
        return
    url = f"{config.WEBAPP_PUBLIC_URL}/coach?tid={user.telegram_id}"
    await message.answer(f"📊 Дашборд тренера: {url}")
