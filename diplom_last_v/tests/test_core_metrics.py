# ============================================================
# tests/test_core_metrics.py — smoke-тесты чистых функций
# ============================================================
# Проверяем математику из app/core/metrics.py и утилиты
# app/bot/utils.py — без БД и LLM, быстро.
# ============================================================

import pytest

from app.bot.utils import chunk_text, money
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


# =============================================================
#                   Утилиты (app/bot/utils.py)
# =============================================================

def test_chunk_text_short():
    # Короткий текст возвращается как есть
    assert chunk_text("hello") == ["hello"]


def test_chunk_text_splits_long():
    # Текст длиннее лимита должен делиться
    block = "x" * 2000
    long_text = block + "\n\n" + block + "\n\n" + block
    parts = chunk_text(long_text, limit=3800)
    assert len(parts) >= 2
    for p in parts:
        assert len(p) <= 3800


def test_chunk_text_hard_split():
    # Одиночный блок длиннее лимита — режется жёстко
    big_block = "a" * 5000
    parts = chunk_text(big_block, limit=3800)
    assert len(parts) == 2
    assert len(parts[0]) == 3800
    assert len(parts[1]) == 1200


def test_money_rub():
    assert money(100000) == "1 000.00 ₽"


def test_money_usd():
    assert money(499, "USD") == "4.99 USD"
