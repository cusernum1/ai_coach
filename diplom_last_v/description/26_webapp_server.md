# app/webapp/server.py — FastAPI дашборд и OAuth-callback

## За что отвечает файл

Веб-приложение на FastAPI — второй «фронт» проекта помимо Telegram-бота. Содержит:
- Дашборд тренера (HTML-страница + JSON API)
- OAuth-callback для Strava
- Статику (HTML/JS/CSS)

Запускается через `uvicorn` в одном event loop с ботом.

## Код с объяснениями

### Создание приложения

```python
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```
- `Path(__file__).resolve().parent` — папка где находится текущий файл (`webapp/`)
- `/ "static"` — путь `/webapp/static`
- `app.mount("/static", StaticFiles(...))` — все файлы из папки `static/` доступны по URL `/static/coach.html` и т.д.

---

### GET `/` — проверка работоспособности

```python
@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse(
        f"<h1>{config.APP_TITLE}</h1>"
        f"<p>OK · v{config.APP_VERSION}</p>"
        f"<p><a href='/coach'>Coach dashboard</a></p>"
    )
```
**Health check** — простой endpoint для проверки что сервер живой. Используется также для первого знакомства.

---

### GET `/coach` — дашборд (HTML)

```python
@app.get("/coach", response_class=HTMLResponse)
async def coach_index(tid: int | None = None) -> HTMLResponse:
    html = (STATIC_DIR / "coach.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
```
Отдаём HTML-файл. `tid` — telegram_id тренера в URL (`/coach?tid=123456`). HTML-страница сама делает AJAX-запрос на `/coach/data?tid=...`.

---

### GET `/coach/data` — JSON для дашборда

```python
@app.get("/coach/data", response_class=JSONResponse)
async def coach_data(tid: int) -> JSONResponse:
    async with get_session() as s:
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
    
    data = {
        "brand_name": coach.config.brand_name if coach.config else "AI Coach",
        "stats": {
            "athletes": stats["athletes"],
            "active_subscriptions": stats["active_subscriptions"],
            "revenue_rub": round(stats["revenue_minor_units"] / 100, 2),
        },
        "athletes": [
            {
                "id": a.id, "name": a.name, "sport": a.sport,
                "level": a.level, "goal": a.goal,
                "subscription_active": a.subscription_active,
            }
            for a in athletes
        ],
    }
    return JSONResponse(data)
```
- `tid: int` в параметрах функции — FastAPI автоматически берёт из URL-параметров (`?tid=123`)
- `raise HTTPException(status_code=404, ...)` — возвращает HTTP 404 с JSON-ошибкой
- List comprehension для сериализации списка спортсменов

---

### GET `/coach/athlete/{athlete_id}` — детали спортсмена

```python
@app.get("/coach/athlete/{athlete_id}", response_class=JSONResponse)
async def athlete_detail(athlete_id: int) -> JSONResponse:
    async with get_session() as s:
        q = select(Athlete).where(Athlete.id == athlete_id).options(selectinload(Athlete.user))
        athlete = (await s.execute(q)).scalar_one_or_none()
        if athlete is None:
            raise HTTPException(status_code=404, detail="Athlete not found")
        
        plans = await list_plans(s, athlete.id)
        logs = await list_training_logs(s, athlete.id, days=60)
        sessions = await list_session_records(s, athlete.id, limit=30)
    
    return JSONResponse({
        "profile": {...},
        "plans": [{"id": p.id, "title": p.title, "weeks": p.weeks, "created_at": p.created_at.isoformat()} for p in plans],
        "logs": [{"date": log.log_date.isoformat(), "name": log.day_name, "status": log.status, "rpe": log.rpe} for log in logs],
        "sessions": [{"at": sr.created_at.isoformat(), "fatigue": sr.fatigue, "sleep": sr.sleep_quality} for sr in sessions],
    })
```
`{athlete_id}` в пути — FastAPI автоматически извлекает как параметр функции. `.isoformat()` — преобразует дату/datetime в строку `"2024-01-15"` для JSON.

---

### GET `/strava/callback` — OAuth-callback

```python
@app.get("/strava/callback")
async def strava_callback(request: Request) -> HTMLResponse:
    params = request.query_params
    error = params.get("error")
    if error:
        return HTMLResponse(f"<h1>Strava отказала в доступе</h1><p>{error}</p>")
    
    code = params.get("code")
    state = params.get("state")
    if not code or not state or not state.isdigit():
        raise HTTPException(status_code=400, detail="Missing code/state")
    
    telegram_id = int(state)
    
    try:
        payload = await exchange_code(code)
    except Exception as e:
        return HTMLResponse(f"<h1>Ошибка обмена кода Strava</h1><pre>{e}</pre>")
    
    async with get_session() as s:
        q = select(User).where(User.telegram_id == telegram_id)
        user = (await s.execute(q)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
    
    await save_tokens(user.id, payload)
    
    return HTMLResponse(
        "<h1>✅ Strava подключена</h1>"
        "<p>Можно закрыть это окно и вернуться в Telegram.</p>"
    )
```
- `request.query_params` — все URL-параметры (`?code=XXX&state=YYY`)
- `state` — это telegram_id который мы закодировали при создании URL
- Меняем `code` на токены через `exchange_code()`, сохраняем в БД

## Ключевые термины

- **FastAPI** — Python-фреймворк для REST API, автоматически генерирует документацию
- **`response_class=HTMLResponse`** — тип ответа (HTML вместо JSON)
- **`HTTPException(status_code=404)`** — возвращает HTTP-ошибку
- **`StaticFiles`** — раздача статических файлов (HTML, JS, CSS)
- **`request.query_params`** — URL-параметры запроса
- **OAuth2 callback** — endpoint на который внешний сервис (Strava) перенаправляет после авторизации
