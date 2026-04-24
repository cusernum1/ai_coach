# ============================================================
# app/bot/main.py — Построение Bot + Dispatcher (aiogram 3)
# ============================================================
# Создаёт объект бота, цепляет middleware, подключает все
# роутеры. Сам polling запускается в run(), который вызывается
# из общего entrypoint app.main.
# ============================================================

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from app.bot.handlers import setup_routers
from app.bot.middlewares import UserContextMiddleware
from app.config import config


def build_bot() -> Bot:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. "
            "Получите токен у @BotFather и пропишите в .env."
        )
    return Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Middleware ставим на оба типа обновлений — message и callback
    mw = UserContextMiddleware()
    dp.message.middleware(mw)
    dp.callback_query.middleware(mw)
    dp.pre_checkout_query.middleware(mw)

    dp.include_router(setup_routers())
    return dp


async def run_bot(bot: Bot, dp: Dispatcher) -> None:
    """Запустить long polling Telegram."""
    logger.info(f"Bot polling started as @{(await bot.me()).username}")
    # drop_pending_updates=True — при перезапуске не обрабатываем «висящие» апдейты
    await dp.start_polling(bot, drop_pending_updates=True)
