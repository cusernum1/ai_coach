# ============================================================
# tests/test_integration.py — Интеграционные тесты
# ============================================================
# Проверяют полный цикл работы системы (без LLM):
# регистрация → план → журнал → анализ → статистика → удаление
# ============================================================
import pytest
import database as db
from metrics import (
    calculate_wellness_score,
    calculate_training_load,
    calculate_acwr,
    get_athlete_summary,
    evaluate_response,
)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_integration.db")
    monkeypatch.setattr(db, "DB_NAME", test_db)
    db.init_db()
    yield test_db


def test_full_athlete_workflow():
    """
    Полный цикл: регистрация → план → журнал → сессии → проверка → удаление.
    Этот тест имитирует реальный сценарий использования приложения.
    """
    # 1. РЕГИСТРАЦИЯ СПОРТСМЕНА
    athlete_data = {
        "name": "Интеграционный Тест",
        "age": 28,
        "sport": "Бег",
        "level": "Любитель",
        "goal": "Выносливость",
        "sessions_per_week": 4,
    }
    aid = db.save_athlete(athlete_data)
    assert aid >= 1

    # Проверяем, что сохранилось
    saved = db.get_athlete_by_id(aid)
    assert saved is not None
    assert saved["name"] == "Интеграционный Тест"
    assert saved["sport"] == "Бег"

    # 2. СОЗДАНИЕ ПЛАНА
    plan_text = "# План на 2 недели\n## Неделя 1\n### День 1 — Бег 5км"
    db.save_plan(aid, plan_text, 2, "выносливость")

    # Состояние: есть план, нет сессий
    state = db.get_athlete_state(aid)
    assert state["state"] == "no_sessions"
    assert state["plans_count"] == 1

    # 3. ЗАПИСЬ ТРЕНИРОВОК В ЖУРНАЛ
    training_data = [
        ("2025-01-06", "Лёгкий бег 5км",    "выполнено", 5, "Ощущения хорошие"),
        ("2025-01-07", "Интервалы 4×400м",   "выполнено", 7, "Тяжело, но справился"),
        ("2025-01-08", "Силовая (ноги)",     "выполнено", 6, "Присед 70кг × 8"),
        ("2025-01-09", "Отдых",              "пропущено", 0, "Активный отдых"),
        ("2025-01-10", "Темповой бег 8км",   "частично",  8, "Пробежал только 6км"),
        ("2025-01-11", "Длинная пробежка",   "выполнено", 7, "12км за 1:05"),
        ("2025-01-12", "Восстановительный",  "выполнено", 3, "Йога 30 мин"),
    ]

    for log_date, day_name, status, rpe, notes in training_data:
        db.save_training_log(aid, log_date, day_name, status, rpe, notes)

    # 4. ЗАПИСЬ СЕССИЙ (физиологические данные)
    sessions_data = [
        ("Бег 5км: 24:30", 4, 8, "нет", "Хороший прогресс"),
        ("Интервалы",       6, 7, "нет", "Нужен отдых"),
        ("Силовая",         5, 8, "колени", "Следить за коленями"),
    ]
    for results, fatigue, sleep, pain, analysis in sessions_data:
        db.save_session(aid, results, fatigue, sleep, pain, analysis)

    # 5. ПРОВЕРЯЕМ СОСТОЯНИЕ → АКТИВНОЕ
    state = db.get_athlete_state(aid)
    assert state["state"] == "active"
    assert state["has_data"] is True
    assert state["logs_count"] == 7

    # 6. ПРОВЕРЯЕМ СТАТИСТИКУ
    stats = db.get_athlete_stats(aid)
    assert stats["plans_count"] == 1
    assert stats["sessions_count"] == 3
    assert stats["avg_fatigue"] == 5.0
    assert stats["avg_sleep"] == pytest.approx(7.7, abs=0.1)

    # 7. ПРОВЕРЯЕМ ПРИВЕРЖЕННОСТЬ ПЛАНУ
    adherence = db.get_training_adherence(aid)
    assert adherence["total"] == 7
    assert adherence["done"] == 5
    assert adherence["partial"] == 1
    assert adherence["skipped"] == 1

    # 8. ПРОВЕРЯЕМ МЕТРИКИ
    logs = db.get_training_logs(aid, limit=28)
    rpe_values = [l[3] for l in logs if l[3] and l[3] > 0]
    assert len(rpe_values) == 6  # один пропущен (RPE=0)

    load = calculate_training_load(rpe_values)
    assert load["avg_rpe"] > 0
    assert load["intensity"] in ("лёгкая", "умеренная", "высокая", "максимальная")

    # 9. СВОДКА
    summary = get_athlete_summary(aid)
    assert summary["has_data"] is True
    assert summary["sessions_count"] == 3
    assert summary["avg_wellness"] > 0
    assert summary["adherence"]["total"] == 7

    # 10. ЛОГИРУЕМ ЗАПРОС АГЕНТА
    db.save_agent_log(aid, "Составь план", "Вот план...", ["generate_training_plan"], 1200.0)
    db.save_agent_log(aid, "Анализируй",  "Анализ...",   ["analyze_progress"],        800.0)
    ag_stats = db.get_agent_stats(aid)
    assert ag_stats["total_queries"] == 2

    # 11. ПОЛНОЕ УДАЛЕНИЕ
    db.delete_athlete(aid)
    assert db.get_athlete_by_id(aid) is None
    assert db.get_athlete_plans(aid) == []
    assert db.get_athlete_sessions(aid) == []
    assert db.get_training_logs(aid) == []


def test_multiple_athletes_isolation():
    """
    Данные разных спортсменов не пересекаются.
    """
    athlete_1 = {"name": "Спортсмен А", "age": 25, "sport": "Бег",
                 "level": "Любитель", "goal": "Выносливость", "sessions_per_week": 3}
    athlete_2 = {"name": "Спортсмен Б", "age": 30, "sport": "Плавание",
                 "level": "Профессионал", "goal": "Похудение", "sessions_per_week": 5}

    aid_1 = db.save_athlete(athlete_1)
    aid_2 = db.save_athlete(athlete_2)

    # Данные для спортсмена А
    db.save_plan(aid_1, "План А", 1)
    db.save_training_log(aid_1, "2025-01-01", "Бег", "выполнено", 6, "")

    # Данные для спортсмена Б
    db.save_plan(aid_2, "План Б", 2)
    db.save_plan(aid_2, "План Б-2", 4)
    db.save_training_log(aid_2, "2025-01-01", "Плавание", "выполнено", 5, "")
    db.save_training_log(aid_2, "2025-01-02", "Плавание", "выполнено", 7, "")

    # Проверяем изоляцию
    assert len(db.get_athlete_plans(aid_1)) == 1
    assert len(db.get_athlete_plans(aid_2)) == 2
    assert len(db.get_training_logs(aid_1)) == 1
    assert len(db.get_training_logs(aid_2)) == 2

    # Удаление одного не затрагивает другого
    db.delete_athlete(aid_1)
    assert db.get_athlete_by_id(aid_1) is None
    assert db.get_athlete_by_id(aid_2) is not None
    assert len(db.get_athlete_plans(aid_2)) == 2


def test_wellness_and_metrics_pipeline():
    """
    Тестирует полный конвейер метрик:
    wellness → load → acwr → evaluate_response
    """
    # Wellness Score
    assert calculate_wellness_score(1, 10) == 95.0
    assert calculate_wellness_score(10, 1) == 5.0

    # Training Load
    rpe = [5, 6, 7, 6, 5, 7, 8, 6, 5, 5, 6, 5, 4, 5]
    load = calculate_training_load(rpe)
    assert 4 <= load["avg_rpe"] <= 8

    # ACWR (нужно >= 7 значений)
    acwr = calculate_acwr(rpe)
    assert acwr["acwr"] is not None
    assert acwr["zone"] != "недостаточно данных"

    # Response Quality
    good_response = (
        "День 1: разминка 10 минут, бег 5км. "
        "Основная часть: 3 подхода приседаний по 10 повторений. "
        "Отдых 2 минуты. Заминка растяжка."
    )
    quality = evaluate_response("generate_training_plan", good_response)
    assert quality["score"] >= 50
    assert quality["grade"] in ("отлично", "хорошо")

    bad_response = "Хорошо, удачи!"
    quality_bad = evaluate_response("generate_training_plan", bad_response)
    assert quality_bad["score"] < quality["score"]
