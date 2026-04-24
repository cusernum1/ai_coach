# ============================================================
# app/main.py — Единая точка входа: бот + планировщик + веб
# ============================================================
# Запускает три компонента в одном event loop:
#   1. FastAPI-приложение (uvicorn) — дашборд + Strava callback
#   2. APScheduler — ежедневные опросы и напоминания
#   3. Aiogram-бот (long polling)
#
# Запуск:
#     python -m app.main
# ============================================================

from __future__ import annotations

import asyncio
import os
import signal

import uvicorn
from loguru import logger

from app.bot.main import build_bot, build_dispatcher, run_bot
from app.config import config
from app.db import init_db
from app.scheduler.jobs import build_scheduler


# ── Логирование в файл ───────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logger.add(
    f"{config.LOG_DIR}/app_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)


async def _run_webapp() -> None:
    """Запуск FastAPI через uvicorn (в текущем event loop)."""
    from app.webapp.server import app as fastapi_app

    uv_config = uvicorn.Config(
        fastapi_app,
        host=config.WEBAPP_HOST,
        port=config.WEBAPP_PORT,
        log_level=config.LOG_LEVEL.lower(),
        loop="asyncio",
        access_log=False,
    )
    server = uvicorn.Server(uv_config)
    logger.info(f"FastAPI starting on http://{config.WEBAPP_HOST}:{config.WEBAPP_PORT}")
    await server.serve()


async def main() -> None:
    # 1) Инициализация БД (create_all — для учебного MVP вместо Alembic)
    await init_db()

    # 2) Aiogram — бот и диспетчер
    bot = build_bot()
    dp = build_dispatcher()

    # 3) Планировщик — подхватывает bot для рассылок
    scheduler = build_scheduler(bot)

    # ── Конкурентный запуск всех компонентов ─────────────────
    tasks = {
        asyncio.create_task(run_bot(bot, dp), name="bot"),
        asyncio.create_task(_run_webapp(), name="webapp"),
    }
    scheduler.start()
    logger.info("Scheduler started")

    # Graceful-shutdown по SIGINT/SIGTERM
    stop_event = asyncio.Event()

    def _handle_stop(*_: object) -> None:
        logger.info("Stop signal received")
        stop_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_stop)
            except NotImplementedError:
                # Windows не поддерживает — пропускаем
                pass
    except RuntimeError:
        pass

    # Ждём либо сигнала остановки, либо падения любой таски
    done, pending = await asyncio.wait(
        {*tasks, asyncio.create_task(stop_event.wait(), name="stop_event")},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in done:
        if t.exception():
            logger.error(f"Task {t.get_name()} crashed: {t.exception()}")

    # Останавливаемся
    scheduler.shutdown(wait=False)
    for t in pending:
        t.cancel()
    await bot.session.close()
    logger.info("Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
