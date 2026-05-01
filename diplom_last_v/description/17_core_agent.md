# app/core/agent.py — LLM-агент (ReAct + function calling)

## Назначение файла
Реализует цикл агента: принимает вопрос пользователя → строит промпт → вызывает LLM → если LLM хочет инструмент — выполняет его и снова вызывает LLM → возвращает финальный ответ.

---

## Построчный разбор

```python
from __future__ import annotations
```
Разрешает современные аннотации типов.

---

```python
import asyncio
```
Нужен для `asyncio.to_thread()` — запуска синхронного SDK в отдельном потоке.

---

```python
import json
```
Стандартная библиотека. Нужна для `json.loads()` — разбора аргументов инструмента. LLM возвращает аргументы как JSON-строку: `'{"weeks": "2", "focus": "сила"}'`.

---

```python
import os
```
Для `os.makedirs()` — создание папки логов.

---

```python
import time
```
Стандартная библиотека. `time.time()` — текущее время в секундах (для измерения скорости работы инструментов).

---

```python
from typing import Any, Optional
```
- `Any` — произвольный тип (ответ от LLM SDK)
- `Optional[str]` — строка или `None`

---

```python
from loguru import logger
```
Логгер — записываем старт/финиш агента и вызовы инструментов.

---

```python
from app.config import config
```
Конфигурация: модель, температура, API-ключи, лимиты.

---

```python
from app.core.prompts import (
    get_analysis_prompt,
    get_nutrition_prompt,
    get_recovery_prompt,
    get_training_plan_prompt,
    get_workload_analysis_prompt,
)
```
Импортируем все пять функций-шаблонов промптов. Каждый инструмент использует свою функцию.

---

```python
os.makedirs(config.LOG_DIR, exist_ok=True)
```
Создаём папку `logs/` если нет.

---

```python
logger.add(
    f"{config.LOG_DIR}/agent_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)
```
Отдельный файл логов для агента (`agent_2024-01-15.log`). `{{time}}` — экранированные фигурные скобки в f-строке, loguru подставит дату.

---

```python
if config.LLM_PROVIDER == "openrouter":
    from openai import OpenAI
    _client = OpenAI(api_key=config.OPENROUTER_API_KEY, base_url=config.OPENROUTER_BASE_URL)
else:
    from groq import Groq
    _client = Groq(api_key=config.GROQ_API_KEY)
```
Выбор провайдера при **загрузке модуля** (не при каждом вызове).
- `if/else` на уровне модуля — выполняется один раз при первом импорте
- `_client` — синглтон клиента, нижнее подчёркивание = «приватная» переменная модуля
- Оба SDK (openai и groq) имеют **одинаковый** интерфейс: `client.chat.completions.create(...)`. Это намеренно — Groq SDK совместим с OpenAI API.

---

```python
TOOLS = [
    {
        "type": "function",
```
`TOOLS` — константа (заглавные буквы = соглашение о константах в Python). Список словарей в формате OpenAI function-calling.

`"type": "function"` — обязательное поле, говорит LLM что это описание функции.

---

```python
        "function": {
            "name": "generate_training_plan",
```
Имя функции. LLM будет использовать именно эту строку в `tool_calls[].function.name`.

---

```python
            "description": "Составляет план тренировок по дням. Используй, когда просят план/программу/расписание.",
```
**Самое важное поле.** LLM читает это описание и сам решает — нужен ли инструмент. Чем точнее описание — тем правильнее LLM выбирает инструмент.

---

```python
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "string", "description": "Количество недель: 1, 2 или 4"},
                    "focus": {"type": "string", "description": "Акцент: сила, выносливость, скорость, восстановление"},
                },
                "required": ["weeks"],
            },
```
JSON Schema параметров функции:
- `"type": "object"` — параметры передаются как объект (словарь)
- `"properties"` — описание каждого параметра
- `"required": ["weeks"]` — `weeks` обязателен, `focus` — нет. LLM обязан включить `weeks` в вызов.

---

```python
def _llm_call(messages: list, use_tools: bool = False) -> Any:
    """Синхронный вызов LLM (внутри to_thread)."""
```
**Синхронная** функция (без `async`). Оба SDK (Groq и OpenAI) синхронные — блокируют поток до получения ответа.

---

```python
    kwargs = dict(
        model=config.MODEL_NAME,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
    )
```
Словарь параметров запроса. Используем `dict(...)` вместо `{...}` — личное предпочтение, оба варианта равнозначны.
- `model` — имя модели: `"llama-3.3-70b-versatile"` или `"openai/gpt-oss-120b:free"`
- `messages` — история диалога в формате `[{role, content}, ...]`
- `temperature` — случайность ответа (0.7)
- `max_tokens` — максимальная длина ответа (2048)

---

```python
    if use_tools:
        kwargs["tools"] = TOOLS
        kwargs["tool_choice"] = "auto"
```
Если нужны инструменты — добавляем их в запрос.
- `"tools": TOOLS` — передаём описания всех 5 инструментов
- `"tool_choice": "auto"` — LLM сам решает использовать ли инструмент. Альтернативы: `"none"` (никогда), `"required"` (всегда).

---

```python
    return _client.chat.completions.create(**kwargs)
```
Отправляем запрос к LLM. `**kwargs` — распаковываем словарь в именованные аргументы. Возвращаем ответ напрямую.

---

```python
async def _llm_call_async(messages: list, use_tools: bool = False) -> Any:
    """Асинхронная обёртка: выносим блокирующий SDK в thread-pool."""
    return await asyncio.to_thread(_llm_call, messages, use_tools)
```
**Ключевая функция.** `asyncio.to_thread(func, *args)` — запускает синхронную функцию `func` в отдельном потоке, не блокируя event loop.

Без этого: при вызове LLM бот «замерзает» на 2-5 секунд — никакие другие сообщения не обрабатываются. С этим: LLM работает в отдельном потоке, бот продолжает принимать сообщения.

---

```python
async def _execute_tool(
    tool_name: str,
    tool_args: dict,
    athlete: dict,
    base_program: Optional[str] = None,
) -> str:
```
Асинхронная функция выполнения инструмента. Принимает имя инструмента, аргументы от LLM, профиль спортсмена, базовую программу тренера. Возвращает строку — результат работы инструмента.

---

```python
    t0 = time.time()
```
Засекаем время начала — для метрики в логах.

---

```python
    try:
        if tool_name == "generate_training_plan":
            weeks = int(tool_args.get("weeks") or 1)
```
`tool_args.get("weeks") or 1` — берём значение по ключу `"weeks"`. Если `None` или пустая строка — используем `1` как значение по умолчанию. `int(...)` — конвертируем в число.

---

```python
            focus = tool_args.get("focus") or "общая подготовка"
```
Акцент тренировки. Если LLM не передал — используем значение по умолчанию.

---

```python
            prompt = get_training_plan_prompt(athlete, weeks, focus, base_program=base_program)
```
Формируем промпт через шаблонную функцию из `prompts.py`.

---

```python
        elif tool_name == "analyze_progress":
            results = (tool_args.get("results") or "").strip()
            if not results:
                return "⚠️ Не предоставлены результаты для анализа."
```
`or ""` — если `None`, берём пустую строку. `.strip()` — убираем пробелы. Если результатов нет — возвращаем предупреждение сразу, без вызова LLM.

---

```python
        elif tool_name == "recovery_recommendation":
            fatigue = int(tool_args.get("fatigue_level") or 5)
            sleep_q = int(tool_args.get("sleep_quality") or 7)
            pain = tool_args.get("symptoms") or "нет жалоб"
            prompt = get_recovery_prompt(athlete, fatigue, sleep_q, pain)
```
Параметры восстановления. Дефолтные значения: усталость=5 (средняя), сон=7 (хороший).

---

```python
        elif tool_name == "nutrition_recommendation":
            training_day = tool_args.get("training_day") or "тренировочный"
            specific_goal = tool_args.get("specific_goal")
            prompt = get_nutrition_prompt(athlete, training_day, specific_goal)
```
`specific_goal` без `or` — может быть `None` (необязательный параметр).

---

```python
        elif tool_name == "analyze_workload":
            logs_summary = (tool_args.get("logs_summary") or "").strip()
            if not logs_summary:
                return "⚠️ Не предоставлены данные журнала для анализа."
            prompt = get_workload_analysis_prompt(athlete, logs_summary)
```

---

```python
        else:
            return f"⚠️ Инструмент «{tool_name}» не найден."
```
Защита от неизвестных инструментов. Теоретически не должно происходить, но LLM иногда «придумывает» несуществующие инструменты.

---

```python
        response = await _llm_call_async(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты профессиональный спортивный тренер с 15-летним опытом. "
                        "Давай конкретные, структурированные рекомендации на русском языке. "
                        "Используй числа, факты и примеры."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
```
Второй вызов LLM — для **выполнения** инструмента. Передаём простой 2-сообщенный диалог:
- system: роль и стиль ответа
- user: промпт (уже сформированный шаблонной функцией)

Обратите внимание: здесь **нет** `use_tools=True` — в этом вызове инструменты не нужны, нам нужен просто текст.

---

```python
        result = response.choices[0].message.content or "Ответ не получен."
```
`response.choices` — список вариантов ответа. Берём первый `[0]`. `.message.content` — текст ответа. `or "Ответ не получен."` — если `None`, используем заглушку.

---

```python
        logger.info(f"Tool '{tool_name}' OK | {(time.time()-t0)*1000:.0f}ms")
```
Логируем: какой инструмент отработал и сколько миллисекунд занял. `(time.time()-t0)*1000` — разница в секундах × 1000 = миллисекунды. `:.0f` — без знаков после запятой.

---

```python
        return result
```
Возвращаем текст ответа LLM как результат инструмента.

---

```python
    except Exception as e:  # noqa: BLE001 — ловим всё ради UX бота
        logger.error(f"Tool '{tool_name}' FAILED: {e}")
        return f"⚠️ Ошибка инструмента «{tool_name}»: {e}"
```
`# noqa: BLE001` — отключаем предупреждение линтера о «широком» `except Exception`. Мы намеренно ловим всё — лучше вернуть сообщение об ошибке пользователю, чем упасть и не ответить вообще.

---

```python
async def run_agent(
    user_message: str,
    athlete: dict,
    *,
    chat_history: Optional[list] = None,
    brand_name: str = "AI Coach",
    base_program: Optional[str] = None,
) -> str:
```
Главная функция. `*` — всё после неё только через имя: `run_agent("вопрос", {...}, brand_name="Тренер")`. Возвращает строку — финальный ответ агента.

---

```python
    t_total = time.time()
    logger.info(f"Agent START | athlete={athlete.get('name')} | q={user_message[:80]!r}")
```
Начало измерения времени всего цикла. `!r` — repr-форматирование (добавляет кавычки, экранирует спецсимволы). `[:80]` — только первые 80 символов вопроса.

---

```python
    system_prompt = f"""Ты — «{brand_name}», профессиональный ИИ-тренер. Отвечай ТОЛЬКО на русском.

ПРОФИЛЬ СПОРТСМЕНА:
- Имя: {athlete.get('name', '—')}, возраст: {athlete.get('age', '—')} лет
- Вид спорта: {athlete.get('sport', '—')} | Уровень: {athlete.get('level', '—')}
- Цель: {athlete.get('goal', '—')} | Тренировок/нед.: {athlete.get('sessions_per_week', '—')}
...
"""
```
Системный промпт — инструкция для LLM о его роли. Персонализирован: вставляем имя тренера и профиль спортсмена. `.get('name', '—')` — безопасное получение с дефолтом `'—'`.

---

```python
    if base_program:
        system_prompt += f"\nБАЗОВАЯ ПРОГРАММА ТРЕНЕРА:\n{base_program.strip()}\n"
```
Если тренер задал базовую программу — дописываем её в системный промпт. `+=` — конкатенация строк (дописываем в конец). `.strip()` — убираем лишние пробелы/переносы.

---

```python
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
```
Начинаем список сообщений с системного промпта. Тип аннотации `list[dict]` — список словарей.

---

```python
    if chat_history:
        recent = chat_history[-config.CHAT_MEMORY_SIZE:]
```
`chat_history[-6:]` — берём последние 6 элементов списка. Отрицательный индекс = от конца. Это «окно памяти» — LLM не будет читать всю историю, только последние 6 реплик.

---

```python
        for msg in recent:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": str(msg["content"])[:800]})
```
Добавляем каждое сообщение истории. Фильтры:
- `role in ("user", "assistant")` — только реплики диалога (не системные)
- `msg.get("content")` — не пустые
- `[:800]` — обрезаем до 800 символов (защита от очень длинных предыдущих ответов)

---

```python
    messages.append({"role": "user", "content": user_message})
```
Добавляем текущий вопрос пользователя в конец списка.

---

```python
    used_tools: set[str] = set()
```
Пустое множество — будем записывать сюда имена уже вызванных инструментов. `set` — коллекция уникальных элементов, быстрая проверка `in`.

---

```python
    final_text: str = ""
```
Переменная для финального ответа. Инициализируем пустой строкой — если цикл закончится без ответа, вернём заглушку.

---

```python
    for iteration in range(config.MAX_AGENT_ITERATIONS):
```
Цикл максимум `MAX_AGENT_ITERATIONS = 5` раз. Защита от бесконечного цикла.

---

```python
        try:
            response = await _llm_call_async(messages, use_tools=True)
        except Exception as e:
            logger.error(f"LLM error iter={iteration + 1}: {e}")
            return f"⚠️ Ошибка соединения с ИИ: {e}"
```
Вызываем LLM с инструментами. При ошибке сети/API — возвращаем понятное сообщение пользователю.

---

```python
        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
```
Извлекаем сообщение и причину завершения. `finish_reason` может быть:
- `"stop"` — LLM закончил ответ
- `"tool_calls"` — LLM хочет вызвать инструмент
- `"length"` — достигнут лимит токенов

---

```python
        tool_calls = getattr(msg, "tool_calls", None) or []
```
`getattr(obj, "attr", default)` — безопасное получение атрибута с дефолтом. Если у `msg` нет атрибута `tool_calls` (разные SDK возвращают по-разному) — берём `None`. `or []` — если `None`, берём пустой список.

---

```python
        if tool_calls and finish_reason in (None, "tool_calls", "stop"):
```
Если LLM запросил инструменты (список не пуст) И причина завершения допустима — обрабатываем вызов инструментов.

---

```python
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                }
            )
```
Добавляем в историю сообщение ассистента с `tool_calls`. Это обязательно — API требует чтобы после assistant-сообщения с tool_calls шли tool-сообщения с результатами.

`tc.model_dump()` — конвертирует pydantic-объект в словарь (для сериализации в JSON).

---

```python
            for tc in tool_calls:
```
Итерируемся по каждому вызову инструмента (обычно один, но может быть несколько).

---

```python
                tname = tc.function.name
```
Имя инструмента: `"generate_training_plan"`, `"analyze_progress"` и т.д.

---

```python
                try:
                    targs = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    targs = {}
```
LLM передаёт аргументы как JSON-строку: `'{"weeks": "2"}'`. `json.loads()` конвертирует в словарь. `tc.function.arguments or "{}"` — если аргументы пустые (`None`), парсим пустой объект. При ошибке парсинга — используем пустой словарь (LLM иногда генерирует невалидный JSON).

---

```python
                if tname in used_tools:
                    tool_result = "⚠️ Инструмент уже вызывался в этом диалоге."
```
Защита от зацикливания: один инструмент в одном ответе не вызывается дважды.

---

```python
                else:
                    tool_result = await _execute_tool(tname, targs, athlete, base_program=base_program)
                    used_tools.add(tname)
```
Выполняем инструмент и добавляем его имя в множество использованных.

---

```python
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )
```
Добавляем результат инструмента в историю. `role: "tool"` — специальная роль для результатов инструментов. `tool_call_id` — связывает результат с конкретным вызовом (если вызывались несколько инструментов).

---

```python
            continue
```
Переходим к следующей итерации цикла — снова вызываем LLM чтобы он сформировал финальный ответ на основе результата инструмента.

---

```python
        final_text = msg.content or ""
        break
```
Если нет `tool_calls` — это финальный текстовый ответ. Сохраняем и выходим из цикла.

---

```python
    logger.info(f"Agent DONE | {(time.time()-t_total)*1000:.0f}ms | tools={sorted(used_tools)}")
```
Логируем итог: общее время, список использованных инструментов (отсортированный для читаемости).

---

```python
    return final_text or "Извини, не удалось сформировать ответ."
```
Возвращаем ответ. `or "Извини..."` — если `final_text` пустая строка (не должно, но на всякий случай).
