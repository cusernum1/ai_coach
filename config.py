# ============================================================
# config.py — Конфигурация приложения
# ============================================================
# Централизованное управление параметрами: LLM-провайдер,
# модели, лимиты, пути к файлам. Fail-fast при ошибках.
# ============================================================

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    """
    Единая точка конфигурации приложения.

    Параметры загружаются из переменных окружения (.env),
    а при их отсутствии используются значения по умолчанию.
    Критические параметры (API-ключи) валидируются при старте.
    """

    # ── Провайдер: groq или openrouter ────────────────────────
    LLM_PROVIDER: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "groq")
    )

    # ── Groq ─────────────────────────────────────────────────
    GROQ_API_KEY: str = field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", "")
    )
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── OpenRouter ───────────────────────────────────────────
    OPENROUTER_API_KEY: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    OPENROUTER_MODEL: str = "openai/gpt-oss-120b:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ── Общие параметры LLM ──────────────────────────────────
    MAX_TOKENS: int = 2048
    TEMPERATURE: float = 0.7
    MAX_AGENT_ITERATIONS: int = 5

    # ── Database ─────────────────────────────────────────────
    DB_NAME: str = "coach.db"

    # ── Logging ──────────────────────────────────────────────
    LOG_DIR: str = "logs"
    LOG_ROTATION: str = "1 MB"
    LOG_RETENTION: str = "7 days"
    LOG_LEVEL: str = "INFO"

    # ── App ──────────────────────────────────────────────────
    APP_TITLE: str = "ИИ-агент спортивного тренера"
    APP_VERSION: str = "2.0.0"

    # ── PDF Fonts ─────────────────────────────────────────────
    FONT_DIR: str = "fonts"
    FONT_REGULAR: str = "fonts/DejaVuSans.ttf"
    FONT_BOLD: str = "fonts/DejaVuSans-Bold.ttf"

    # ── Метрики и оценка качества ─────────────────────────────
    WELLNESS_FATIGUE_WEIGHT: float = 5.0
    WELLNESS_SLEEP_WEIGHT: float = 5.0
    MIN_RESPONSE_QUALITY: float = 50.0  # мин. % для «хорошего» ответа

    # ── Chat memory ──────────────────────────────────────────
    CHAT_MEMORY_SIZE: int = 6  # кол-во сообщений контекста (пары user/assistant)

    @property
    def MODEL_NAME(self) -> str:
        if self.LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_MODEL
        return self.GROQ_MODEL

    @property
    def API_KEY(self) -> str:
        if self.LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_API_KEY
        return self.GROQ_API_KEY

    def __post_init__(self):
        """Валидация при создании — fail-fast"""
        valid_providers = ("groq", "openrouter")
        if self.LLM_PROVIDER not in valid_providers:
            raise ValueError(
                f"LLM_PROVIDER='{self.LLM_PROVIDER}' не поддерживается. "
                f"Допустимые: {valid_providers}"
            )

        if not self.API_KEY:
            key_name = (
                "OPENROUTER_API_KEY"
                if self.LLM_PROVIDER == "openrouter"
                else "GROQ_API_KEY"
            )
            raise ValueError(
                f"API-ключ не задан. Создайте файл .env и укажите {key_name}. "
                f"Шаблон: cp .env.example .env"
            )

        if self.MAX_AGENT_ITERATIONS < 1 or self.MAX_AGENT_ITERATIONS > 10:
            raise ValueError("MAX_AGENT_ITERATIONS должен быть от 1 до 10")

        if self.TEMPERATURE < 0 or self.TEMPERATURE > 2:
            raise ValueError("TEMPERATURE должен быть от 0.0 до 2.0")


config = AppConfig()
