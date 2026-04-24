# ============================================================
# app/db/models.py — ORM-модели (SQLAlchemy 2.x, async)
# ============================================================
# Предметная модель AI-Coach v3:
#
#   User       — любой пользователь Telegram (1:1 с профилем)
#   Coach      — роль тренера (1:N у User, но на старте 1:1)
#   CoachConfig — настройки бота у конкретного тренера
#                 (название, лого, базовая программа, цены)
#   Athlete    — спортсмен, закреплённый за тренером
#   Plan       — тренировочный план спортсмена
#   Session    — фактическая тренировка/результат
#   TrainingLog — запись журнала (факт vs план, RPE, заметки)
#   Poll / PollAnswer — опросник (ежедневный, еженедельный)
#   Payment    — оплата услуг тренера через Telegram Payments
#   StravaToken — OAuth-токены пользователя Strava
# ============================================================

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ── Роль пользователя ────────────────────────────────────────
class Role(str, enum.Enum):
    """Ролевая модель: COACH настраивает бота, ATHLETE пользуется."""
    COACH = "coach"
    ATHLETE = "athlete"
    UNKNOWN = "unknown"  # впервые зашёл, роль ещё не выбрана


# ── User (Telegram-профиль) ──────────────────────────────────
class User(Base):
    """
    Пользователь Telegram (уникален по telegram_id).
    Один User может быть либо COACH, либо ATHLETE.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=16),
        default=Role.UNKNOWN,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # ── Связи ────────────────────────────────────────────────
    coach: Mapped[Optional["Coach"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    athlete: Mapped[Optional["Athlete"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    strava_token: Mapped[Optional["StravaToken"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


# ── Coach ────────────────────────────────────────────────────
class Coach(Base):
    """Тренер — владелец конфигурации и списка спортсменов."""
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    display_name: Mapped[str] = mapped_column(String(255), default="Тренер")

    user: Mapped[User] = relationship(back_populates="coach")
    athletes: Mapped[list["Athlete"]] = relationship(back_populates="coach")
    config: Mapped[Optional["CoachConfig"]] = relationship(
        back_populates="coach", uselist=False, cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="coach")


# ── CoachConfig — кастомизация бота под тренера ───────────────
class CoachConfig(Base):
    """
    Настройки работы бота конкретного тренера:
    • бренд: название, логотип
    • базовая программа (шаблон плана, который агент использует как basis)
    • цена услуги и описание тарифа
    • расписание опросов (перекрывает глобальное)
    Тренер меняет всё это через чат-команды бота.
    """
    __tablename__ = "coach_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("coaches.id", ondelete="CASCADE"), unique=True
    )

    # Бренд
    brand_name: Mapped[str] = mapped_column(String(255), default="AI Coach")
    logo_url: Mapped[Optional[str]] = mapped_column(String(1024))
    welcome_message: Mapped[str] = mapped_column(
        Text, default="Привет! Я твой AI-тренер. Спроси меня о плане или восстановлении."
    )

    # Базовая программа — произвольный текст/шаблон, который агент
    # добавит в system-prompt как ориентир.
    base_program: Mapped[str] = mapped_column(
        Text, default="Базовая программа: 3 тренировки в неделю — сила, выносливость, восстановление."
    )

    # Цена подписки (копейки, минимальная единица — для TG Payments)
    subscription_price: Mapped[int] = mapped_column(Integer, default=100000)  # 1000 руб
    subscription_title: Mapped[str] = mapped_column(String(255), default="Месячная подписка")
    subscription_description: Mapped[str] = mapped_column(
        Text, default="Персональные планы, еженедельный анализ, расписание от тренера."
    )

    # Расписание опросов
    daily_poll_time: Mapped[str] = mapped_column(String(5), default="08:00")
    weekly_summary_day: Mapped[int] = mapped_column(Integer, default=0)  # 0=пн
    polls_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    coach: Mapped[Coach] = relationship(back_populates="config")


# ── Athlete ──────────────────────────────────────────────────
class Athlete(Base):
    """Спортсмен. Привязан к одному тренеру."""
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    coach_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("coaches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Анкета спортсмена
    name: Mapped[str] = mapped_column(String(255))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    sport: Mapped[Optional[str]] = mapped_column(String(64))
    level: Mapped[Optional[str]] = mapped_column(String(64))
    goal: Mapped[Optional[str]] = mapped_column(String(255))
    sessions_per_week: Mapped[Optional[int]] = mapped_column(Integer)

    # Служебное
    subscription_active: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="athlete")
    coach: Mapped[Optional[Coach]] = relationship(back_populates="athletes")

    plans: Mapped[list["Plan"]] = relationship(back_populates="athlete", cascade="all, delete-orphan")
    sessions: Mapped[list["Session"]] = relationship(back_populates="athlete", cascade="all, delete-orphan")
    logs: Mapped[list["TrainingLog"]] = relationship(back_populates="athlete", cascade="all, delete-orphan")
    polls: Mapped[list["Poll"]] = relationship(back_populates="athlete", cascade="all, delete-orphan")


# ── Plan ─────────────────────────────────────────────────────
class Plan(Base):
    """Сформированный тренером/агентом план тренировок."""
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="План тренировок")
    focus: Mapped[str] = mapped_column(String(64), default="общая подготовка")
    content: Mapped[str] = mapped_column(Text)  # Markdown / plain text
    weeks: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    athlete: Mapped[Athlete] = relationship(back_populates="plans")


# ── Session (результат тренировки) ───────────────────────────
class Session(Base):
    """Запись о физиологическом состоянии / результате тренировки."""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    fatigue: Mapped[int] = mapped_column(Integer)        # 1..10
    sleep_quality: Mapped[int] = mapped_column(Integer)  # 1..10
    results: Mapped[str] = mapped_column(Text, default="")
    pain: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    athlete: Mapped[Athlete] = relationship(back_populates="sessions")


# ── TrainingLog (план vs факт) ───────────────────────────────
class TrainingLog(Base):
    """Журнал тренировок: фактическое выполнение плана."""
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    log_date: Mapped[date] = mapped_column(Date)
    day_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))   # выполнено / частично / пропущено
    rpe: Mapped[int] = mapped_column(Integer, default=0)  # 0..10
    notes: Mapped[str] = mapped_column(Text, default="")
    # Источник: manual | strava
    source: Mapped[str] = mapped_column(String(32), default="manual")
    external_id: Mapped[Optional[str]] = mapped_column(String(64))  # id активности в Strava

    athlete: Mapped[Athlete] = relationship(back_populates="logs")


# ── Poll / PollAnswer (опросники) ────────────────────────────
class Poll(Base):
    """Опрос — набор вопросов, отправляемый спортсмену планировщиком."""
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="daily")  # daily / weekly / custom
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    athlete: Mapped[Athlete] = relationship(back_populates="polls")
    answers: Mapped[list["PollAnswer"]] = relationship(
        back_populates="poll", cascade="all, delete-orphan"
    )


class PollAnswer(Base):
    """Одиночный ответ на вопрос опроса."""
    __tablename__ = "poll_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(String(255))
    answer: Mapped[str] = mapped_column(Text)

    poll: Mapped[Poll] = relationship(back_populates="answers")


# ── Payment (Telegram Payments) ──────────────────────────────
class Payment(Base):
    """История успешных оплат подписки (через Telegram Payments)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    coach_id: Mapped[Optional[int]] = mapped_column(ForeignKey("coaches.id", ondelete="SET NULL"))
    amount: Mapped[int] = mapped_column(Integer)              # минимальные единицы (копейки)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    title: Mapped[str] = mapped_column(String(255))
    telegram_charge_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    provider_charge_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    coach: Mapped[Optional[Coach]] = relationship(back_populates="payments")


# ── StravaToken ──────────────────────────────────────────────
class StravaToken(Base):
    """OAuth2-токены Strava (обновляются refresh_token'ом)."""
    __tablename__ = "strava_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    access_token: Mapped[str] = mapped_column(String(255))
    refresh_token: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[int] = mapped_column(Integer)     # unix ts
    athlete_id_strava: Mapped[Optional[int]] = mapped_column(BigInteger)
    connected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="strava_token")

    __table_args__ = (UniqueConstraint("user_id", name="uq_strava_tokens_user"),)
