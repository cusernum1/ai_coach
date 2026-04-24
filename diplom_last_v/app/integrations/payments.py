# ============================================================
# app/integrations/payments.py — Telegram Payments
# ============================================================
# Используем встроенные Telegram Payments: bot.send_invoice().
# Провайдер — ЮKassa или Stripe-test, настраивается через
# @BotFather → Payments → выбрать и получить provider_token.
#
# Flow:
#   1. /subscribe -> send_invoice
#   2. PreCheckoutQuery — подтверждаем (или отказываем)
#   3. SuccessfulPayment — активируем подписку, пишем в Payment
# ============================================================

from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice

from app.config import config


async def send_subscription_invoice(
    bot: Bot,
    *,
    chat_id: int,
    title: str,
    description: str,
    amount_minor: int,
    payload: str,
) -> None:
    """
    Отправляет инвойс на оплату подписки.

    amount_minor — сумма в минимальных единицах (копейках/центах).
    payload      — произвольная строка, возвращается в SuccessfulPayment.
    """
    if not config.PAYMENTS_PROVIDER_TOKEN:
        raise RuntimeError(
            "PAYMENTS_PROVIDER_TOKEN не задан в .env — "
            "получите его у @BotFather → Payments → провайдер."
        )

    await bot.send_invoice(
        chat_id=chat_id,
        title=title[:32] or "Подписка",
        description=description[:255] or "Подписка на услуги тренера",
        payload=payload,
        provider_token=config.PAYMENTS_PROVIDER_TOKEN,
        currency=config.PAYMENTS_CURRENCY,
        prices=[LabeledPrice(label=title[:32] or "Подписка", amount=amount_minor)],
        need_email=False,
        need_name=False,
        need_phone_number=False,
        is_flexible=False,
        start_parameter="subscribe",
    )
