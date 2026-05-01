# description/ — Объяснение кода для защиты диплома

Каждый файл объясняет один модуль проекта **по строчкам**, простым языком.

## Навигация

| Файл | Что объясняет |
|------|--------------|
| `00_init_файлы.md` | Все `__init__.py` сгруппированы вместе |
| `01_run.md` | `run.py` — точка входа для запуска |
| `02_main.md` | `app/main.py` — запуск бота+веб+планировщика |
| `03_config.md` | `app/config.py` — конфигурация из .env |
| `04_bot_main.md` | `app/bot/main.py` — сборка бота и диспетчера |
| `05_states.md` | `app/bot/states.py` — FSM состояния диалогов |
| `06_middlewares.md` | `app/bot/middlewares.py` — пользователь из БД |
| `07_keyboards.md` | `app/bot/keyboards.py` — кнопки бота |
| `08_utils.md` | `app/bot/utils.py` — chunk_text, money |
| `09_handlers_common.md` | `/start`, `/help`, `/profile` |
| `10_handlers_athlete.md` | Онбординг и меню спортсмена |
| `11_handlers_coach.md` | Команды тренера |
| `12_handlers_poll.md` | Ежедневный опрос самочувствия |
| `13_handlers_training_log.md` | Журнал тренировок |
| `14_handlers_payments.md` | Telegram Payments |
| `15_handlers_strava.md` | Подключение Strava в боте |
| `16_handlers_agent_chat.md` | Свободный диалог с ИИ |
| `17_core_agent.md` | LLM-агент, ReAct, 5 инструментов |
| `18_core_metrics.md` | Wellness, ACWR, монотонность |
| `19_core_prompts.md` | Промпт-шаблоны для LLM |
| `20_db_database.md` | Подключение к БД, сессии |
| `21_db_models.md` | ORM-модели (таблицы) |
| `22_db_repo.md` | CRUD-репозитории |
| `23_integrations_strava.md` | OAuth2 + синхронизация |
| `24_integrations_payments.md` | Отправка инвойса |
| `25_scheduler_jobs.md` | Задачи по расписанию |
| `26_webapp_server.md` | FastAPI дашборд |
| `27_tests.md` | Автотесты метрик |

## Частые вопросы на защите

**Как работает LLM-агент?**
→ Смотри `17_core_agent.md` — ReAct-цикл, 5 инструментов, asyncio.to_thread

**Как устроена БД?**
→ Смотри `21_db_models.md` — схема таблиц и связей

**Что такое FSM?**
→ Смотри `05_states.md` — состояния диалогов

**Как работает оплата?**
→ Смотри `14_handlers_payments.md` — цикл Telegram Payments

**Как считаются метрики?**
→ Смотри `18_core_metrics.md` — ACWR, wellness_score, монотонность

**Зачем `asyncio`?**
→ Смотри `02_main.md` — запуск трёх компонентов в одном event loop
