# ============================================================
# tests/test_models.py — Тесты валидации Pydantic-моделей
# ============================================================
import pytest
from pydantic import ValidationError
from models import AthleteProfile, SessionRecord, TrainingLogEntry


# ══════════════════════════════════════════════════════════════
# AthleteProfile
# ══════════════════════════════════════════════════════════════

def test_valid_athlete_profile():
    athlete = AthleteProfile(
        name="Иван Иванов", age=25, sport="Бег",
        level="Любитель", goal="Выносливость", sessions_per_week=3,
    )
    assert athlete.name == "Иван Иванов"
    assert athlete.age  == 25


def test_athlete_name_too_short():
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="А", age=25, sport="Бег", level="Любитель",
            goal="Выносливость", sessions_per_week=3,
        )


def test_athlete_name_strips_whitespace():
    athlete = AthleteProfile(
        name="  Иван  ", age=25, sport="Бег",
        level="Любитель", goal="Выносливость", sessions_per_week=3,
    )
    assert athlete.name == "Иван"


def test_athlete_age_too_young():
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="Малыш", age=5, sport="Бег",
            level="Начинающий", goal="Похудение", sessions_per_week=2,
        )


def test_athlete_age_too_old():
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="Дедушка", age=90, sport="Бег",
            level="Начинающий", goal="Общая физическая форма", sessions_per_week=1,
        )


def test_athlete_sessions_out_of_range_high():
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="Фанатик", age=25, sport="Бег",
            level="Профессионал", goal="Выносливость", sessions_per_week=10,
        )


def test_athlete_sessions_out_of_range_low():
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="Ленивый", age=25, sport="Бег",
            level="Начинающий", goal="Похудение", sessions_per_week=0,
        )


def test_athlete_invalid_sport():
    """НОВОЕ: Невалидный вид спорта"""
    with pytest.raises(ValidationError):
        AthleteProfile(
            name="Тест", age=25, sport="Квиддич",
            level="Любитель", goal="Выносливость", sessions_per_week=3,
        )


def test_athlete_to_dict():
    athlete = AthleteProfile(
        name="Тест", age=30, sport="Бег",
        level="Любитель", goal="Выносливость", sessions_per_week=4,
    )
    d = athlete.to_dict()
    assert isinstance(d, dict)
    assert d["name"]              == "Тест"
    assert d["sessions_per_week"] == 4


# ══════════════════════════════════════════════════════════════
# SessionRecord
# ══════════════════════════════════════════════════════════════

def test_valid_session_record():
    session = SessionRecord(athlete_id=1, fatigue=6, sleep_quality=8)
    assert session.fatigue       == 6
    assert session.sleep_quality == 8
    assert session.results       == ""
    assert session.pain          == ""


def test_session_fatigue_out_of_range():
    with pytest.raises(ValidationError):
        SessionRecord(athlete_id=1, fatigue=11, sleep_quality=7)


def test_session_sleep_out_of_range():
    with pytest.raises(ValidationError):
        SessionRecord(athlete_id=1, fatigue=5, sleep_quality=0)


def test_session_invalid_athlete_id():
    with pytest.raises(ValidationError):
        SessionRecord(athlete_id=0, fatigue=5, sleep_quality=7)


def test_session_optional_fields():
    session = SessionRecord(
        athlete_id=5, fatigue=7, sleep_quality=6,
        results="Бег 5км: 25 мин", pain="Ноют колени",
    )
    assert session.results == "Бег 5км: 25 мин"
    assert session.pain    == "Ноют колени"


# ══════════════════════════════════════════════════════════════
# TrainingLogEntry (НОВОЕ)
# ══════════════════════════════════════════════════════════════

def test_valid_training_log_entry():
    """НОВОЕ: Валидная запись журнала"""
    entry = TrainingLogEntry(
        athlete_id=1, log_date="2025-01-15",
        day_name="Силовая", status="выполнено", rpe=7,
    )
    assert entry.status == "выполнено"
    assert entry.rpe    == 7


def test_training_log_invalid_status():
    """НОВОЕ: Невалидный статус"""
    with pytest.raises(ValidationError):
        TrainingLogEntry(
            athlete_id=1, log_date="2025-01-15",
            day_name="Бег", status="неизвестно", rpe=5,
        )


def test_training_log_rpe_out_of_range():
    """НОВОЕ: RPE вне диапазона"""
    with pytest.raises(ValidationError):
        TrainingLogEntry(
            athlete_id=1, log_date="2025-01-15",
            day_name="Бег", status="выполнено", rpe=15,
        )


def test_training_log_strips_name():
    """НОВОЕ: Название очищается от пробелов"""
    entry = TrainingLogEntry(
        athlete_id=1, log_date="2025-01-15",
        day_name="  Кардио  ", status="выполнено", rpe=5,
    )
    assert entry.day_name == "Кардио"


def test_training_log_short_name_rejected():
    """НОВОЕ: Слишком короткое название"""
    with pytest.raises(ValidationError):
        TrainingLogEntry(
            athlete_id=1, log_date="2025-01-15",
            day_name="А", status="выполнено", rpe=5,
        )
