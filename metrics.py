# ============================================================
# metrics.py — Метрики эффективности агента и спортсмена
# ============================================================
# Модуль реализует:
# 1. Wellness Score — интегральный показатель самочувствия
# 2. Training Load — мониторинг тренировочной нагрузки
# 3. ACWR — Acute:Chronic Workload Ratio (коэф. нагрузки)
# 4. Response Quality — оценка качества ответов агента
# 5. Сводная аналитика — агрегация для дашборда
# ============================================================

from typing import List, Dict, Optional
import pandas as pd
from loguru import logger

from database import (
    get_athlete_sessions,
    get_agent_stats,
    get_athlete_plans,
    get_training_logs,
    get_training_adherence,
)


# ══════════════════════════════════════════════════════════════
# WELLNESS SCORE — Самочувствие (0–100)
# ══════════════════════════════════════════════════════════════

def calculate_wellness_score(fatigue: int, sleep: int) -> float:
    """
    Интегральный показатель самочувствия (0–100).

    Формула: (10 - усталость) × 5 + сон × 5
    Логика: меньше усталость + лучше сон = выше балл.

    Примеры:
      fatigue=1, sleep=10 → 95 (отлично)
      fatigue=5, sleep=7  → 60 (хорошо)
      fatigue=10, sleep=1 → 5  (критично)
    """
    fatigue_score = (10 - fatigue) * 5   # 0–45 баллов
    sleep_score   = sleep * 5             # 5–50 баллов
    return round(fatigue_score + sleep_score, 1)


def wellness_label(score: float) -> tuple[str, str]:
    """Возвращает (emoji, текстовая метка) по Wellness Score"""
    if score >= 70:
        return "🟢", "Отличное"
    elif score >= 50:
        return "🟡", "Хорошее"
    elif score >= 30:
        return "🟠", "Среднее"
    else:
        return "🔴", "Плохое"


def trend_arrow(values: List[float]) -> str:
    """
    Определяет тренд за последние 3 значения.
    Возвращает стрелку: ↑ (рост), ↓ (спад), → (стабильно).
    """
    if len(values) < 2:
        return "→"
    recent = values[-3:] if len(values) >= 3 else values
    delta  = recent[-1] - recent[0]
    if delta > 0.4:
        return "↑"
    elif delta < -0.4:
        return "↓"
    return "→"


# ══════════════════════════════════════════════════════════════
# TRAINING LOAD — Мониторинг нагрузки (НОВОЕ)
# ══════════════════════════════════════════════════════════════

def calculate_training_load(rpe_values: List[int]) -> Dict:
    """
    Рассчитывает показатели тренировочной нагрузки.

    Метрики:
    - avg_rpe:      средний RPE за период
    - load_trend:   тренд нагрузки (↑/↓/→)
    - monotony:     монотонность нагрузки (std/mean) — чем выше, тем однообразнее
    - strain:       напряжённость (load × monotony)
    - intensity:    категория интенсивности (лёгкая/умеренная/высокая/максимальная)
    """
    if not rpe_values:
        return {
            "avg_rpe":   0,
            "load_trend": "→",
            "monotony":  0,
            "strain":    0,
            "intensity": "нет данных",
        }

    avg_rpe = round(sum(rpe_values) / len(rpe_values), 1)

    # Монотонность нагрузки
    if len(rpe_values) >= 3:
        mean = sum(rpe_values) / len(rpe_values)
        variance = sum((x - mean) ** 2 for x in rpe_values) / len(rpe_values)
        std = variance ** 0.5
        monotony = round(mean / std, 2) if std > 0 else 0
    else:
        monotony = 0

    # Напряжённость
    total_load = sum(rpe_values)
    strain = round(total_load * (monotony if monotony > 0 else 1), 1)

    # Категория интенсивности
    if avg_rpe <= 3:
        intensity = "лёгкая"
    elif avg_rpe <= 5:
        intensity = "умеренная"
    elif avg_rpe <= 7:
        intensity = "высокая"
    else:
        intensity = "максимальная"

    return {
        "avg_rpe":    avg_rpe,
        "load_trend": trend_arrow([float(x) for x in rpe_values]),
        "monotony":   monotony,
        "strain":     strain,
        "intensity":  intensity,
    }


def calculate_acwr(rpe_values: List[int], acute_days: int = 7, chronic_days: int = 28) -> Dict:
    """
    Рассчитывает Acute:Chronic Workload Ratio (ACWR).

    ACWR — ключевая метрика в спортивной науке для предотвращения
    травм и перетренированности.

    Интерпретация:
    - < 0.8  → недотренированность (риск потери формы)
    - 0.8–1.3 → оптимальная зона («sweet spot»)
    - > 1.5  → опасная зона (высокий риск травмы)

    Args:
        rpe_values: список RPE (от новых к старым)
        acute_days: окно острой нагрузки (7 дней)
        chronic_days: окно хронической нагрузки (28 дней)
    """
    if len(rpe_values) < acute_days:
        return {
            "acwr": None,
            "zone": "недостаточно данных",
            "color": "gray",
            "recommendation": "Нужно минимум 7 записей для расчёта ACWR",
        }

    acute_load = sum(rpe_values[:acute_days]) / acute_days
    chronic_values = rpe_values[:chronic_days]
    chronic_load = sum(chronic_values) / len(chronic_values) if chronic_values else 1

    if chronic_load == 0:
        chronic_load = 0.1  # предотвращаем деление на 0

    acwr = round(acute_load / chronic_load, 2)

    # Интерпретация
    if acwr < 0.8:
        zone = "недотренированность"
        color = "blue"
        recommendation = "Нагрузка ниже привычной. Можно увеличить интенсивность."
    elif acwr <= 1.3:
        zone = "оптимальная зона"
        color = "green"
        recommendation = "Идеальное соотношение нагрузки. Продолжайте в том же духе."
    elif acwr <= 1.5:
        zone = "зона внимания"
        color = "orange"
        recommendation = "Нагрузка выше привычной. Следите за восстановлением."
    else:
        zone = "опасная зона"
        color = "red"
        recommendation = "Резкий рост нагрузки! Высокий риск травмы. Рекомендуется снизить интенсивность."

    return {
        "acwr":           acwr,
        "acute_load":     round(acute_load, 1),
        "chronic_load":   round(chronic_load, 1),
        "zone":           zone,
        "color":          color,
        "recommendation": recommendation,
    }


# ══════════════════════════════════════════════════════════════
# RESPONSE QUALITY — Оценка качества ответов агента
# ══════════════════════════════════════════════════════════════

TOOL_KEYWORDS: Dict[str, List[str]] = {
    "generate_training_plan": [
        "день", "упражнени", "подход", "минут", "разминка",
        "отдых", "повторени", "заминка",
    ],
    "analyze_progress": [
        "прогресс", "рекоменда", "слабые", "риск", "следующий",
        "динамик", "сильные",
    ],
    "recovery_recommendation": [
        "восстановлени", "тренировк", "сон", "растяжк",
        "готовность", "гидратац",
    ],
    "nutrition_recommendation": [
        "калори", "белк", "углевод", "питание", "продукт",
        "меню", "гидратац",
    ],
    "analyze_workload": [
        "нагрузк", "rpe", "выполнени", "монотон",
        "прогресси", "корректировк",
    ],
}


def evaluate_response(tool_name: str, response: str) -> Dict:
    """
    Оценивает качество ответа инструмента по ключевым словам.

    Метод: проверка наличия доменных терминов в ответе.
    Чем больше ожидаемых слов найдено — тем полнее ответ.

    Returns:
        {
            'score': процент найденных ключевых слов,
            'found': список найденных слов,
            'missing': список ненайденных слов,
            'word_count': количество слов в ответе,
            'char_count': количество символов,
            'grade': оценка (отлично/хорошо/удовлетворительно/плохо),
        }
    """
    keywords = TOOL_KEYWORDS.get(tool_name, [])
    if not keywords or not response:
        return {
            "score": 0, "found": [], "missing": keywords,
            "word_count": 0, "char_count": 0, "grade": "нет данных",
        }

    resp_lower = response.lower()
    found   = [kw for kw in keywords if kw in resp_lower]
    missing = [kw for kw in keywords if kw not in resp_lower]
    score   = round(len(found) / len(keywords) * 100, 1)

    # Оценка
    if score >= 80:
        grade = "отлично"
    elif score >= 60:
        grade = "хорошо"
    elif score >= 40:
        grade = "удовлетворительно"
    else:
        grade = "плохо"

    return {
        "score":      score,
        "found":      found,
        "missing":    missing,
        "word_count": len(response.split()),
        "char_count": len(response),
        "grade":      grade,
    }


# ══════════════════════════════════════════════════════════════
# DATAFRAME — Данные для визуализации
# ══════════════════════════════════════════════════════════════

def get_sessions_dataframe(athlete_id: int) -> Optional[pd.DataFrame]:
    """Возвращает сессии в виде DataFrame (хронологический порядок)"""
    sessions = get_athlete_sessions(athlete_id, limit=20)
    if len(sessions) < 2:
        return None

    data = list(reversed(sessions))   # от старых к новым
    df = pd.DataFrame(data, columns=["Усталость", "Сон", "Дата", "Боли"])
    df["Самочувствие"] = df.apply(
        lambda r: calculate_wellness_score(r["Усталость"], r["Сон"]),
        axis=1,
    )
    df["Дата"] = pd.to_datetime(df["Дата"])
    return df


def get_training_load_dataframe(athlete_id: int) -> Optional[pd.DataFrame]:
    """
    НОВОЕ: DataFrame для графика нагрузки на основе журнала.
    """
    logs = get_training_logs(athlete_id, limit=28)
    if not logs:
        return None

    rpe_logs = [(l[0], l[1], l[3], l[2]) for l in logs if l[3] and l[3] > 0]
    if len(rpe_logs) < 2:
        return None

    df = pd.DataFrame(
        list(reversed(rpe_logs)),
        columns=["Дата", "Тренировка", "RPE", "Статус"],
    )
    return df


# ══════════════════════════════════════════════════════════════
# СВОДНАЯ АНАЛИТИКА — Агрегация для дашборда
# ══════════════════════════════════════════════════════════════

def get_athlete_summary(athlete_id: int) -> Dict:
    """
    Формирует полную сводку по спортсмену.
    Включает: статистику, тренды, нагрузку, ACWR.
    """
    sessions     = get_athlete_sessions(athlete_id, limit=20)
    agent_stats  = get_agent_stats(athlete_id)
    plans        = get_athlete_plans(athlete_id, limit=10)
    logs         = get_training_logs(athlete_id, limit=28)
    adherence    = get_training_adherence(athlete_id)

    base = {
        "has_data":       False,
        "sessions_count": 0,
        "plans_count":    len(plans),
        "agent_stats":    agent_stats,
        "adherence":      adherence,
    }

    # RPE-данные из журнала
    rpe_values = [l[3] for l in logs if l[3] and l[3] > 0]
    if rpe_values:
        base["training_load"] = calculate_training_load(rpe_values)
        base["acwr"] = calculate_acwr(rpe_values)
    else:
        base["training_load"] = None
        base["acwr"] = None

    if not sessions:
        return base

    fatigues  = [s[0] for s in sessions]
    sleeps    = [s[1] for s in sessions]
    wellness  = [calculate_wellness_score(f, s) for f, s in zip(fatigues, sleeps)]

    # Хронологический порядок для тренда
    f_chron = list(reversed(fatigues))
    s_chron = list(reversed(sleeps))
    w_chron = list(reversed(wellness))

    return {
        **base,
        "has_data":         True,
        "sessions_count":   len(sessions),
        "avg_fatigue":      round(sum(fatigues) / len(fatigues), 1),
        "avg_sleep":        round(sum(sleeps)   / len(sleeps),   1),
        "avg_wellness":     round(sum(wellness)  / len(wellness),  1),
        "latest_fatigue":   fatigues[0],
        "latest_sleep":     sleeps[0],
        "latest_wellness":  wellness[0],
        "fatigue_trend":    trend_arrow(f_chron),
        "sleep_trend":      trend_arrow(s_chron),
        "wellness_trend":   trend_arrow(w_chron),
    }
