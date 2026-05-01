# ============================================================
# app/core/agent.py — Async-обёртка LLM-агента (ReAct + tools)
# ============================================================
# Переписан из legacy agent.py под:
#   • async (asyncio.to_thread, чтобы SDK Groq/OpenRouter не
#     блокировали event loop бота).
#   • инъекцию brand_name / base_program тренера в system-prompt.
#   • возврат только финального текста — для хэндлера бота.
# ============================================================

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional

from loguru import logger

from app.config import config
from app.core.prompts import (
    get_analysis_prompt,
    get_nutrition_prompt,
    get_recovery_prompt,
    get_training_plan_prompt,
    get_workload_analysis_prompt,
)

# ── Логи ─────────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logger.add(
    f"{config.LOG_DIR}/agent_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)

# ── Ленивая инициализация клиента LLM ────────────────────────
# Оба SDK (Groq, OpenRouter-OpenAI) — синхронные. Чтобы не
# тормозить бота, все вызовы делаем через asyncio.to_thread().
if config.LLM_PROVIDER == "openrouter":
    from openai import OpenAI
    _client = OpenAI(api_key=config.OPENROUTER_API_KEY, base_url=config.OPENROUTER_BASE_URL)
else:
    from groq import Groq
    _client = Groq(api_key=config.GROQ_API_KEY)


# Инструменты, результат которых возвращается напрямую без пересказа LLM.
# LLM склонен сокращать длинные планы — обходим это, возвращая контент сразу.
DIRECT_RETURN_TOOLS = {
    "generate_training_plan",
    "nutrition_recommendation",
    "recovery_recommendation",
    "analyze_progress",
    "analyze_workload",
}

# ── Определения функций (OpenAI function-calling schema) ──────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_training_plan",
            "description": "Составляет план тренировок по дням. Используй, когда просят план/программу/расписание.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {"type": "string", "description": "Количество недель: 1, 2 или 4"},
                    "focus": {"type": "string", "description": "Акцент: сила, выносливость, скорость, восстановление"},
                },
                "required": ["weeks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_progress",
            "description": "Анализирует результаты тренировок (если они переданы).",
            "parameters": {
                "type": "object",
                "properties": {"results": {"type": "string"}},
                "required": ["results"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recovery_recommendation",
            "description": "Оценка восстановления при жалобах на усталость/боли/сон.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fatigue_level": {"type": "string"},
                    "symptoms": {"type": "string"},
                    "sleep_quality": {"type": "string"},
                },
                "required": ["fatigue_level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nutrition_recommendation",
            "description": "Рекомендации по питанию: КБЖУ, меню.",
            "parameters": {
                "type": "object",
                "properties": {
                    "training_day": {"type": "string"},
                    "specific_goal": {"type": "string"},
                },
                "required": ["training_day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_workload",
            "description": "Анализ журнала тренировок (RPE, статусы).",
            "parameters": {
                "type": "object",
                "properties": {"logs_summary": {"type": "string"}},
                "required": ["logs_summary"],
            },
        },
    },
]


def _llm_call(messages: list, use_tools: bool = False) -> Any:
    """Синхронный вызов LLM (внутри to_thread)."""
    kwargs = dict(
        model=config.MODEL_NAME,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
    )
    if use_tools:
        kwargs["tools"] = TOOLS
        kwargs["tool_choice"] = "auto"
    return _client.chat.completions.create(**kwargs)


async def _llm_call_async(messages: list, use_tools: bool = False) -> Any:
    """Асинхронная обёртка: выносим блокирующий SDK в thread-pool."""
    return await asyncio.to_thread(_llm_call, messages, use_tools)


# ── Исполнение инструмента ────────────────────────────────────
async def _execute_tool(
    tool_name: str,
    tool_args: dict,
    athlete: dict,
    base_program: Optional[str] = None,
) -> str:
    """Сопоставляет имя инструмента с промптом и зовёт LLM."""
    t0 = time.time()
    try:
        if tool_name == "generate_training_plan":
            weeks = int(tool_args.get("weeks") or 1)
            focus = tool_args.get("focus") or "общая подготовка"
            prompt = get_training_plan_prompt(athlete, weeks, focus, base_program=base_program)

        elif tool_name == "analyze_progress":
            results = (tool_args.get("results") or "").strip()
            if not results:
                return "⚠️ Не предоставлены результаты для анализа."
            prompt = get_analysis_prompt(athlete, results)

        elif tool_name == "recovery_recommendation":
            fatigue = int(tool_args.get("fatigue_level") or 5)
            sleep_q = int(tool_args.get("sleep_quality") or 7)
            pain = tool_args.get("symptoms") or "нет жалоб"
            prompt = get_recovery_prompt(athlete, fatigue, sleep_q, pain)

        elif tool_name == "nutrition_recommendation":
            training_day = tool_args.get("training_day") or "тренировочный"
            specific_goal = tool_args.get("specific_goal")
            prompt = get_nutrition_prompt(athlete, training_day, specific_goal)

        elif tool_name == "analyze_workload":
            logs_summary = (tool_args.get("logs_summary") or "").strip()
            if not logs_summary:
                return "⚠️ Не предоставлены данные журнала для анализа."
            prompt = get_workload_analysis_prompt(athlete, logs_summary)

        else:
            return f"⚠️ Инструмент «{tool_name}» не найден."

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
        result = response.choices[0].message.content or "Ответ не получен."
        logger.info(f"Tool '{tool_name}' OK | {(time.time()-t0)*1000:.0f}ms")
        return result

    except Exception as e:  # noqa: BLE001 — ловим всё ради UX бота
        logger.error(f"Tool '{tool_name}' FAILED: {e}")
        return f"⚠️ Ошибка инструмента «{tool_name}»: {e}"


# ── Основной цикл агента ──────────────────────────────────────
async def run_agent(
    user_message: str,
    athlete: dict,
    *,
    chat_history: Optional[list] = None,
    brand_name: str = "AI Coach",
    base_program: Optional[str] = None,
) -> str:
    """
    Запускает ReAct-цикл агента и возвращает финальный ответ.

    Параметры, специфичные для бота:
      brand_name   — имя, которым агент подписывается
      base_program — методика тренера, встраиваемая в инструменты

    История чата (chat_history) — список dict{role, content}
    в формате OpenAI messages.
    """
    t_total = time.time()
    logger.info(f"Agent START | athlete={athlete.get('name')} | q={user_message[:80]!r}")

    # ── Системный промпт ─────────────────────────────────────
    system_prompt = f"""Ты — «{brand_name}», профессиональный ИИ-тренер. Отвечай ТОЛЬКО на русском.

ПРОФИЛЬ СПОРТСМЕНА:
- Имя: {athlete.get('name', '—')}, возраст: {athlete.get('age', '—')} лет
- Вид спорта: {athlete.get('sport', '—')} | Уровень: {athlete.get('level', '—')}
- Цель: {athlete.get('goal', '—')} | Тренировок/нед.: {athlete.get('sessions_per_week', '—')}

ИНСТРУМЕНТЫ:
- generate_training_plan   → составить план/программу/расписание
- analyze_progress         → анализ конкретных результатов
- recovery_recommendation  → усталость, боли, сон
- nutrition_recommendation → питание, рацион, диета
- analyze_workload         → анализ журнала (RPE, статусы)

ПРАВИЛА:
1. На общие вопросы отвечай напрямую без инструментов.
2. На конкретные задачи — используй инструмент.
3. Не вызывай один инструмент дважды подряд.
4. Если недостаёт данных — попроси пользователя их предоставить.
"""

    if base_program:
        system_prompt += f"\nБАЗОВАЯ ПРОГРАММА ТРЕНЕРА:\n{base_program.strip()}\n"

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # ── Подмешиваем историю чата ─────────────────────────────
    if chat_history:
        recent = chat_history[-config.CHAT_MEMORY_SIZE:]
        for msg in recent:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": str(msg["content"])[:800]})

    messages.append({"role": "user", "content": user_message})

    used_tools: set[str] = set()
    final_text: str = ""

    for iteration in range(config.MAX_AGENT_ITERATIONS):
        try:
            response = await _llm_call_async(messages, use_tools=True)
        except Exception as e:  # noqa: BLE001
            logger.error(f"LLM error iter={iteration + 1}: {e}")
            return f"⚠️ Ошибка соединения с ИИ: {e}"

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Если LLM запросил инструмент
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls and finish_reason in (None, "tool_calls", "stop"):
            # Добавляем assistant-сообщение с tool_calls
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in tool_calls],
                }
            )
            direct_result: Optional[str] = None
            for tc in tool_calls:
                tname = tc.function.name
                try:
                    targs = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    targs = {}
                if tname in used_tools:
                    tool_result = "⚠️ Инструмент уже вызывался в этом диалоге."
                else:
                    tool_result = await _execute_tool(tname, targs, athlete, base_program=base_program)
                    used_tools.add(tname)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )
                if tname in DIRECT_RETURN_TOOLS:
                    direct_result = tool_result

            # Контент-инструменты возвращаем напрямую — LLM иначе пересказывает
            if direct_result is not None:
                logger.info(f"Agent DIRECT | {(time.time()-t_total)*1000:.0f}ms | tools={sorted(used_tools)}")
                return direct_result
            continue  # для нон-контент инструментов — спрашиваем LLM дальше

        # Финальный текстовый ответ
        final_text = msg.content or ""
        break

    logger.info(f"Agent DONE | {(time.time()-t_total)*1000:.0f}ms | tools={sorted(used_tools)}")
    return final_text or "Извини, не удалось сформировать ответ."
