# ============================================================
# app/core/metrics.py — Чистые формулы спортивных метрик
# ============================================================
# Модуль без зависимостей от БД — только математика.
# Доступ к данным осуществляется на уровне репозиториев,
# а агрегаторы живут в webapp/api.
# ============================================================

from __future__ import annotations

from typing import Iterable


def wellness_score(fatigue: int, sleep: int) -> float:
    """
    Интегральный показатель самочувствия (0–100).
    Формула: (10 - fatigue) × 5 + sleep × 5.
    """
    fatigue = max(1, min(10, int(fatigue)))
    sleep = max(1, min(10, int(sleep)))
    return float((10 - fatigue) * 5 + sleep * 5)


def wellness_label(score: float) -> str:
    """Человеко-читаемая метка (отличное/хорошее/среднее/плохое)."""
    if score >= 70:
        return "🟢 Отличное"
    if score >= 50:
        return "🟡 Хорошее"
    if score >= 30:
        return "🟠 Среднее"
    return "🔴 Плохое"


def training_load(rpe_values: Iterable[int]) -> float:
    """
    Суммарная тренировочная нагрузка по шкале RPE (сумма усилий).
    Foster's sRPE обычно RPE * duration, но в учебной версии
    используем просто сумму RPE-значений за период.
    """
    return float(sum(int(v) for v in rpe_values if v))


def acwr(recent_7: list[int], recent_28: list[int]) -> float | None:
    """
    Acute:Chronic Workload Ratio — коэффициент нагрузки.
    ACWR = среднее за 7 дней / среднее за 28 дней.

    Возвращает None, если данных недостаточно.
    """
    if not recent_7 or not recent_28:
        return None
    avg_7 = sum(recent_7) / len(recent_7)
    avg_28 = sum(recent_28) / len(recent_28)
    if avg_28 == 0:
        return None
    return round(avg_7 / avg_28, 2)


def acwr_zone(value: float | None) -> str:
    """Зоны риска по Gabbett T. (2016)."""
    if value is None:
        return "—"
    if value < 0.8:
        return "Недотренированность"
    if value <= 1.3:
        return "🟢 Оптимальная"
    if value <= 1.5:
        return "🟡 Внимание"
    return "🔴 Высокий риск травмы"


def training_monotony(rpe_values: list[int]) -> float | None:
    """
    Training Monotony (Foster): среднее RPE / стандартное отклонение.
    Высокое значение → монотонная нагрузка → риск перетренированности.
    """
    if len(rpe_values) < 2:
        return None
    mean = sum(rpe_values) / len(rpe_values)
    variance = sum((v - mean) ** 2 for v in rpe_values) / len(rpe_values)
    std = variance ** 0.5
    if std == 0:
        return None
    return round(mean / std, 2)
