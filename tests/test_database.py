# ============================================================
# tests/test_database.py — Юнит-тесты для database.py
# ============================================================
import pytest
import database as db


# ── Фикстура: временная БД ────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Каждый тест получает свою чистую БД"""
    test_db = str(tmp_path / "test_coach.db")
    monkeypatch.setattr(db, "DB_NAME", test_db)
    db.init_db()
    yield test_db


def make_athlete(name: str = "Тест Спортсмен") -> dict:
    return {
        "name":              name,
        "age":               25,
        "sport":             "Бег",
        "level":             "Любитель",
        "goal":              "Выносливость",
        "sessions_per_week": 3,
    }


# ══════════════════════════════════════════════════════════════
# init_db
# ══════════════════════════════════════════════════════════════

def test_init_db_creates_tables(temp_db):
    """Все 6 таблиц должны быть созданы"""
    import sqlite3
    conn = sqlite3.connect(temp_db)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in c.fetchall()}
    conn.close()

    expected = {"athletes", "plans", "sessions", "nutrition_logs", "agent_logs", "training_log"}
    assert expected.issubset(tables), f"Отсутствуют таблицы: {expected - tables}"


# ══════════════════════════════════════════════════════════════
# Athletes CRUD
# ══════════════════════════════════════════════════════════════

def test_save_new_athlete_returns_id():
    athlete = make_athlete()
    aid = db.save_athlete(athlete)
    assert isinstance(aid, int)
    assert aid >= 1


def test_save_athlete_persists_correctly():
    athlete = make_athlete("Иван Иванов")
    db.save_athlete(athlete)
    all_athletes = db.get_all_athletes()
    assert len(all_athletes) == 1
    assert all_athletes[0][1] == "Иван Иванов"
    assert all_athletes[0][2] == 25
    assert all_athletes[0][3] == "Бег"


def test_save_duplicate_athlete_updates_not_inserts():
    """Повторное сохранение должно обновить, не добавить дубликат"""
    athlete = make_athlete("Дубликат")
    id1 = db.save_athlete(athlete)
    athlete["age"] = 30
    id2 = db.save_athlete(athlete)

    assert id1 == id2, "ID должен остаться тем же при UPDATE"
    all_athletes = db.get_all_athletes()
    dupes = [a for a in all_athletes if a[1] == "Дубликат"]
    assert len(dupes) == 1
    assert dupes[0][2] == 30, "Возраст должен обновиться"


def test_get_all_athletes_sorted_by_name():
    for name in ["Яна", "Анна", "Борис"]:
        db.save_athlete(make_athlete(name))
    athletes = db.get_all_athletes()
    names = [a[1] for a in athletes]
    assert names == sorted(names)


def test_delete_athlete_removes_all_data():
    """ИСПРАВЛЕНО: Теперь проверяет и training_log"""
    athlete = make_athlete("Удалить")
    aid = db.save_athlete(athlete)
    db.save_plan(aid, "Тест план", 1)
    db.save_session(aid, "Результаты", 5, 7, "нет", "Анализ")
    db.save_nutrition(aid, "тренировочный", "Цель", "Рекомендации")
    db.save_training_log(aid, "2025-01-01", "Бег", "выполнено", 6, "OK")

    db.delete_athlete(aid)

    assert not db.get_athlete_by_id(aid)
    assert not db.get_athlete_plans(aid)
    assert not db.get_athlete_sessions(aid)
    assert not db.get_athlete_nutrition(aid)
    assert not db.get_training_logs(aid)  # ← НОВАЯ ПРОВЕРКА


def test_get_athlete_by_id_returns_none_for_missing():
    result = db.get_athlete_by_id(99999)
    assert result is None


# ══════════════════════════════════════════════════════════════
# Plans
# ══════════════════════════════════════════════════════════════

def test_save_and_retrieve_plan():
    aid = db.save_athlete(make_athlete())
    db.save_plan(aid, "День 1: бег 5км", 1, "выносливость")
    plans = db.get_athlete_plans(aid)
    assert len(plans) == 1
    assert "бег 5км" in plans[0][0]
    assert plans[0][1] == 1
    assert plans[0][3] == "выносливость"


def test_get_plans_limit():
    aid = db.save_athlete(make_athlete())
    for i in range(7):
        db.save_plan(aid, f"План {i}", 1)
    plans = db.get_athlete_plans(aid, limit=5)
    assert len(plans) <= 5


# ══════════════════════════════════════════════════════════════
# Sessions
# ══════════════════════════════════════════════════════════════

def test_save_and_retrieve_session():
    aid = db.save_athlete(make_athlete())
    db.save_session(aid, "Бег 5км", 6, 8, "нет болей", "Хороший прогресс")
    sessions = db.get_athlete_sessions(aid)
    assert len(sessions) == 1
    assert sessions[0][0] == 6
    assert sessions[0][1] == 8


def test_get_athlete_stats_empty():
    aid = db.save_athlete(make_athlete())
    stats = db.get_athlete_stats(aid)
    assert stats["plans_count"] == 0
    assert stats["sessions_count"] == 0


def test_get_athlete_stats_with_data():
    aid = db.save_athlete(make_athlete())
    db.save_plan(aid, "Тест", 1)
    db.save_session(aid, "", 4, 8, "", "")
    db.save_session(aid, "", 6, 6, "", "")

    stats = db.get_athlete_stats(aid)
    assert stats["plans_count"]    == 1
    assert stats["sessions_count"] == 2
    assert stats["avg_fatigue"]    == 5.0
    assert stats["avg_sleep"]      == 7.0


# ══════════════════════════════════════════════════════════════
# Training Log
# ══════════════════════════════════════════════════════════════

def test_save_and_retrieve_training_log():
    """НОВОЕ: Тест журнала тренировок"""
    aid = db.save_athlete(make_athlete())
    db.save_training_log(aid, "2025-01-01", "Силовая", "выполнено", 7, "Отлично")

    logs = db.get_training_logs(aid)
    assert len(logs) == 1
    assert logs[0][1] == "Силовая"
    assert logs[0][2] == "выполнено"
    assert logs[0][3] == 7


def test_training_adherence():
    """НОВОЕ: Тест расчёта приверженности плану"""
    aid = db.save_athlete(make_athlete())
    db.save_training_log(aid, "2025-01-01", "День 1", "выполнено", 6, "")
    db.save_training_log(aid, "2025-01-02", "День 2", "выполнено", 7, "")
    db.save_training_log(aid, "2025-01-03", "День 3", "частично", 5, "")
    db.save_training_log(aid, "2025-01-04", "День 4", "пропущено", 0, "")

    adherence = db.get_training_adherence(aid)
    assert adherence["total"] == 4
    assert adherence["done"] == 2
    assert adherence["partial"] == 1
    assert adherence["skipped"] == 1
    # (2 + 0.5) / 4 * 100 = 62.5 → 62
    assert adherence["adherence"] == 62


# ══════════════════════════════════════════════════════════════
# Athlete State
# ══════════════════════════════════════════════════════════════

def test_athlete_state_no_plan():
    """НОВОЕ: Состояние нового спортсмена"""
    aid = db.save_athlete(make_athlete())
    state = db.get_athlete_state(aid)
    assert state["state"] == "no_plan"
    assert state["plans_count"] == 0


def test_athlete_state_no_sessions():
    """НОВОЕ: Состояние с планом, но без тренировок"""
    aid = db.save_athlete(make_athlete())
    db.save_plan(aid, "План", 1)
    state = db.get_athlete_state(aid)
    assert state["state"] == "no_sessions"


def test_athlete_state_active():
    """НОВОЕ: Активное состояние"""
    aid = db.save_athlete(make_athlete())
    db.save_plan(aid, "План", 1)
    db.save_training_log(aid, "2025-01-01", "Бег", "выполнено", 6, "OK")
    state = db.get_athlete_state(aid)
    assert state["state"] == "active"
    assert state["has_data"] is True


# ══════════════════════════════════════════════════════════════
# Agent Logs
# ══════════════════════════════════════════════════════════════

def test_save_and_get_agent_stats():
    aid = db.save_athlete(make_athlete())
    db.save_agent_log(aid, "Составь план", "Вот план...", ["generate_training_plan"], 1500.0)
    db.save_agent_log(aid, "Анализируй",  "Анализ...",  ["analyze_progress"],         900.0)

    stats = db.get_agent_stats(aid)
    assert stats["total_queries"] == 2
    assert "generate_training_plan" in stats["tool_counts"]
    assert "analyze_progress"       in stats["tool_counts"]
