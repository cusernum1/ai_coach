# ============================================================
# app/db/repo.py — Репозитории (CRUD-операции поверх моделей)
# ============================================================
# Репозитории группируют все запросы, чтобы хэндлеры бота
# и веб-приложения не писали SQL напрямую. Все функции — async
# и принимают AsyncSession, полученную из get_session().
# ============================================================

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Athlete,
    Coach,
    CoachConfig,
    Payment,
    Plan,
    Poll,
    PollAnswer,
    Role,
    Session as SessionRow,
    StravaToken,
    TrainingLog,
    User,
)


# =============================================================
#                        Users & Roles
# =============================================================

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    """Найти пользователя по telegram_id или создать нового (без роли)."""
    q = select(User).where(User.telegram_id == telegram_id)
    user = (await session.execute(q)).scalar_one_or_none()
    if user:
        # Обновим имя/юзернейм на случай изменений в TG
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if changed:
            await session.flush()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        role=Role.UNKNOWN,
    )
    session.add(user)
    await session.flush()
    return user


async def set_role(session: AsyncSession, user: User, role: Role) -> None:
    """Установить роль пользователя и создать связанный профиль."""
    user.role = role
    await session.flush()

    if role == Role.COACH and user.coach is None:
        coach = Coach(user_id=user.id, display_name=user.full_name or "Тренер")
        session.add(coach)
        await session.flush()
        # Сразу создаём дефолтную конфигурацию
        session.add(CoachConfig(coach_id=coach.id))
        await session.flush()

    if role == Role.ATHLETE and user.athlete is None:
        session.add(Athlete(
            user_id=user.id,
            name=user.full_name or (user.username or "Спортсмен"),
        ))
        await session.flush()


async def get_user_with_profile(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """Получить пользователя со всеми связанными профилями (coach/athlete)."""
    q = (
        select(User)
        .where(User.telegram_id == telegram_id)
        .options(
            selectinload(User.coach).selectinload(Coach.config),
            selectinload(User.athlete).selectinload(Athlete.coach),
            selectinload(User.strava_token),
        )
    )
    return (await session.execute(q)).scalar_one_or_none()


# =============================================================
#                        Coach / Config
# =============================================================

async def get_default_coach(session: AsyncSession) -> Optional[Coach]:
    """Получить первого (админского) тренера — MVP-привязка спортсменов."""
    q = select(Coach).options(selectinload(Coach.config)).order_by(Coach.id).limit(1)
    return (await session.execute(q)).scalar_one_or_none()


async def get_coach_config(session: AsyncSession, coach_id: int) -> Optional[CoachConfig]:
    q = select(CoachConfig).where(CoachConfig.coach_id == coach_id)
    return (await session.execute(q)).scalar_one_or_none()


async def update_coach_config(session: AsyncSession, coach_id: int, **fields) -> CoachConfig:
    """Частичное обновление настроек тренера."""
    cfg = await get_coach_config(session, coach_id)
    if cfg is None:
        cfg = CoachConfig(coach_id=coach_id)
        session.add(cfg)
    for key, value in fields.items():
        if value is None:
            continue
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    await session.flush()
    return cfg


# =============================================================
#                        Athletes
# =============================================================

async def list_athletes(session: AsyncSession, coach_id: Optional[int] = None) -> Sequence[Athlete]:
    q = select(Athlete).options(selectinload(Athlete.user)).order_by(Athlete.id)
    if coach_id is not None:
        q = q.where(Athlete.coach_id == coach_id)
    return (await session.execute(q)).scalars().all()


async def get_athlete_by_user_id(session: AsyncSession, user_id: int) -> Optional[Athlete]:
    q = select(Athlete).where(Athlete.user_id == user_id)
    return (await session.execute(q)).scalar_one_or_none()


async def get_athlete_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[Athlete]:
    q = (
        select(Athlete)
        .join(User, User.id == Athlete.user_id)
        .where(User.telegram_id == telegram_id)
        .options(selectinload(Athlete.user))
    )
    return (await session.execute(q)).scalar_one_or_none()


async def update_athlete_profile(session: AsyncSession, athlete_id: int, **fields) -> None:
    """Обновить анкету спортсмена (из /profile или из диалога)."""
    await session.execute(
        update(Athlete).where(Athlete.id == athlete_id).values(**{k: v for k, v in fields.items() if v is not None})
    )


async def attach_athlete_to_default_coach(session: AsyncSession, athlete: Athlete) -> None:
    """Привязать спортсмена к единственному тренеру (MVP-флоу)."""
    if athlete.coach_id is not None:
        return
    coach = await get_default_coach(session)
    if coach is not None:
        athlete.coach_id = coach.id
        await session.flush()


# =============================================================
#                        Plans / Sessions / Logs
# =============================================================

async def add_plan(
    session: AsyncSession,
    athlete_id: int,
    *,
    content: str,
    title: str = "План тренировок",
    focus: str = "общая подготовка",
    weeks: int = 1,
) -> Plan:
    plan = Plan(
        athlete_id=athlete_id,
        title=title,
        focus=focus,
        content=content,
        weeks=weeks,
    )
    session.add(plan)
    await session.flush()
    return plan


async def list_plans(session: AsyncSession, athlete_id: int) -> Sequence[Plan]:
    q = select(Plan).where(Plan.athlete_id == athlete_id).order_by(Plan.created_at.desc())
    return (await session.execute(q)).scalars().all()


async def add_session_record(
    session: AsyncSession,
    athlete_id: int,
    *,
    fatigue: int,
    sleep_quality: int,
    results: str = "",
    pain: str = "",
) -> SessionRow:
    row = SessionRow(
        athlete_id=athlete_id,
        fatigue=fatigue,
        sleep_quality=sleep_quality,
        results=results,
        pain=pain,
    )
    session.add(row)
    await session.flush()
    return row


async def list_session_records(
    session: AsyncSession, athlete_id: int, limit: int = 30
) -> Sequence[SessionRow]:
    q = (
        select(SessionRow)
        .where(SessionRow.athlete_id == athlete_id)
        .order_by(SessionRow.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(q)).scalars().all()


async def add_training_log(
    session: AsyncSession,
    athlete_id: int,
    *,
    log_date: date,
    day_name: str,
    status: str,
    rpe: int = 0,
    notes: str = "",
    source: str = "manual",
    external_id: Optional[str] = None,
) -> TrainingLog:
    row = TrainingLog(
        athlete_id=athlete_id,
        log_date=log_date,
        day_name=day_name,
        status=status,
        rpe=rpe,
        notes=notes,
        source=source,
        external_id=external_id,
    )
    session.add(row)
    await session.flush()
    return row


async def list_training_logs(
    session: AsyncSession, athlete_id: int, days: int = 28
) -> Sequence[TrainingLog]:
    since = date.today() - timedelta(days=days)
    q = (
        select(TrainingLog)
        .where(TrainingLog.athlete_id == athlete_id, TrainingLog.log_date >= since)
        .order_by(TrainingLog.log_date.desc())
    )
    return (await session.execute(q)).scalars().all()


# =============================================================
#                        Polls
# =============================================================

async def create_poll(session: AsyncSession, athlete_id: int, kind: str = "daily") -> Poll:
    poll = Poll(athlete_id=athlete_id, kind=kind)
    session.add(poll)
    await session.flush()
    return poll


async def save_poll_answers(
    session: AsyncSession, poll_id: int, answers: dict[str, str]
) -> None:
    for question, answer in answers.items():
        session.add(PollAnswer(poll_id=poll_id, question=question, answer=answer))
    await session.execute(update(Poll).where(Poll.id == poll_id).values(completed=True))
    await session.flush()


# =============================================================
#                        Payments
# =============================================================

async def record_payment(
    session: AsyncSession,
    *,
    user_id: int,
    coach_id: Optional[int],
    amount: int,
    currency: str,
    title: str,
    telegram_charge_id: Optional[str],
    provider_charge_id: Optional[str],
) -> Payment:
    payment = Payment(
        user_id=user_id,
        coach_id=coach_id,
        amount=amount,
        currency=currency,
        title=title,
        telegram_charge_id=telegram_charge_id,
        provider_charge_id=provider_charge_id,
    )
    session.add(payment)
    await session.flush()
    return payment


async def activate_subscription(
    session: AsyncSession, user_id: int, days: int = 30
) -> None:
    """Активировать подписку спортсмена на N дней с текущего момента."""
    athlete = await get_athlete_by_user_id(session, user_id)
    if athlete is None:
        return
    until = datetime.utcnow() + timedelta(days=days)
    athlete.subscription_active = True
    athlete.subscription_until = until
    await session.flush()


async def list_payments_for_coach(
    session: AsyncSession, coach_id: int, limit: int = 50
) -> Sequence[Payment]:
    q = (
        select(Payment)
        .where(Payment.coach_id == coach_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(q)).scalars().all()


# =============================================================
#                        Strava tokens
# =============================================================

async def upsert_strava_token(
    session: AsyncSession,
    *,
    user_id: int,
    access_token: str,
    refresh_token: str,
    expires_at: int,
    athlete_id_strava: Optional[int] = None,
) -> StravaToken:
    q = select(StravaToken).where(StravaToken.user_id == user_id)
    token = (await session.execute(q)).scalar_one_or_none()
    if token is None:
        token = StravaToken(user_id=user_id)
        session.add(token)
    token.access_token = access_token
    token.refresh_token = refresh_token
    token.expires_at = expires_at
    if athlete_id_strava:
        token.athlete_id_strava = athlete_id_strava
    await session.flush()
    return token


async def get_strava_token(session: AsyncSession, user_id: int) -> Optional[StravaToken]:
    q = select(StravaToken).where(StravaToken.user_id == user_id)
    return (await session.execute(q)).scalar_one_or_none()


# =============================================================
#                        Dashboard stats
# =============================================================

async def coach_dashboard_stats(session: AsyncSession, coach_id: int) -> dict:
    """Агрегаты для дашборда тренера."""
    athletes_count = (
        await session.execute(select(func.count(Athlete.id)).where(Athlete.coach_id == coach_id))
    ).scalar_one()
    active_subs = (
        await session.execute(
            select(func.count(Athlete.id)).where(
                Athlete.coach_id == coach_id,
                Athlete.subscription_active.is_(True),
            )
        )
    ).scalar_one()
    revenue_sum = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.coach_id == coach_id)
        )
    ).scalar_one()
    return {
        "athletes": athletes_count,
        "active_subscriptions": active_subs,
        "revenue_minor_units": revenue_sum,
    }
