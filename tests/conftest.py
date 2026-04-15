# ============================================================
# tests/conftest.py — Общие фикстуры для всех тестов
# ============================================================
import sys
import os
import pytest

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db


@pytest.fixture
def sample_athlete() -> dict:
    """Стандартный профиль для тестов"""
    return {
        "name":              "Тест Атлет",
        "age":               25,
        "sport":             "Бег",
        "level":             "Любитель",
        "goal":              "Выносливость",
        "sessions_per_week": 3,
    }


@pytest.fixture(autouse=False)
def temp_db(tmp_path, monkeypatch):
    """Временная БД для тестов, требующих базу данных"""
    test_db = str(tmp_path / "test_coach.db")
    monkeypatch.setattr(db, "DB_NAME", test_db)
    db.init_db()
    yield test_db
