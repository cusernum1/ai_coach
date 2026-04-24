# AI Coach — Дипломный проект

**Автор:** Волошин Данила Александрович · 2026  
**Тип:** Дипломная работа  
**Рабочая папка:** `diplom_last_v/`

---

## Что это

AI-ассистент спортивного тренера. Telegram-бот + Web Mini-App дашборд.

**Роли:** тренер (`ADMIN_TELEGRAM_ID` при `/start`) / спортсмен (все остальные).  
**LLM:** Groq (`llama-3.3-70b-versatile`) или OpenRouter — переключается через `.env`.  
**БД:** PostgreSQL (prod) или SQLite (`SQLITE_FALLBACK=1`) для dev.

---

## Tech Stack

| Слой | Технология |
|------|-----------|
| Бот | Python 3.12, aiogram 3, FSM (MemoryStorage) |
| Web | FastAPI 0.110, Plotly + vanilla JS |
| БД | PostgreSQL 15, SQLAlchemy 2.x async + aiosqlite fallback |
| LLM | Groq / OpenRouter, function-calling (ReAct-цикл, 5 инструментов) |
| Планировщик | APScheduler (CronTrigger) |
| Интеграции | Strava OAuth2, Telegram Payments |
| Логи | loguru (ротация 1 MB, retention 7 дней) |

---

## Структура кода (`diplom_last_v/app/`)

```
main.py              # asyncio.run: бот + uvicorn + APScheduler в одном loop
config.py            # AppConfig dataclass, fail-fast валидация, .env через find_dotenv()
bot/
  handlers/
    common.py        # /start /help /profile
    athlete.py       # онбординг-анкета, /plan /nutrition /checkin
    coach.py         # /settings /athletes /stats /payments /broadcast /dashboard
    poll.py          # ежедневный опрос (FSM DailyPoll)
    training_log.py  # /log — журнал (факт vs план, RPE)
    payments.py      # /subscribe, PreCheckoutQuery, SuccessfulPayment
    strava.py        # /strava /sync_strava
    agent_chat.py    # fallback: любой текст → LLM-агент
  keyboards.py       # scale_kb(), reply/inline клавиатуры
  states.py          # FSM: Onboarding, DailyPoll, TrainingLog, CoachSettings, ...
  middlewares.py     # UserContextMiddleware → data["user"], data["role"], data["profile"]
  utils.py           # chunk_text (4096), money helpers
core/
  agent.py           # run_agent() — ReAct, asyncio.to_thread, max 5 итераций, history 6 реплик
  prompts.py         # get_training_plan_prompt/get_analysis_prompt/get_recovery_prompt/...
  metrics.py         # wellness_score, acwr, training_monotony (чистые формулы, без БД)
db/
  database.py        # engine + AsyncSession factory + init_db() (create_all, не Alembic)
  models.py          # User / Coach / CoachConfig / Athlete / Plan / Session /
                     # TrainingLog / Poll / PollAnswer / Payment / StravaToken
  repo.py            # CRUD-репозитории (async with get_session())
integrations/
  strava.py          # exchange_code(), save_tokens(), sync_to_training_logs()
  payments.py        # send_invoice()
scheduler/
  jobs.py            # daily_poll_job (HH:MM) / weekly_summary_job (пн 09:00) /
                     # strava_sync_job (каждые 6 ч)
webapp/
  server.py          # GET / /coach /coach/data /coach/athlete/{id} /strava/callback
  static/            # coach.html, app.js, style.css
```

---

## LLM-агент: как работает

`core/agent.py → run_agent()`

1. Строится system-prompt: профиль спортсмена + `base_program` тренера (если задана).
2. Подмешивается `chat_history` (последние 6 реплик, max 800 символов на реплику).
3. Вызов LLM с `tools=TOOLS` (function-calling).
4. Если LLM вернул `tool_calls` → `_execute_tool()` → второй вызов LLM за финальным ответом.
5. Защита от зацикливания: `used_tools` set (один инструмент не вызывается дважды), max 5 итераций.
6. Весь синхронный SDK (Groq / OpenAI) запускается через `asyncio.to_thread`.

**5 инструментов:**
| Инструмент | Когда вызывается |
|-----------|-----------------|
| `generate_training_plan` | план/программа/расписание |
| `analyze_progress` | конкретные результаты на анализ |
| `recovery_recommendation` | усталость, боли, сон |
| `nutrition_recommendation` | питание, КБЖУ, меню |
| `analyze_workload` | анализ журнала RPE |

---

## ORM-модели (ключевые связи)

```
User (telegram_id)
  ├── Coach ──► CoachConfig (brand_name, base_program, subscription_price, polls_enabled)
  │              └── athletes: List[Athlete]
  ├── Athlete ──► plans, sessions, logs, polls
  └── StravaToken (access_token, refresh_token, expires_at)

TrainingLog: log_date, status (выполнено/частично/пропущено), rpe 0..10, source (manual|strava)
Poll + PollAnswer: kind (daily/weekly), completed bool
Payment: amount (копейки), telegram_charge_id (unique)
```

---

## Метрики (core/metrics.py)

| Метрика | Формула | Где используется |
|---------|---------|-----------------|
| `wellness_score` | `(10-fatigue)*5 + sleep*5` → 0..100 | /checkin, дашборд |
| `acwr` | avg_7 / avg_28 по RPE | дашборд, analyze_workload |
| `acwr_zone` | <0.8 недотрен / 0.8-1.3 ок / 1.3-1.5 внимание / >1.5 риск | — |
| `training_monotony` | mean_RPE / std_RPE | анализ журнала |

---

## Запуск

```bash
# Зависимости
cd diplom_last_v
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# PostgreSQL через Docker
docker run --rm -d --name coach-pg \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ai_coach \
  -p 5432:5432 postgres:15

# Старт (бот + FastAPI :8080 + scheduler — всё в одном процессе)
python run.py
```

**Dev-режим (без Postgres):** `SQLITE_FALLBACK=1` в `.env`  
**Таблицы** создаются автоматически при первом запуске.

---

## Ключевые .env переменные

```ini
TELEGRAM_BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...         # первый тренер; узнать у @userinfobot
LLM_PROVIDER=groq             # groq | openrouter
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coach
SQLITE_FALLBACK=0             # 1 = dev-режим без Postgres
WEBAPP_PUBLIC_URL=https://... # нужен https для кнопки WebApp в TG
WEBAPP_PORT=8080
DAILY_POLL_TIME=08:00
SCHEDULER_TIMEZONE=Europe/Moscow
# опционально:
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
PAYMENTS_PROVIDER_TOKEN=...
```

---

## Тесты

```bash
cd diplom_last_v
pytest tests/ -q
# test_core_metrics.py — smoke-тесты wellness/acwr/monotony (нет БД, нет LLM)
```

---

## Известные ограничения (MVP / диплом)

> Это не баги — они задокументированы в README. Указать комиссии если спросят.

1. **WebApp-аутентификация по `?tid=<telegram_id>`** — не HMAC. В продакшне заменить на проверку `Telegram.WebApp.initData`.
2. **`init_db()` → `create_all`** — не Alembic. В продакшне использовать миграции.
3. **`daily_poll_job`** отправляет сообщение с клавиатурой, но не переводит FSM-состояние напрямую — опрос запускается при первом клике.
4. **MemoryStorage** (FSM) — состояния теряются при перезапуске бота. В продакшне → RedisStorage.
5. **Тесты** только на формулы метрик; нет интеграционных тестов хендлеров.

---

## Версии проекта

| Папка | Описание |
|-------|---------|
| `diplom_last_v/` | **Финальная версия** — бот + FastAPI + PostgreSQL |
| `diplomaV1/` | Промежуточная версия |
| Корень `ai_coach/` | Legacy Streamlit-файлы (для сравнения комиссии) |

---

## Что писать мне (в этот файл) для экономии токенов

Добавляй заметки в следующий раздел. Это то, что Claude **не может узнать** из кода:

---

## Заметки для Claude (заполняй сам)

> *Что сейчас делается / что сломалось / решения которые принял / что показал преподаватель*

- **Текущий статус:** ?
- **Открытые вопросы / баги:** ?
- **Что сказал научрук:** ?
- **Дедлайн сдачи:** ?

---

## Лог сессий

- **2026-04-23:** Создал Obsidian-хранилище (`Diploma/`), Claude заполнил обзорный файл по проекту — архитектура, стек, LLM-агент, ORM-схема, метрики, известные ограничения, инструкция запуска.
- **2026-04-23:** Починили запуск pytest — нужно использовать `.venv/bin/pytest` или активировать `source .venv/bin/activate`. Все 6 тестов проходят.
- **2026-04-23:** Настроено автоматическое обновление этого лога после каждого ответа Claude.
- **2026-04-24:** Оценка готовности к отправке преподавателю — проект готов (MVP, 2676 строк, тесты зелёные, README подробный). Нужно убрать coach.db из diplom_last_v/ перед отправкой.
