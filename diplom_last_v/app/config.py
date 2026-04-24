# ============================================================
# app/config.py — Единая конфигурация приложения (v3)
# ============================================================
# Централизованная точка конфигурации: LLM, Postgres,
# Telegram-бот, Strava OAuth, Telegram Payments, WebApp.
# Все значения читаются из переменных окружения (.env)
# с fail-fast валидацией при старте.
# ============================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# ── Загружаем .env автоматически при импорте конфига ──────────
# Код теперь живёт в diplom_last_v/, а .env остаётся в корне репозитория
# (пользователь попросил его не трогать). find_dotenv() поднимается
# по дереву каталогов и находит .env у корня. Fallback — рядом с пакетом.
_dotenv_path = find_dotenv(usecwd=True)
if not _dotenv_path:
    # Пробуем корень репозитория: diplom_last_v/app/ → ../../.env
    _candidate = Path(__file__).resolve().parents[2] / ".env"
    if _candidate.exists():
        _dotenv_path = str(_candidate)
load_dotenv(_dotenv_path or None)


def _env(name: str, default: str = "") -> str:
    """Безопасное чтение переменной окружения (strip whitespace)."""
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    """Целочисленная переменная окружения."""
    raw = _env(name)
    return int(raw) if raw else default


def _env_bool(name: str, default: bool = False) -> bool:
    """Булева переменная окружения (true/1/yes)."""
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "y")


@dataclass
class AppConfig:
    """
    Единый объект конфигурации проекта.

    Блоки:
      • LLM (Groq / OpenRouter)
      • Telegram-бот (токен, админ)
      • PostgreSQL (DSN)
      • Планировщик (таймзона, время опроса)
      • Strava (client_id/secret, redirect_uri)
      • Telegram Payments (provider_token)
      • WebApp (URL мини-приложения + порт FastAPI)
      • Логи и пути (fonts, logs)
    """

    # ── Провайдер LLM: groq | openrouter ─────────────────────
    LLM_PROVIDER: str = field(default_factory=lambda: _env("LLM_PROVIDER", "groq"))

    # ── Groq ─────────────────────────────────────────────────
    GROQ_API_KEY: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    GROQ_MODEL: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))

    # ── OpenRouter ───────────────────────────────────────────
    OPENROUTER_API_KEY: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    OPENROUTER_MODEL: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"))
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ── LLM-параметры ────────────────────────────────────────
    MAX_TOKENS: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 2048))
    TEMPERATURE: float = field(default_factory=lambda: float(_env("TEMPERATURE", "0.7")))
    MAX_AGENT_ITERATIONS: int = 5
    CHAT_MEMORY_SIZE: int = 6

    # ── Telegram-бот ─────────────────────────────────────────
    # Получить у @BotFather: /newbot → токен
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    # Telegram ID первого тренера-администратора (можно узнать у @userinfobot)
    # При старте бота этот пользователь автоматически получит роль COACH.
    ADMIN_TELEGRAM_ID: int = field(default_factory=lambda: _env_int("ADMIN_TELEGRAM_ID", 0))
    # Имя бота для обращений
    BOT_NAME: str = field(default_factory=lambda: _env("BOT_NAME", "AI Coach"))

    # ── База данных (PostgreSQL, async DSN) ──────────────────
    # Пример: postgresql+asyncpg://user:pass@localhost:5432/ai_coach
    DATABASE_URL: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coach",
        )
    )
    # Флаг для dev-режима: sqlite fallback, если выставлен SQLITE_FALLBACK=1
    SQLITE_FALLBACK: bool = field(default_factory=lambda: _env_bool("SQLITE_FALLBACK", False))

    # ── Планировщик (APScheduler) ────────────────────────────
    SCHEDULER_TIMEZONE: str = field(default_factory=lambda: _env("SCHEDULER_TIMEZONE", "Europe/Moscow"))
    # Время ежедневного утреннего опроса спортсменов: HH:MM
    DAILY_POLL_TIME: str = field(default_factory=lambda: _env("DAILY_POLL_TIME", "08:00"))

    # ── Strava OAuth ─────────────────────────────────────────
    # https://www.strava.com/settings/api
    STRAVA_CLIENT_ID: str = field(default_factory=lambda: _env("STRAVA_CLIENT_ID"))
    STRAVA_CLIENT_SECRET: str = field(default_factory=lambda: _env("STRAVA_CLIENT_SECRET"))
    # URL, на который Strava вернёт пользователя после авторизации
    # Должен совпадать с настройкой в личном кабинете Strava API.
    STRAVA_REDIRECT_URI: str = field(
        default_factory=lambda: _env("STRAVA_REDIRECT_URI", "http://localhost:8080/strava/callback")
    )

    # ── Telegram Payments ────────────────────────────────────
    # Provider-токен выдаётся в @BotFather → Payments → выбрать провайдера
    # (ЮKassa, Stripe Test и т.д.)
    PAYMENTS_PROVIDER_TOKEN: str = field(default_factory=lambda: _env("PAYMENTS_PROVIDER_TOKEN"))
    PAYMENTS_CURRENCY: str = field(default_factory=lambda: _env("PAYMENTS_CURRENCY", "RUB"))

    # ── Web Mini-App (FastAPI) ───────────────────────────────
    WEBAPP_HOST: str = field(default_factory=lambda: _env("WEBAPP_HOST", "0.0.0.0"))
    WEBAPP_PORT: int = field(default_factory=lambda: _env_int("WEBAPP_PORT", 8080))
    # Публичный URL мини-приложения, который открывается кнопкой Web App в TG.
    # Для локальной разработки можно использовать ngrok.
    WEBAPP_PUBLIC_URL: str = field(
        default_factory=lambda: _env("WEBAPP_PUBLIC_URL", "http://localhost:8080")
    )

    # ── Логи ─────────────────────────────────────────────────
    LOG_DIR: str = "logs"
    LOG_ROTATION: str = "1 MB"
    LOG_RETENTION: str = "7 days"
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # ── App meta ─────────────────────────────────────────────
    APP_TITLE: str = "AI Coach — Telegram + WebApp"
    APP_VERSION: str = "3.0.0"

    # ── Шрифты для PDF (из legacy-ядра) ──────────────────────
    FONT_DIR: str = "fonts"
    FONT_REGULAR: str = "fonts/DejaVuSans.ttf"
    FONT_BOLD: str = "fonts/DejaVuSans-Bold.ttf"

    # ── Метрики ──────────────────────────────────────────────
    WELLNESS_FATIGUE_WEIGHT: float = 5.0
    WELLNESS_SLEEP_WEIGHT: float = 5.0
    MIN_RESPONSE_QUALITY: float = 50.0

    # ─────────────────────────────────────────────────────────
    #   Производные свойства
    # ─────────────────────────────────────────────────────────

    @property
    def MODEL_NAME(self) -> str:
        """Имя модели LLM в зависимости от активного провайдера."""
        if self.LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_MODEL
        return self.GROQ_MODEL

    @property
    def API_KEY(self) -> str:
        """Активный API-ключ LLM."""
        if self.LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_API_KEY
        return self.GROQ_API_KEY

    @property
    def effective_database_url(self) -> str:
        """
        Фактический DSN БД.
        Если SQLITE_FALLBACK=1 — используем локальный SQLite (для dev без Postgres).
        """
        if self.SQLITE_FALLBACK:
            return "sqlite+aiosqlite:///coach.db"
        return self.DATABASE_URL

    # ─────────────────────────────────────────────────────────
    #   Fail-fast валидация
    # ─────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        # LLM-провайдер
        if self.LLM_PROVIDER not in ("groq", "openrouter"):
            raise ValueError(
                f"LLM_PROVIDER='{self.LLM_PROVIDER}' не поддерживается. "
                f"Используйте 'groq' или 'openrouter'."
            )

        # LLM-ключ (критично для работы агента)
        if not self.API_KEY:
            key_name = "OPENROUTER_API_KEY" if self.LLM_PROVIDER == "openrouter" else "GROQ_API_KEY"
            raise ValueError(
                f"API-ключ LLM не задан. Укажите {key_name} в .env "
                f"(см. .env.example)."
            )

        # Telegram-токен (без него бот не запустится,
        # но конфиг может использоваться только для webapp — делаем мягкое предупреждение)
        # Строгую проверку делаем в bot/main.py перед стартом диспетчера.

        # Границы LLM-параметров
        if not (1 <= self.MAX_AGENT_ITERATIONS <= 10):
            raise ValueError("MAX_AGENT_ITERATIONS должен быть 1..10")
        if not (0.0 <= self.TEMPERATURE <= 2.0):
            raise ValueError("TEMPERATURE должен быть 0.0..2.0")


# ── Глобальный синглтон конфигурации ──────────────────────────
config = AppConfig()
