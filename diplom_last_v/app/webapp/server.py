# ============================================================
# app/webapp/server.py — FastAPI-дашборд и OAuth-callback'и
# ============================================================
# Маршруты:
#   • GET  /             — заглавная (проверка доступности)
#   • GET  /coach        — HTML мини-приложения (дашборд тренера)
#   • GET  /coach/data   — JSON агрегатов (статистика + список спортсменов)
#   • GET  /coach/athlete/{id} — JSON деталей по спортсмену
#   • GET  /strava/callback     — обмен code на токены Strava
#   • GET  /static/*    — статика (HTML/JS/CSS TG WebApp)
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import config
from app.db import get_session
from app.db.models import Athlete, Coach, User
from app.db.repo import (
    coach_dashboard_stats,
    list_athletes,
    list_plans,
    list_session_records,
    list_training_logs,
)
from app.integrations.strava import exchange_code, save_tokens

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ══════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse(
        f"<h1>{config.APP_TITLE}</h1>"
        f"<p>OK · v{config.APP_VERSION}</p>"
        f"<p><a href='/coach'>Coach dashboard</a></p>"
    )


# ══════════════════════════════════════════════════════════════
# Coach dashboard (HTML)
# ══════════════════════════════════════════════════════════════
@app.get("/coach", response_class=HTMLResponse)
async def coach_index(tid: int | None = None) -> HTMLResponse:
    """
    Отдаём HTML-оболочку мини-приложения. Сам React/vanilla-JS
    внутри static/coach.html получает данные через /coach/data.
    Параметр ?tid=<telegram_id> нужен для идентификации тренера
    без auth-сервера (учебный MVP).
    """
    html = (STATIC_DIR / "coach.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/coach/data", response_class=JSONResponse)
async def coach_data(tid: int) -> JSONResponse:
    """JSON с данными для дашборда — вызывается из фронта."""
    async with get_session() as s:
        # Найдём тренера по telegram_id
        q = (
            select(Coach)
            .join(User, User.id == Coach.user_id)
            .where(User.telegram_id == tid)
            .options(selectinload(Coach.config))
        )
        coach = (await s.execute(q)).scalar_one_or_none()
        if coach is None:
            raise HTTPException(status_code=404, detail="Coach not found for this telegram id")

        stats = await coach_dashboard_stats(s, coach.id)
        athletes = await list_athletes(s, coach_id=coach.id)

    data: dict[str, Any] = {
        "brand_name": coach.config.brand_name if coach.config else "AI Coach",
        "stats": {
            "athletes": stats["athletes"],
            "active_subscriptions": stats["active_subscriptions"],
            "revenue_rub": round(stats["revenue_minor_units"] / 100, 2),
        },
        "athletes": [
            {
                "id": a.id,
                "name": a.name,
                "sport": a.sport,
                "level": a.level,
                "goal": a.goal,
                "sessions_per_week": a.sessions_per_week,
                "subscription_active": a.subscription_active,
            }
            for a in athletes
        ],
    }
    return JSONResponse(data)


@app.get("/coach/athlete/{athlete_id}", response_class=JSONResponse)
async def athlete_detail(athlete_id: int) -> JSONResponse:
    """Детали конкретного спортсмена: журнал + сессии + планы."""
    async with get_session() as s:
        q = select(Athlete).where(Athlete.id == athlete_id).options(selectinload(Athlete.user))
        athlete = (await s.execute(q)).scalar_one_or_none()
        if athlete is None:
            raise HTTPException(status_code=404, detail="Athlete not found")
        plans = await list_plans(s, athlete.id)
        logs = await list_training_logs(s, athlete.id, days=60)
        sessions = await list_session_records(s, athlete.id, limit=30)

    return JSONResponse(
        {
            "profile": {
                "id": athlete.id,
                "name": athlete.name,
                "sport": athlete.sport,
                "level": athlete.level,
                "goal": athlete.goal,
            },
            "plans": [
                {"id": p.id, "title": p.title, "weeks": p.weeks, "created_at": p.created_at.isoformat()}
                for p in plans
            ],
            "logs": [
                {
                    "date": log.log_date.isoformat(),
                    "name": log.day_name,
                    "status": log.status,
                    "rpe": log.rpe,
                    "source": log.source,
                }
                for log in logs
            ],
            "sessions": [
                {
                    "at": sr.created_at.isoformat(),
                    "fatigue": sr.fatigue,
                    "sleep": sr.sleep_quality,
                    "notes": sr.pain,
                }
                for sr in sessions
            ],
        }
    )


# ══════════════════════════════════════════════════════════════
# Strava OAuth callback
# ══════════════════════════════════════════════════════════════
@app.get("/strava/callback")
async def strava_callback(request: Request) -> HTMLResponse:
    """
    Strava редиректит сюда с параметрами code & state.
    state мы задавали как telegram_id пользователя — по нему
    находим User в БД и сохраняем токены.
    """
    params = request.query_params
    error = params.get("error")
    if error:
        return HTMLResponse(f"<h1>Strava отказала в доступе</h1><p>{error}</p>")

    code = params.get("code")
    state = params.get("state")
    if not code or not state or not state.isdigit():
        raise HTTPException(status_code=400, detail="Missing code/state")

    telegram_id = int(state)
    logger.info(f"Strava callback for tg={telegram_id}")

    try:
        payload = await exchange_code(code)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<h1>Ошибка обмена кода Strava</h1><pre>{e}</pre>")

    # Найдём пользователя
    async with get_session() as s:
        q = select(User).where(User.telegram_id == telegram_id)
        user = (await s.execute(q)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found; run /start in bot")
        # save_tokens открывает собственную сессию — просто вызовем её
    await save_tokens(user.id, payload)

    return HTMLResponse(
        "<h1>✅ Strava подключена</h1>"
        "<p>Можно закрыть это окно и вернуться в Telegram.</p>"
        "<p>В боте используй /sync_strava, чтобы подтянуть активности.</p>"
    )
