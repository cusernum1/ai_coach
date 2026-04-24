# ============================================================
# tests/test_core_metrics.py — smoke-тесты чистых формул
# ============================================================
# Проверяем только математику из app/core/metrics.py —
# без БД и LLM, быстро.
# ============================================================

import pytest

from app.core.metrics import (
    acwr,
    acwr_zone,
    training_load,
    training_monotony,
    wellness_label,
    wellness_score,
)


def test_wellness_score_bounds():
    assert wellness_score(1, 10) == 95
    assert wellness_score(10, 1) == 5
    # out-of-range clipping
    assert wellness_score(-5, 20) == 95


def test_wellness_label_ranges():
    assert wellness_label(90).startswith("🟢")
    assert wellness_label(60).startswith("🟡")
    assert wellness_label(40).startswith("🟠")
    assert wellness_label(10).startswith("🔴")


def test_training_load_sums_rpe():
    assert training_load([5, 6, 7]) == 18
    assert training_load([0, 0]) == 0


def test_acwr_math():
    # Оптимальная зона: равная нагрузка = 1.0
    assert acwr([5, 5, 5, 5, 5, 5, 5], [5] * 28) == 1.0
    # Скачок вверх: 10 vs 5 → 2.0 (риск)
    assert acwr([10] * 7, [5] * 28) == 2.0
    # Недостаточно данных
    assert acwr([], [5]) is None


def test_acwr_zone_labels():
    assert acwr_zone(None) == "—"
    assert "Недотренированность" in acwr_zone(0.5)
    assert "Оптимальная" in acwr_zone(1.1)
    assert "Внимание" in acwr_zone(1.4)
    assert "Высокий" in acwr_zone(1.8)


def test_training_monotony():
    # Полностью монотонная нагрузка — std=0 → None
    assert training_monotony([5, 5, 5, 5]) is None
    # Разная — возвращает число
    value = training_monotony([5, 7, 3, 6])
    assert value is not None and value > 0
