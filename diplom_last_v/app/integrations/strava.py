# ============================================================
# app/integrations/strava.py — OAuth2 + синхронизация активностей
# ============================================================
# Flow:
#   1. /strava в боте -> генерируем authorize_url с state=telegram_id
#   2. Пользователь авторизуется в Strava
#   3. Strava редиректит на STRAVA_REDIRECT_URI (обработчик — FastAPI)
#   4. Мы меняем code на access/refresh токены, сохраняем в БД
#   5. По расписанию/команде — подтягиваем новые activities
# ============================================================

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.config import config
from app.db import get_session
from app.db.repo import (
    add_training_log,
    get_athlete_by_telegram_id,
    get_strava_token,
    upsert_strava_token,
)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


# ── URL для кнопки «Подключить Strava» ───────────────────────
def build_authorize_url(telegram_id: int) -> str:
    """
    Формирует URL авторизации Strava.
    state=telegram_id — чтобы в callback'е мы знали, чей токен сохранять.
    """
    params = {
        "client_id": config.STRAVA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.STRAVA_REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": "read,activity:read",
        "state": str(telegram_id),
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


# ── Обмен code -> tokens ─────────────────────────────────────
async def exchange_code(code: str) -> dict[str, Any]:
    """Меняем короткий code на access/refresh токены."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": config.STRAVA_CLIENT_ID,
                "client_secret": config.STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


# ── Обновление токенов ───────────────────────────────────────
async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": config.STRAVA_CLIENT_ID,
                "client_secret": config.STRAVA_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def save_tokens(user_id: int, payload: dict[str, Any]) -> None:
    """Сохранить ответ /oauth/token в БД."""
    async with get_session() as s:
        await upsert_strava_token(
            s,
            user_id=user_id,
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=int(payload["expires_at"]),
            athlete_id_strava=(payload.get("athlete") or {}).get("id"),
        )


# ── Получить валидный access-token (с refresh) ───────────────
async def get_valid_access_token(user_id: int) -> Optional[str]:
    async with get_session() as s:
        token = await get_strava_token(s, user_id)
    if token is None:
        return None
    # Запас 60 сек — обновляем чуть раньше истечения
    if token.expires_at > int(time.time()) + 60:
        return token.access_token
    # refresh
    logger.info(f"Strava refresh for user {user_id}")
    payload = await refresh_tokens(token.refresh_token)
    await save_tokens(user_id, payload)
    return payload["access_token"]


# ── Получение активностей ───────────────────────────────────
async def fetch_activities(user_id: int, per_page: int = 10) -> list[dict[str, Any]]:
    access = await get_valid_access_token(user_id)
    if not access:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access}"},
            params={"per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json()


# ── Синхронизация активностей -> TrainingLog ─────────────────
async def sync_to_training_logs(telegram_id: int) -> int:
    """Подтянуть последние активности и записать их в журнал."""
    async with get_session() as s:
        athlete = await get_athlete_by_telegram_id(s, telegram_id)
    if athlete is None:
        return 0
    activities = await fetch_activities(athlete.user.id, per_page=10)
    added = 0
    async with get_session() as s:
        # чтобы не дублировать — можно было бы сверять external_id,
        # но для учебного проекта — пишем всё, что пришло.
        for act in activities:
            ext_id = str(act.get("id"))
            date_str = act.get("start_date_local", "")[:10]
            try:
                log_date = datetime.fromisoformat(date_str).date()
            except Exception:
                log_date = datetime.now(timezone.utc).date()
            name = act.get("name") or act.get("type") or "Активность"
            await add_training_log(
                s,
                athlete.id,
                log_date=log_date,
                day_name=str(name)[:250],
                status="выполнено",
                rpe=int(act.get("perceived_exertion") or 5),
                notes=f"Strava · {act.get('type', '')} · {round((act.get('distance') or 0) / 1000, 1)} км",
                source="strava",
                external_id=ext_id,
            )
            added += 1
    logger.info(f"Strava sync: {added} activities for tg={telegram_id}")
    return added
