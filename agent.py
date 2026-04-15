# ============================================================
# agent.py — Ядро ИИ-агента спортивного тренера
# ============================================================
# Реализует паттерн ReAct (Reasoning + Acting):
# 1. Получает запрос пользователя
# 2. Решает, нужен ли инструмент (tool-calling)
# 3. Исполняет инструмент и получает результат
# 4. Формирует финальный ответ
#
# Поддерживает контекст чата (chat memory) для связных диалогов.
# ============================================================

import os
import json
import time
from dotenv import load_dotenv
from loguru import logger

from config import config
from tools import (
    get_training_plan_prompt,
    get_analysis_prompt,
    get_recovery_prompt,
    get_nutrition_prompt,
    get_workload_analysis_prompt,
)

load_dotenv()

os.makedirs(config.LOG_DIR, exist_ok=True)
logger.add(
    f"{config.LOG_DIR}/agent_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)

# ── Инициализация клиента LLM ─────────────────────────────────

if config.LLM_PROVIDER == "openrouter":
    from openai import OpenAI
    client = OpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
    )
else:
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)


# ── Справочник инструментов ───────────────────────────────────

TOOL_NAMES_RU = {
    "generate_training_plan":   "Составление плана тренировок",
    "analyze_progress":         "Анализ прогресса",
    "recovery_recommendation":  "Оценка восстановления",
    "nutrition_recommendation": "Рекомендации по питанию",
    "analyze_workload":         "Анализ тренировочной нагрузки",
}

# ── Определения инструментов (OpenAI function-calling schema) ─

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_training_plan",
            "description": (
                "Составляет детальный план тренировок по дням недели. "
                "Используй когда просят план, программу, расписание тренировок."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weeks": {
                        "type": "string",
                        "description": "Количество недель плана: 1, 2 или 4",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Акцент: сила, выносливость, скорость, восстановление",
                    },
                },
                "required": ["weeks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_progress",
            "description": (
                "Анализирует прогресс и результаты тренировок. "
                "Используй когда предоставлены конкретные результаты или данные журнала."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "string",
                        "description": "Результаты тренировок для анализа",
                    },
                },
                "required": ["results"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recovery_recommendation",
            "description": (
                "Оценивает восстановление и даёт рекомендации. "
                "Используй при жалобах на усталость, боли, плохой сон."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fatigue_level": {
                        "type": "string",
                        "description": "Уровень усталости от 1 до 10",
                    },
                    "symptoms": {
                        "type": "string",
                        "description": "Боли, дискомфорт, симптомы",
                    },
                    "sleep_quality": {
                        "type": "string",
                        "description": "Качество сна от 1 до 10",
                    },
                },
                "required": ["fatigue_level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nutrition_recommendation",
            "description": (
                "Рекомендации по питанию: КБЖУ, меню, режим. "
                "Используй при вопросах про питание, рацион, диету."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "training_day": {
                        "type": "string",
                        "description": "Тип дня: тренировочный или день отдыха",
                    },
                    "specific_goal": {
                        "type": "string",
                        "description": "Конкретная цель питания",
                    },
                },
                "required": ["training_day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_workload",
            "description": (
                "Анализирует тренировочную нагрузку по данным журнала: "
                "RPE, статусы выполнения, паттерны. Используй когда "
                "просят проанализировать журнал тренировок или нагрузку."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "logs_summary": {
                        "type": "string",
                        "description": "Сводка записей журнала тренировок",
                    },
                },
                "required": ["logs_summary"],
            },
        },
    },
]


# ── Вызов LLM ─────────────────────────────────────────────────

def _llm_call(messages: list, use_tools: bool = False) -> object:
    """Единая точка вызова LLM (Groq или OpenRouter)"""
    kwargs = dict(
        model=config.MODEL_NAME,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
    )
    if use_tools:
        kwargs["tools"] = TOOLS
        kwargs["tool_choice"] = "auto"

    return client.chat.completions.create(**kwargs)


# ── Исполнение инструмента ────────────────────────────────────

def execute_tool(tool_name: str, tool_args: dict, athlete: dict) -> str:
    """
    Исполняет инструмент агента.

    Каждый инструмент:
    1. Валидирует входные аргументы
    2. Формирует специализированный промпт
    3. Вызывает LLM для генерации ответа
    4. Логирует время выполнения

    Returns:
        str: Результат инструмента (текст ответа LLM или сообщение об ошибке).
    """
    t_start = time.time()

    try:
        # ── Маршрутизация по имени инструмента ────────────────
        if tool_name == "generate_training_plan":
            weeks = int(tool_args.get("weeks", 1))
            focus = tool_args.get("focus", "общая подготовка")
            prompt = get_training_plan_prompt(athlete, weeks, focus)

        elif tool_name == "analyze_progress":
            results = tool_args.get("results", "").strip()
            if not results:
                return "⚠️ Не предоставлены результаты для анализа."
            prompt = get_analysis_prompt(athlete, results)

        elif tool_name == "recovery_recommendation":
            fatigue  = tool_args.get("fatigue_level", "5")
            symptoms = tool_args.get("symptoms", "нет жалоб")
            sleep_q  = tool_args.get("sleep_quality", "7")
            prompt   = get_recovery_prompt(athlete, int(fatigue), int(sleep_q), symptoms)

        elif tool_name == "nutrition_recommendation":
            training_day  = tool_args.get("training_day", "тренировочный")
            specific_goal = tool_args.get("specific_goal")
            prompt        = get_nutrition_prompt(athlete, training_day, specific_goal)

        elif tool_name == "analyze_workload":
            logs_summary = tool_args.get("logs_summary", "").strip()
            if not logs_summary:
                return "⚠️ Не предоставлены данные журнала для анализа."
            prompt = get_workload_analysis_prompt(athlete, logs_summary)

        else:
            return f"⚠️ Инструмент «{tool_name}» не найден."

        # ── Вызов LLM ────────────────────────────────────────
        response = _llm_call([
            {
                "role": "system",
                "content": (
                    "Ты профессиональный спортивный тренер с 15-летним опытом. "
                    "Давай конкретные, структурированные рекомендации на русском языке. "
                    "Используй числа, факты и примеры."
                ),
            },
            {"role": "user", "content": prompt},
        ])

        result = response.choices[0].message.content or "Ответ не получен."
        elapsed = (time.time() - t_start) * 1000
        logger.info(f"Tool '{tool_name}' OK | {elapsed:.0f}ms | {len(result)} chars")
        return result

    except ValueError as e:
        logger.warning(f"Tool '{tool_name}' validation error: {e}")
        return f"⚠️ Ошибка параметров инструмента «{TOOL_NAMES_RU.get(tool_name, tool_name)}»: {e}"

    except Exception as e:
        logger.error(f"Tool '{tool_name}' FAILED: {e}")
        return f"⚠️ Ошибка инструмента «{TOOL_NAMES_RU.get(tool_name, tool_name)}»: {str(e)}"


# ── Основной цикл агента ──────────────────────────────────────

def run_agent(
    user_message: str,
    athlete: dict,
    chat_history: list = None,
) -> tuple[str, list]:
    """
    Запускает агентский цикл ReAct.

    Алгоритм:
    1. Формирует системный промпт с профилем спортсмена
    2. Добавляет контекст из истории чата (memory)
    3. Отправляет запрос в LLM с доступными инструментами
    4. Если LLM вызывает инструмент — исполняет и повторяет
    5. Возвращает финальный ответ и список шагов рассуждения

    Args:
        user_message: Текст запроса пользователя
        athlete:      Профиль спортсмена (dict)
        chat_history: История чата для контекста (опционально)

    Returns:
        tuple[str, list]: (финальный ответ, список шагов агента)
    """
    t_total = time.time()
    logger.info(f"Agent START | athlete={athlete.get('name')} | query={user_message[:80]}")

    # ── Системный промпт ──────────────────────────────────────
    system_prompt = f"""Ты — профессиональный ИИ-агент спортивного тренера. Отвечай ТОЛЬКО на русском языке.

ПРОФИЛЬ СПОРТСМЕНА:
- Имя: {athlete['name']}, возраст: {athlete['age']} лет
- Вид спорта: {athlete['sport']} | Уровень: {athlete['level']}
- Цель: {athlete['goal']} | Тренировок/нед.: {athlete['sessions_per_week']}

КОГДА ИСПОЛЬЗОВАТЬ ИНСТРУМЕНТЫ:
- generate_training_plan   → просьба составить план/программу тренировок
- analyze_progress         → анализ конкретных результатов/прогресса
- recovery_recommendation  → усталость, боли, вопросы о восстановлении
- nutrition_recommendation → вопросы о питании, рационе, диете
- analyze_workload         → анализ журнала тренировок и нагрузки (RPE, статусы)

ПРАВИЛА:
1. На общие вопросы — отвечай напрямую без инструментов
2. На конкретные задачи — используй подходящий инструмент
3. После получения результата инструмента — интегрируй его в ответ
4. Не вызывай один инструмент дважды за запрос
5. Если нужны данные, которых нет — попроси пользователя предоставить"""

    messages = [{"role": "system", "content": system_prompt}]

    # ── Добавляем контекст чата (memory) ──────────────────────
    if chat_history:
        memory_size = config.CHAT_MEMORY_SIZE
        recent = chat_history[-memory_size:]
        for msg in recent:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"][:500],  # ограничиваем размер
                })
        logger.debug(f"Chat memory: {len(recent)} messages added")

    messages.append({"role": "user", "content": user_message})

    # ── Цикл ReAct ────────────────────────────────────────────
    steps: list = []
    last_tool_result = None
    used_tools: set = set()  # предотвращаем повторный вызов

    for iteration in range(config.MAX_AGENT_ITERATIONS):
        try:
            response = _llm_call(messages, use_tools=True)
        except Exception as e:
            logger.error(f"API error iter={iteration + 1}: {e}")
            err = f"⚠️ Ошибка соединения с ИИ: {e}"
            steps.append({"type": "final", "content": err, "tool_name": None})
            return err, steps

        message       = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # ── Инструментальный вызов ────────────────────────────
        if finish_reason == "tool_calls" and message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name

            # Защита от повторного вызова
            if tool_name in used_tools:
                logger.warning(f"Tool '{tool_name}' already used, skipping")
                messages.append({
                    "role": "assistant",
                    "content": "Этот инструмент уже был использован. Формирую ответ.",
                })
                continue

            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            # Шаг: мышление
            steps.append({
                "type":      "thinking",
                "content":   f"Применяю: **{TOOL_NAMES_RU.get(tool_name, tool_name)}**",
                "args":      tool_args,
                "tool_name": tool_name,
            })

            # Исполнение инструмента
            tool_result      = execute_tool(tool_name, tool_args, athlete)
            last_tool_result = tool_result
            used_tools.add(tool_name)

            # Шаг: результат
            steps.append({
                "type":      "result",
                "content":   tool_result,
                "tool_name": tool_name,
            })

            # Добавляем в контекст для LLM
            messages.append({
                "role":       "assistant",
                "content":    message.content or "",
                "tool_calls": [{
                    "id":       tool_call.id,
                    "type":     "function",
                    "function": {
                        "name":      tool_name,
                        "arguments": tool_call.function.arguments,
                    },
                }],
            })
            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      tool_result,
            })

        # ── Финальный ответ ───────────────────────────────────
        else:
            final = message.content
            if not final:
                final = last_tool_result or "Не удалось сформировать ответ. Попробуйте переформулировать вопрос."

            elapsed = (time.time() - t_total) * 1000
            steps.append({
                "type":        "final",
                "content":     final,
                "tool_name":   None,
                "duration_ms": elapsed,
                "iterations":  iteration + 1,
            })
            logger.info(
                f"Agent DONE | {elapsed:.0f}ms | "
                f"iterations={iteration + 1} | "
                f"tools={list(used_tools)}"
            )
            return final, steps

    # ── Лимит итераций ────────────────────────────────────────
    final = last_tool_result or "Достигнут лимит итераций агента."
    elapsed = (time.time() - t_total) * 1000
    steps.append({
        "type": "final", "content": final,
        "tool_name": None, "duration_ms": elapsed,
    })
    logger.warning(f"Agent hit iteration limit ({config.MAX_AGENT_ITERATIONS})")
    return final, steps
