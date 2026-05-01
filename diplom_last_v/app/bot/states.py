# ============================================================
# app/bot/states.py — Состояния FSM (aiogram StatesGroup)
# ============================================================
# Используем память в процессе (MemoryStorage) — достаточно для
# учебного проекта. Для продакшна можно поднять Redis-storage.
# ============================================================

from aiogram.fsm.state import State, StatesGroup


class AthleteOnboarding(StatesGroup):
    """Онбординг спортсмена: сбор анкеты."""
    waiting_age = State()
    waiting_sport = State()
    waiting_level = State()
    waiting_goal = State()
    waiting_sessions = State()


class DailyPoll(StatesGroup):
    """Ежедневный опрос: усталость + сон + заметки."""
    waiting_fatigue = State()
    waiting_sleep = State()
    waiting_notes = State()


class TrainingLogFlow(StatesGroup):
    """Добавление записи в журнал тренировок."""
    waiting_name = State()
    waiting_status = State()
    waiting_rpe = State()
    waiting_notes = State()


class PlanQuestionnaire(StatesGroup):
    """Уточняющий вопрос перед составлением тренировочного плана."""
    waiting_weeks = State()


class NutritionQuestionnaire(StatesGroup):
    """Уточняющие вопросы перед составлением плана питания."""
    waiting_weight = State()
    waiting_height = State()
    waiting_restrictions = State()
    waiting_meals = State()


class CoachSettings(StatesGroup):
    """Тренер меняет настройку через чат."""
    # В data передаём, какое именно поле редактируется: field_name.
    waiting_value = State()
