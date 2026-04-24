# ============================================================
# app/db/database.py — Engine + async session factory
# ============================================================
# Построено на SQLAlchemy 2.0 (async API).
# • engine         — общий AsyncEngine, создаётся один раз.
# • AsyncSessionLocal — фабрика async-сессий.
# • get_session()  — асинхронный контекстный менеджер сессии
#                    с автокоммитом/откатом.
# • init_db()      — создаёт все таблицы (упрощённая замена Alembic
#                    для dev/учебных целей).
# ============================================================

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import config


# ── Базовый класс ORM-моделей ────────────────────────────────
class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей (SQLAlchemy 2.x declarative)."""
    pass


# ── Async-engine (ленивое создание) ──────────────────────────
# echo=False: SQL в логи не пишем (можно включить при отладке).
# pool_pre_ping=True: проверяем соединение перед использованием,
# что важно для длительно работающего бота (reconnect на reset).
engine = create_async_engine(
    config.effective_database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

# Фабрика сессий. expire_on_commit=False — чтобы объекты оставались
# «живыми» после commit (нужно при возврате ORM-объектов хэндлерам бота).
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Асинхронный контекстный менеджер для работы с БД.

    Использование::

        async with get_session() as s:
            user = await s.get(User, 1)

    Автоматически commit при успешном выходе, rollback при исключении.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """
    Создаёт все таблицы, описанные в моделях (metadata.create_all).

    Для учебного/дипломного проекта этого достаточно.
    В продакшне вместо этого использовать Alembic-миграции.
    """
    # Импортируем модели здесь, чтобы зарегистрировать их в Base.metadata
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB schema ensured (Base.metadata.create_all)")
