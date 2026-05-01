# app/integrations/strava.py — OAuth2 + синхронизация Strava

## За что отвечает файл

Вся бизнес-логика интеграции со Strava:
1. Построение URL авторизации
2. Обмен `code` на токены (после авторизации)
3. Обновление просроченных токенов (refresh)
4. Получение активностей из Strava API
5. Сохранение активностей как `TrainingLog` в нашу БД

## Код с объяснениями

### Константы

```python
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
```
Публичные URL Strava API.

---

### `build_authorize_url()` — ссылка авторизации

```python
def build_authorize_url(telegram_id: int) -> str:
    params = {
        "client_id": config.STRAVA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.STRAVA_REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": "read,activity:read",
        "state": str(telegram_id),   # ← ключевое: сохраняем чей это telegram_id
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"
```
`urlencode(params)` — преобразует словарь в строку URL-параметров: `?client_id=123&state=456...`

`state=telegram_id` — Strava вернёт этот параметр в callback. Так мы узнаем, чьи токены сохранять.

---

### `exchange_code()` — обмен кода на токены

```python
async def exchange_code(code: str) -> dict[str, Any]:
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
```
`httpx.AsyncClient` — асинхронный HTTP-клиент (не блокирует event loop).

`grant_type="authorization_code"` — стандартный OAuth2-флоу. Отправляем `code`, получаем `access_token + refresh_token`.

`resp.raise_for_status()` — если HTTP-статус >= 400, бросает исключение.

---

### `refresh_tokens()` — обновление токенов

```python
async def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={...
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
```
`access_token` живёт 6 часов. Когда истекает — используем `refresh_token` для получения нового.

---

### `get_valid_access_token()` — автообновление

```python
async def get_valid_access_token(user_id: int) -> Optional[str]:
    async with get_session() as s:
        token = await get_strava_token(s, user_id)
    if token is None:
        return None
    
    # Запас 60 сек — обновляем чуть раньше истечения
    if token.expires_at > int(time.time()) + 60:
        return token.access_token
    
    # refresh
    payload = await refresh_tokens(token.refresh_token)
    await save_tokens(user_id, payload)
    return payload["access_token"]
```
`int(time.time())` — текущий Unix timestamp (секунды с 1970). Сравниваем с `expires_at`. Запас 60 секунд — чтобы не отправлять запрос с токеном который истечёт прямо в процессе.

---

### `fetch_activities()` — получение активностей

```python
async def fetch_activities(user_id: int, per_page: int = 10) -> list[dict]:
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
```
Bearer-токен в заголовке — стандарт OAuth2. `per_page=10` — берём последние 10 активностей.

---

### `sync_to_training_logs()` — синхронизация

```python
async def sync_to_training_logs(telegram_id: int) -> int:
    async with get_session() as s:
        athlete = await get_athlete_by_telegram_id(s, telegram_id)
    if athlete is None:
        return 0
    
    activities = await fetch_activities(athlete.user.id, per_page=10)
    added = 0
    
    async with get_session() as s:
        for act in activities:
            ext_id = str(act.get("id"))
            date_str = act.get("start_date_local", "")[:10]
            try:
                log_date = datetime.fromisoformat(date_str).date()
            except Exception:
                log_date = datetime.now(timezone.utc).date()
            
            name = act.get("name") or act.get("type") or "Активность"
            await add_training_log(
                s, athlete.id,
                log_date=log_date,
                day_name=str(name)[:250],
                status="выполнено",
                rpe=int(act.get("perceived_exertion") or 5),
                notes=f"Strava · {act.get('type', '')} · {round((act.get('distance') or 0) / 1000, 1)} км",
                source="strava",
                external_id=ext_id,
            )
            added += 1
    return added
```
- `start_date_local` из Strava — дата и время в формате ISO: `"2024-01-15T10:30:00Z"`. `[:10]` берёт только дату `"2024-01-15"`.
- `act.get("distance") / 1000` — Strava возвращает дистанцию в метрах, конвертируем в км.
- `act.get("perceived_exertion") or 5` — если нет RPE (не указал в Strava) → ставим 5 по умолчанию.
- `source="strava"` — маркер источника, чтобы не путать с ручными записями.

## Схема OAuth2-флоу

```
1. build_authorize_url(telegram_id)
   → https://strava.com/oauth/authorize?client_id=X&state=telegram_id&...

2. Пользователь авторизуется в Strava

3. Strava: GET /strava/callback?code=ABC&state=telegram_id
   (обрабатывает FastAPI, webapp/server.py)

4. exchange_code("ABC")
   → POST strava.com/oauth/token → {access_token, refresh_token, expires_at}

5. save_tokens(user.id, payload)
   → сохраняем в strava_tokens

6. Через 6 часов: get_valid_access_token()
   → expires_at истёк → refresh_tokens() → новый access_token
```
