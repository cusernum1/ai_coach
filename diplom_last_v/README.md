# 🏋️ AI Coach — Telegram-бот + Web Mini-App (v3)

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3-green.svg)](https://docs.aiogram.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-teal.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

AI-ассистент спортивного тренера:
**Telegram-бот** + **Web Mini-App-дашборд** + **PostgreSQL** + **расписание** +
**Strava** + **оплата в чате**.

**Дипломная работа** · Python · aiogram 3 · FastAPI · SQLAlchemy async · APScheduler · OpenRouter/Groq.

---

## 🎯 Что делает

| Возможность | Где |
|------------|------|
| Ролевая модель (тренер / спортсмен) | бот, БД |
| Тренер настраивает всё через чат (бренд, лого, программа, цена) | `/settings` |
| БД со знаниями о спортсменах (планы, сессии, журнал) | PostgreSQL |
| Базовая программа тренера попадает в system-prompt агента | `core/agent.py` |
| Автоматические опросы по расписанию (wellness) | `scheduler/jobs.py` |
| Интеграция со Strava (OAuth + sync активностей) | `integrations/strava.py` |
| Дашборд тренера (графики RPE, список спортсменов) | FastAPI + JS |
| Оплата через чат — Telegram Payments (ЮKassa / Stripe Test) | `integrations/payments.py` |

---

## 🏗 Архитектура

```
┌─────────────────── Telegram user (coach/athlete) ──────────────────┐
│                                                                    │
│   Telegram bot (aiogram 3)        Web Mini-App (Plotly + JS)       │
│            │                              │                        │
│            ▼                              ▼                        │
│  ┌────────────────────┐        ┌───────────────────────┐            │
│  │ handlers (role-    │        │ FastAPI (/coach/data) │            │
│  │ aware: coach/      │◄──────►│  + Strava callback    │            │
│  │ athlete/payments/  │        └──────────┬────────────┘            │
│  │ strava/agent_chat) │                   │                         │
│  └─────────┬──────────┘                   │                         │
│            │                              │                         │
│  ┌─────────▼──────────┐        ┌──────────▼──────────┐             │
│  │ core (LLM agent,   │        │ integrations        │             │
│  │ prompts, metrics)  │        │ (Strava, Payments)  │             │
│  └─────────┬──────────┘        └──────────┬──────────┘             │
│            │                              │                         │
│            ▼                              ▼                         │
│  ┌─────────────────────────────────────────────────────┐           │
│  │    db (SQLAlchemy 2.x async)  →  PostgreSQL         │           │
│  └─────────────────────────────────────────────────────┘           │
│                   ▲                                                 │
│                   │                                                 │
│            APScheduler (daily poll / weekly summary / strava sync) │
└────────────────────────────────────────────────────────────────────┘
```

### Структура кода

```
ai_coach/
├── app/
│   ├── __init__.py
│   ├── main.py                 # ★ единая точка входа: бот + web + scheduler
│   ├── config.py               # конфиг из .env (fail-fast)
│   │
│   ├── bot/                    # Telegram-бот (aiogram 3)
│   │   ├── main.py             #   build Bot + Dispatcher
│   │   ├── keyboards.py        #   reply / inline клавиатуры
│   │   ├── states.py           #   FSM (онбординг, опрос, журнал, настройки)
│   │   ├── middlewares.py      #   UserContextMiddleware (роль, профиль)
│   │   ├── utils.py            #   chunk_text, money helpers
│   │   └── handlers/
│   │       ├── common.py       #   /start /help /profile
│   │       ├── athlete.py      #   онбординг анкеты, /plan /nutrition /checkin
│   │       ├── coach.py        #   /settings /athletes /stats /payments /broadcast
│   │       ├── poll.py         #   ежедневный опрос (FSM)
│   │       ├── training_log.py #   /log (журнал тренировок)
│   │       ├── payments.py     #   /subscribe, PreCheckout, SuccessfulPayment
│   │       ├── strava.py       #   /strava /sync_strava
│   │       └── agent_chat.py   #   свободный диалог с LLM (последний в цепочке)
│   │
│   ├── core/                   # Домен (без зависимости от транспорта)
│   │   ├── agent.py            #   ReAct-агент (async-обёртка)
│   │   ├── prompts.py          #   промпт-шаблоны + base_program тренера
│   │   └── metrics.py          #   Wellness / ACWR / Monotony
│   │
│   ├── db/                     # Слой данных
│   │   ├── database.py         #   engine + AsyncSession factory
│   │   ├── models.py           #   ORM (User/Coach/Athlete/Plan/.../Payment/StravaToken)
│   │   └── repo.py             #   репозитории (CRUD)
│   │
│   ├── integrations/
│   │   ├── strava.py           #   OAuth2 + /oauth/token + fetch activities
│   │   └── payments.py         #   Telegram Payments: send_invoice
│   │
│   ├── scheduler/
│   │   └── jobs.py             #   daily_poll / weekly_summary / strava_sync
│   │
│   └── webapp/                 # FastAPI-приложение
│       ├── server.py           #   /, /coach, /coach/data, /strava/callback
│       └── static/             #   coach.html + app.js + style.css
│
├── tests/
│   └── test_core_metrics.py    # smoke-тесты формул
│
├── run.py                      # `python run.py` = python -m app.main
├── requirements.txt            # новые зависимости (aiogram, asyncpg, fastapi, ...)
│
├── agent.py, app.py, database.py, metrics.py, models.py, pdf_export.py,
│   services.py, tools.py       # ← legacy (Streamlit-версия) — оставлено для справки
│
├── fonts/
├── logs/
├── .env                        # секреты (не в git)
├── .env.example                # шаблон переменных
└── README.md                   # этот файл
```

---

## ⚙️ Переменные окружения (.env)

Нужно задать минимум:

```ini
# LLM (один из двух)
LLM_PROVIDER=groq                # или openrouter
GROQ_API_KEY=gsk_...

# Telegram
TELEGRAM_BOT_TOKEN=123:AA...
ADMIN_TELEGRAM_ID=123456789      # первый тренер (роль COACH назначится автоматически)

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coach
# SQLITE_FALLBACK=1              # включить, если нет Postgres (dev-режим, SQLite+aiosqlite)

# Strava (опционально)
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REDIRECT_URI=http://localhost:8080/strava/callback

# Telegram Payments (опционально)
PAYMENTS_PROVIDER_TOKEN=...      # получить у @BotFather → Payments
PAYMENTS_CURRENCY=RUB

# Web Mini-App
WEBAPP_PUBLIC_URL=https://<ngrok-или-домен>   # нужен https для кнопки WebApp в TG
WEBAPP_PORT=8080

# Расписание
SCHEDULER_TIMEZONE=Europe/Moscow
DAILY_POLL_TIME=08:00
```

Файл `.env.example` в репозитории описывает все переменные.

---

## 🚀 Запуск

### 1. Инсталляция зависимостей

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Подготовка БД

**С PostgreSQL** (рекомендуется):

```bash
# быстрый старт через Docker
docker run --rm -d --name coach-pg \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ai_coach \
  -p 5432:5432 postgres:15
```

**Или** без Postgres, в режиме SQLite (dev):

```ini
# .env
SQLITE_FALLBACK=1
```

Таблицы создаются автоматически при старте (`init_db()`).

### 3. Запуск

```bash
python run.py
```

Запустятся одновременно:
- long polling Telegram-бота;
- FastAPI на `:8080` (с эндпоинтом дашборда и OAuth-callback Strava);
- APScheduler (ежедневные опросы + еженедельная сводка + sync Strava).

---

## 👨‍🏫 Сценарии

### Тренер
1. `/start` (с ID = `ADMIN_TELEGRAM_ID`) — автоматически получает роль COACH.
2. `/settings` — меняет бренд, лого, приветствие, базовую программу, цену подписки.
3. `/base` — обновляет методику («Понедельник: верх… Среда: кардио…»). Этот текст будет попадать в system-prompt агента при генерации планов.
4. `/athletes` — список спортсменов, `/stats` — агрегаты, `/payments` — история оплат.
5. `/broadcast сообщение` — массовая рассылка.
6. `/dashboard` — ссылка на WebApp-дашборд с графиками RPE.

### Спортсмен
1. `/start` → выбрать роль «спортсмен» → анкета (возраст, спорт, уровень, цель, частота).
2. Кнопка «📋 План» или `/plan 2` → агент составляет план с учётом базовой программы тренера.
3. «💪 Самочувствие» или `/checkin` → inline-опрос (усталость/сон + заметка).
4. «📓 Журнал» или `/log` → запись тренировки (факт vs план, RPE).
5. «🔗 Strava» или `/strava` → OAuth, затем `/sync_strava` подтягивает активности в журнал.
6. «💳 Подписка» или `/subscribe` → Telegram Payments (ЮKassa/Stripe Test).
7. Любой текст = вопрос к ИИ-тренеру (с памятью последних 6 реплик).

---

## 🧪 Тесты

```bash
pytest tests/ -q
```

`tests/test_core_metrics.py` — smoke-тесты формул (wellness, ACWR, monotony), не требует БД и LLM.

Legacy-тесты в `tests/` (test_agent, test_database, test_integration, test_models) написаны под старую Streamlit-версию и остались как референс.

---

## 🛡 Безопасность и ограничения

- `.env` и `.env.example` не редактируются (только читаются). Секреты не пушим в git.
- При первом старте роль COACH получает только пользователь с Telegram ID из `ADMIN_TELEGRAM_ID`.
- В учебном MVP тренер идентифицируется по `tid=<telegram_id>` в query-параметре — для продакшна добавьте проверку `Telegram.WebApp.initData` (HMAC-подпись).
- `init_db()` использует `Base.metadata.create_all` — в продакшне замените на Alembic-миграции.

---

## 🧬 Что перенесено из старой версии

| Модуль legacy | Новое место | Изменения |
|--------------|------------|-----------|
| `agent.py`   | `app/core/agent.py` | async-обёртка через `asyncio.to_thread`, поддержка `base_program` тренера |
| `tools.py`   | `app/core/prompts.py` | + параметр `base_program` |
| `metrics.py` | `app/core/metrics.py` | убраны импорты из БД, остались чистые формулы |
| `models.py`  | `app/db/models.py` | Pydantic → SQLAlchemy (ORM); добавлены Coach, CoachConfig, Payment, StravaToken, Poll |
| `database.py`| `app/db/database.py` + `repo.py` | SQLite → PostgreSQL (async, SQLAlchemy 2.x) |
| `app.py`     | `app/bot/*` + `app/webapp/*` | Streamlit → Telegram bot + FastAPI Web Mini-App |

Старые файлы (`agent.py`, `app.py`, `database.py`, `metrics.py`, `models.py`, `services.py`, `tools.py`, `pdf_export.py`, `download_fonts.py`) оставлены в корне — проверяющий комиссии может сравнить подходы.

---

## 📜 Лицензия

MIT.

## 👤 Автор

Волошин Данила Александрович · 2026
