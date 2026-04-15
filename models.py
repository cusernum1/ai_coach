# ============================================================
# models.py — Pydantic-модели данных с валидацией
# ============================================================
# Все входные данные проходят через эти модели перед
# сохранением в БД или отправкой агенту. Это гарантирует
# целостность данных и предотвращает ошибки на этапе ввода.
# ============================================================

from pydantic import BaseModel, Field, field_validator
from typing import Optional,ClassVar, List
from datetime import date



# ── Профиль спортсмена ────────────────────────────────────────

class AthleteProfile(BaseModel):
    """
    Модель профиля спортсмена.

    Валидация:
    - Имя: 2–100 символов, автоматически очищается от пробелов
    - Возраст: 10–80 лет
    - Тренировки в неделю: 1–7
    - Спорт, уровень, цель: из фиксированных списков
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Имя спортсмена (2–100 символов)",
    )
    age: int = Field(
        ...,
        ge=10,
        le=80,
        description="Возраст (10–80 лет)",
    )
    sport: str = Field(
        ...,
        description="Вид спорта",
    )
    level: str = Field(
        ...,
        description="Уровень подготовки",
    )
    goal: str = Field(
        ...,
        description="Тренировочная цель",
    )
    sessions_per_week: int = Field(
        ...,
        ge=1,
        le=7,
        description="Количество тренировок в неделю (1–7)",
    )

    VALID_SPORTS: ClassVar[List[str]] = [
        "Бег", "Плавание", "Велоспорт", "Футбол",
        "Баскетбол", "Тяжёлая атлетика", "Теннис", "Другое",
    ]
    VALID_LEVELS: ClassVar[List[str]] = [
        "Начинающий", "Любитель", "Полупрофессионал", "Профессионал",
    ]
    VALID_GOALS: ClassVar[List[str]] = [
        "Похудение", "Набор мышечной массы", "Выносливость",
        "Подготовка к соревнованиям", "Общая физическая форма",
    ]

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("name")
    @classmethod
    def strip_and_validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Имя должно содержать минимум 2 символа")
        return v

    @field_validator("sport")
    @classmethod
    def validate_sport(cls, v: str) -> str:
        if v not in cls.VALID_SPORTS:
            raise ValueError(f"Неизвестный вид спорта: {v}")
        return v

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v not in cls.VALID_LEVELS:
            raise ValueError(f"Неизвестный уровень: {v}")
        return v

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        if v not in cls.VALID_GOALS:
            raise ValueError(f"Неизвестная цель: {v}")
        return v

    def to_dict(self) -> dict:
        """Конвертация в dict для БД и агента"""
        return {
            "name": self.name,
            "age": self.age,
            "sport": self.sport,
            "level": self.level,
            "goal": self.goal,
            "sessions_per_week": self.sessions_per_week,
        }


# ── Запись тренировочной сессии ────────────────────────────────

class SessionRecord(BaseModel):
    """
    Модель записи результатов тренировки.
    Содержит физиологические показатели для анализа агентом.
    """

    athlete_id: int = Field(
        ...,
        ge=1,
        description="ID спортсмена в БД",
    )
    fatigue: int = Field(
        ...,
        ge=1,
        le=10,
        description="Уровень усталости (1=нет — 10=истощение)",
    )
    sleep_quality: int = Field(
        ...,
        ge=1,
        le=10,
        description="Качество сна (1=плохой — 10=отличный)",
    )
    results: str = Field(
        default="",
        max_length=2000,
        description="Результаты тренировки (свободный текст)",
    )
    pain: str = Field(
        default="",
        max_length=500,
        description="Боли и дискомфорт",
    )


# ── Запись журнала тренировок ─────────────────────────────────

class TrainingLogEntry(BaseModel):
    """
    Модель записи в журнале тренировок.
    Отслеживает выполнение плана по дням.
    """

    athlete_id: int = Field(..., ge=1)
    log_date: str = Field(
        ...,
        description="Дата тренировки (YYYY-MM-DD)",
    )
    day_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Название тренировки",
    )
    status: str = Field(
        ...,
        description="Статус выполнения",
    )
    rpe: int = Field(
        default=0,
        ge=0,
        le=10,
        description="RPE — воспринимаемое усилие (0=нет, 1–10 шкала)",
    )
    notes: str = Field(
        default="",
        max_length=1000,
        description="Заметки",
    )

    VALID_STATUSES: ClassVar[List[str]] = ["выполнено", "частично", "пропущено"]

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in cls.VALID_STATUSES:
            raise ValueError(f"Неизвестный статус: {v}. Допустимые: {cls.VALID_STATUSES}")
        return v

    @field_validator("day_name")
    @classmethod
    def strip_day_name(cls, v: str) -> str:
        return v.strip()


# ── Модель запроса к агенту (для логирования) ─────────────────

class AgentQuery(BaseModel):
    """Модель запроса пользователя к агенту"""

    athlete_id: int = Field(..., ge=1)
    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Текст запроса",
    )

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()
