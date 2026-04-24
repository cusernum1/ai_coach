# ============================================================
# app/bot/keyboards.py — Клавиатуры бота (reply + inline)
# ============================================================
# Разделены по ролям: тренер видит одни кнопки, спортсмен — другие.
# WebApp-кнопка запускает мини-приложение (FastAPI-дашборд).
# ============================================================

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import config


# ── Выбор роли (для новых пользователей) ─────────────────────
def role_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍🏫 Я тренер", callback_data="role:coach")],
            [InlineKeyboardButton(text="🏃 Я спортсмен", callback_data="role:athlete")],
        ]
    )


# ── Главное меню спортсмена ──────────────────────────────────
def athlete_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📋 План"), KeyboardButton(text="📓 Журнал")],
        [KeyboardButton(text="💪 Самочувствие"), KeyboardButton(text="🍎 Питание")],
        [KeyboardButton(text="🔗 Strava"), KeyboardButton(text="💳 Подписка")],
    ]
    # Кнопка-запуск мини-приложения (дашборд в TG)
    if config.WEBAPP_PUBLIC_URL.startswith("https"):
        rows.append([
            KeyboardButton(
                text="📊 Дашборд",
                web_app=WebAppInfo(url=config.WEBAPP_PUBLIC_URL),
            )
        ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ── Главное меню тренера ─────────────────────────────────────
def coach_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👥 Спортсмены"), KeyboardButton(text="⚙️ Настройки бота")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💰 Оплаты")],
        [KeyboardButton(text="📝 Базовая программа"), KeyboardButton(text="📣 Рассылка")],
    ]
    if config.WEBAPP_PUBLIC_URL.startswith("https"):
        rows.append([
            KeyboardButton(
                text="📊 Открыть дашборд",
                web_app=WebAppInfo(url=f"{config.WEBAPP_PUBLIC_URL}/coach"),
            )
        ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ── Настройки тренера (inline) ───────────────────────────────
def coach_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Название", callback_data="set:brand_name")],
            [InlineKeyboardButton(text="🖼 Логотип", callback_data="set:logo_url")],
            [InlineKeyboardButton(text="👋 Приветствие", callback_data="set:welcome_message")],
            [InlineKeyboardButton(text="📝 Базовая программа", callback_data="set:base_program")],
            [InlineKeyboardButton(text="💰 Цена подписки", callback_data="set:subscription_price")],
            [InlineKeyboardButton(text="⏰ Время опроса", callback_data="set:daily_poll_time")],
            [InlineKeyboardButton(text="🔔 Вкл/выкл опросы", callback_data="set:polls_toggle")],
        ]
    )


# ── Оценка самочувствия (inline 1–10) ────────────────────────
def scale_kb(prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура 1..10 — для выбора значения в опросе самочувствия."""
    row1 = [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


# ── Статусы тренировки ───────────────────────────────────────
def training_status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data="log_status:выполнено"),
                InlineKeyboardButton(text="~ Частично", callback_data="log_status:частично"),
                InlineKeyboardButton(text="⛔ Пропущено", callback_data="log_status:пропущено"),
            ],
        ]
    )


# ── Подтверждение ────────────────────────────────────────────
def confirm_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"{prefix}:no"),
            ]
        ]
    )
