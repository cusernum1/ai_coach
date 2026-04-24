# ============================================================
# app/bot/handlers/payments.py — Telegram Payments: подписка
# ============================================================

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery
from loguru import logger

from app.bot.keyboards import athlete_main_kb
from app.bot.utils import money
from app.config import config
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import (
    activate_subscription,
    get_coach_config,
    get_default_coach,
    record_payment,
)
from app.integrations.payments import send_subscription_invoice

router = Router(name="payments")


# ── Запуск оплаты ────────────────────────────────────────────
@router.message(Command("subscribe"))
@router.message(F.text == "💳 Подписка")
async def cmd_subscribe(message: Message, user: User | None, bot: Bot) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Только для спортсменов.")
        return
    async with get_session() as s:
        coach = await get_default_coach(s)
        cfg = await get_coach_config(s, coach.id) if coach else None

    if cfg is None or not config.PAYMENTS_PROVIDER_TOKEN:
        await message.answer(
            "⚠️ Оплата временно недоступна (тренер не задал цену или провайдер не настроен)."
        )
        return

    try:
        await send_subscription_invoice(
            bot,
            chat_id=message.chat.id,
            title=cfg.subscription_title,
            description=cfg.subscription_description,
            amount_minor=cfg.subscription_price,
            payload=f"sub:{user.id}:{coach.id}",  # в pre_checkout распарсим
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"send_invoice failed: {e}")
        await message.answer(f"Не удалось отправить инвойс: {e}")


# ── Pre-checkout: Telegram ждёт ACK в 10 сек ─────────────────
@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery) -> None:
    # Валидация payload — должно быть sub:user_id:coach_id
    ok = pcq.invoice_payload.startswith("sub:") and pcq.total_amount > 0
    await pcq.answer(ok=ok, error_message="Оплата не прошла валидацию" if not ok else None)


# ── Успешная оплата ──────────────────────────────────────────
@router.message(F.successful_payment)
async def on_successful_payment(message: Message, user: User) -> None:
    sp = message.successful_payment
    if sp is None or user is None:
        return
    try:
        _, user_id_str, coach_id_str = sp.invoice_payload.split(":", 2)
        uid = int(user_id_str)
        cid = int(coach_id_str)
    except ValueError:
        uid, cid = user.id, None  # type: ignore[assignment]

    async with get_session() as s:
        await record_payment(
            s,
            user_id=uid,
            coach_id=cid,
            amount=sp.total_amount,
            currency=sp.currency,
            title=sp.order_info.name if sp.order_info else "Подписка",
            telegram_charge_id=sp.telegram_payment_charge_id,
            provider_charge_id=sp.provider_payment_charge_id,
        )
        await activate_subscription(s, uid, days=30)

    await message.answer(
        f"✅ Оплата принята: {money(sp.total_amount, sp.currency)}.\n"
        f"Подписка активна на 30 дней. Спасибо!",
        reply_markup=athlete_main_kb(),
    )
