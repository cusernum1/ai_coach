# app/config.py — Конфигурация приложения

## Назначение файла
Единое место хранения всех настроек: токен Telegram, ключи LLM, URL базы данных, параметры Strava, платежей и логов. Читает значения из файла `.env`. Проверяет корректность при старте (fail-fast).

---

## Построчный разбор

```python
from __future__ import annotations
```
Разрешает современные аннотации типов.

---

```python
import os
```
Стандартная библиотека. Нужна для `os.getenv()` — читает переменные окружения.

---

```python
from dataclasses import dataclass, field
```
- `dataclass` — декоратор, превращающий обычный класс в «контейнер данных». Автоматически генерирует `__init__`, `__repr__` и другие методы.
- `field` — позволяет задать сложные значения по умолчанию через `default_factory=`.

---

```python
from pathlib import Path
```
Объектно-ориентированная работа с путями файловой системы. `Path(__file__)` — путь к текущему файлу.

---

```python
from dotenv import load_dotenv, find_dotenv
```
- `load_dotenv` — читает файл `.env` и помещает переменные в `os.environ`
- `find_dotenv` — ищет `.env` поднимаясь по дереву каталогов вверх

---

```python
_dotenv_path = find_dotenv(usecwd=True)
```
Ищем `.env` начиная с текущей рабочей директории (`usecwd=True`), поднимаясь выше. Переменная с `_` в начале — соглашение: «приватная», используется только внутри этого модуля.

---

```python
if not _dotenv_path:
```
Если `find_dotenv` ничего не нашёл — `_dotenv_path` будет пустой строкой, что равно `False`.

---

```python
    _candidate = Path(__file__).resolve().parents[2] / ".env"
```
- `Path(__file__)` — путь к файлу `config.py`
- `.resolve()` — преобразует в абсолютный путь
- `.parents[2]` — дедушка-директория (config.py находится в `diplom_last_v/app/`, `.parents[2]` = корень репозитория)
- `/ ".env"` — добавляет к пути имя файла

---

```python
    if _candidate.exists():
        _dotenv_path = str(_candidate)
```
Если файл существует — используем его путь.

---

```python
load_dotenv(_dotenv_path or None)
```
Загружаем `.env`. Если путь пустой (`""`), `or None` превращает его в `None`, и `load_dotenv` сам ищет файл.

---

```python
def _env(name: str, default: str = "") -> str:
```
Вспомогательная функция для чтения строковой переменной окружения.
- `name` — имя переменной (напр. `"TELEGRAM_BOT_TOKEN"`)
- `default=""` — значение если переменная не задана

---

```python
    return (os.getenv(name) or default).strip()
```
- `os.getenv(name)` — читает переменную. Возвращает `None` если не задана.
- `or default` — если `None` или пустая строка — берём `default`
- `.strip()` — убираем пробелы по краям (частая ошибка при редактировании `.env`)

---

```python
def _env_int(name: str, default: int) -> int:
```
Для целочисленных переменных (порты, ID пользователей).

---

```python
    raw = _env(name)
    return int(raw) if raw else default
```
- Сначала читаем как строку
- `if raw` — если строка непустая — конвертируем в `int`
- Иначе — возвращаем `default`

---

```python
def _env_bool(name: str, default: bool = False) -> bool:
```
Для булевых переменных — `SQLITE_FALLBACK=1`, `POLLS_ENABLED=true`.

---

```python
    raw = _env(name).lower()
```
Приводим к нижнему регистру чтобы `"TRUE"`, `"True"`, `"true"` — все работали.

---

```python
    return raw in ("1", "true", "yes", "on", "y")
```
Считаем «истинными» пять строк. Любое другое значение (`"0"`, `"false"`, `"no"`) = `False`.

---

```python
@dataclass
class AppConfig:
```
Определяем класс конфигурации. Декоратор `@dataclass` автоматически создаст `__init__` из всех полей.

---

```python
    LLM_PROVIDER: str = field(default_factory=lambda: _env("LLM_PROVIDER", "groq"))
```
- `LLM_PROVIDER` — название провайдера LLM: `"groq"` или `"openrouter"`
- `field(default_factory=...)` — значение вычисляется при создании объекта (не при загрузке модуля)
- `lambda: _env(...)` — анонимная функция без аргументов которая читает `.env`

---

```python
    GROQ_API_KEY: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
```
API-ключ для сервиса Groq (бесплатные LLM с высокой скоростью).

---

```python
    GROQ_MODEL: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))
```
Название модели Groq. `"llama-3.3-70b-versatile"` — LLaMA 3.3 70B, хорошо работает для спортивного коучинга.

---

```python
    OPENROUTER_API_KEY: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    OPENROUTER_MODEL: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"))
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
```
Настройки второго провайдера OpenRouter. `OPENROUTER_BASE_URL` — константа, поэтому просто строка (не `field(...)`).

---

```python
    MAX_TOKENS: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 2048))
```
Максимальное количество токенов в ответе LLM. 2048 ≈ ~1500 слов.

---

```python
    TEMPERATURE: float = field(default_factory=lambda: float(_env("TEMPERATURE", "0.7")))
```
Температура генерации: 0.0 = детерминированный, 2.0 = очень случайный. 0.7 — баланс между точностью и разнообразием.

---

```python
    MAX_AGENT_ITERATIONS: int = 5
```
Максимальное число итераций ReAct-цикла агента. 5 — достаточно для большинства задач без риска бесконечного цикла.

---

```python
    CHAT_MEMORY_SIZE: int = 6
```
Сколько последних сообщений хранить в памяти чата с агентом. 6 = 3 обмена «пользователь-бот».

---

```python
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
```
Токен бота от `@BotFather`. Без него бот не запустится.

---

```python
    ADMIN_TELEGRAM_ID: int = field(default_factory=lambda: _env_int("ADMIN_TELEGRAM_ID", 0))
```
Telegram ID владельца бота (тренера-администратора). `0` означает «не задан». Используется в мидлваре для автоматического назначения роли COACH.

---

```python
    BOT_NAME: str = field(default_factory=lambda: _env("BOT_NAME", "AI Coach"))
```
Имя бота для обращений в сообщениях. По умолчанию `"AI Coach"`.

---

```python
    DATABASE_URL: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coach",
        )
    )
```
Строка подключения к PostgreSQL. Формат: `драйвер://пользователь:пароль@хост:порт/база`. `asyncpg` — асинхронный драйвер PostgreSQL.

---

```python
    SQLITE_FALLBACK: bool = field(default_factory=lambda: _env_bool("SQLITE_FALLBACK", False))
```
Флаг режима разработки. `SQLITE_FALLBACK=1` в `.env` переключает на локальный SQLite-файл — не нужно поднимать PostgreSQL.

---

```python
    SCHEDULER_TIMEZONE: str = field(default_factory=lambda: _env("SCHEDULER_TIMEZONE", "Europe/Moscow"))
```
Таймзона для планировщика APScheduler. `"Europe/Moscow"` = UTC+3.

---

```python
    DAILY_POLL_TIME: str = field(default_factory=lambda: _env("DAILY_POLL_TIME", "08:00"))
```
Время ежедневного опроса спортсменов в формате `"HH:MM"`. В 08:00 утра по часовому поясу планировщика.

---

```python
    STRAVA_CLIENT_ID: str = field(default_factory=lambda: _env("STRAVA_CLIENT_ID"))
    STRAVA_CLIENT_SECRET: str = field(default_factory=lambda: _env("STRAVA_CLIENT_SECRET"))
```
Учётные данные приложения Strava API. Получаются на https://www.strava.com/settings/api.

---

```python
    STRAVA_REDIRECT_URI: str = field(
        default_factory=lambda: _env("STRAVA_REDIRECT_URI", "http://localhost:8080/strava/callback")
    )
```
URL для OAuth-callback: после авторизации в Strava пользователь перенаправляется сюда. Должен совпадать с настройкой в личном кабинете Strava API.

---

```python
    PAYMENTS_PROVIDER_TOKEN: str = field(default_factory=lambda: _env("PAYMENTS_PROVIDER_TOKEN"))
    PAYMENTS_CURRENCY: str = field(default_factory=lambda: _env("PAYMENTS_CURRENCY", "RUB"))
```
Токен платёжного провайдера (ЮKassa, Stripe и т.д.) — выдаётся в `@BotFather → Payments`. Валюта — `"RUB"` по умолчанию.

---

```python
    WEBAPP_HOST: str = field(default_factory=lambda: _env("WEBAPP_HOST", "0.0.0.0"))
    WEBAPP_PORT: int = field(default_factory=lambda: _env_int("WEBAPP_PORT", 8080))
```
На каком хосте и порту запускать FastAPI веб-сервер. `"0.0.0.0"` — слушать на всех сетевых интерфейсах.

---

```python
    WEBAPP_PUBLIC_URL: str = field(
        default_factory=lambda: _env("WEBAPP_PUBLIC_URL", "http://localhost:8080")
    )
```
Публичный URL мини-приложения. Если начинается с `https` — кнопка «Дашборд» появится в меню бота (Telegram требует HTTPS для WebApp).

---

```python
    LOG_DIR: str = "logs"
    LOG_ROTATION: str = "1 MB"
    LOG_RETENTION: str = "7 days"
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
```
Настройки логирования:
- `LOG_DIR` — папка для файлов логов
- `LOG_ROTATION` — создавать новый файл при достижении 1 МБ
- `LOG_RETENTION` — удалять файлы старше 7 дней
- `LOG_LEVEL` — минимальный уровень: INFO (DEBUG, INFO, WARNING, ERROR)

---

```python
    APP_TITLE: str = "AI Coach — Telegram + WebApp"
    APP_VERSION: str = "3.0.0"
```
Мета-данные приложения. Используются в FastAPI Swagger UI (документации API).

---

```python
    FONT_DIR: str = "fonts"
    FONT_REGULAR: str = "fonts/DejaVuSans.ttf"
    FONT_BOLD: str = "fonts/DejaVuSans-Bold.ttf"
```
Пути к шрифтам для генерации PDF-отчётов. DejaVu Sans поддерживает кириллицу.

---

```python
    WELLNESS_FATIGUE_WEIGHT: float = 5.0
    WELLNESS_SLEEP_WEIGHT: float = 5.0
    MIN_RESPONSE_QUALITY: float = 50.0
```
Коэффициенты для формул метрик:
- `WELLNESS_FATIGUE_WEIGHT` = 5.0 — вес усталости в wellness_score
- `WELLNESS_SLEEP_WEIGHT` = 5.0 — вес сна в wellness_score
- `MIN_RESPONSE_QUALITY` = 50.0 — минимальный порог качества ответа агента

---

```python
    @property
    def MODEL_NAME(self) -> str:
```
`@property` — этот атрибут вычисляется как метод, но обращаться к нему как к обычному атрибуту: `config.MODEL_NAME`. Не нужны скобки.

---

```python
        if self.LLM_PROVIDER == "openrouter":
            return self.OPENROUTER_MODEL
        return self.GROQ_MODEL
```
Если провайдер — openrouter, возвращаем его модель. Иначе — модель Groq.

---

```python
    @property
    def API_KEY(self) -> str:
```
Аналогично — возвращает активный API-ключ в зависимости от выбранного провайдера.

---

```python
    @property
    def effective_database_url(self) -> str:
```
Фактический URL для подключения к БД.

---

```python
        if self.SQLITE_FALLBACK:
            return "sqlite+aiosqlite:///coach.db"
        return self.DATABASE_URL
```
`aiosqlite` — асинхронный драйвер SQLite. `///coach.db` — три слеша = относительный путь от рабочей директории.

---

```python
    def __post_init__(self) -> None:
```
Специальный метод датакласса. Вызывается автоматически **сразу после** `__init__`. Здесь выполняем проверки корректности.

---

```python
        if self.LLM_PROVIDER not in ("groq", "openrouter"):
            raise ValueError(...)
```
Если задан неизвестный провайдер — немедленно бросаем исключение с понятным сообщением. Лучше упасть при старте, чем получать непонятные ошибки позже.

---

```python
        if not self.API_KEY:
            key_name = "OPENROUTER_API_KEY" if self.LLM_PROVIDER == "openrouter" else "GROQ_API_KEY"
            raise ValueError(...)
```
Без API-ключа агент работать не будет. Сообщаем пользователю конкретно какую переменную нужно добавить в `.env`.

---

```python
        if not (1 <= self.MAX_AGENT_ITERATIONS <= 10):
            raise ValueError("MAX_AGENT_ITERATIONS должен быть 1..10")
```
Границы для числа итераций агента. 0 — бессмысленно, больше 10 — риск бесконечного цикла. `1 <= x <= 10` — Python позволяет такую цепочку сравнений.

---

```python
        if not (0.0 <= self.TEMPERATURE <= 2.0):
            raise ValueError("TEMPERATURE должен быть 0.0..2.0")
```
Допустимый диапазон температуры для OpenAI-совместимых API.

---

```python
config = AppConfig()
```
**Ключевая строка.** Создаём единственный экземпляр конфигурации. Этот объект импортируют все остальные модули: `from app.config import config`. Синглтон — один объект на всё приложение. Выполняется при первом импорте — `__post_init__` проверит все значения сразу.
