# ============================================================
# database.py — Слой доступа к данным (SQLite)
# ============================================================
# Все операции с БД проходят через этот модуль.
# Контекстный менеджер гарантирует commit/rollback.
# Миграции добавляют колонки без потери данных.
# ============================================================

import sqlite3
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from loguru import logger
import os

from config import config

DB_NAME = config.DB_NAME

os.makedirs(config.LOG_DIR, exist_ok=True)
logger.add(
    f"{config.LOG_DIR}/db_{{time}}.log",
    rotation=config.LOG_ROTATION,
    retention=config.LOG_RETENTION,
    level=config.LOG_LEVEL,
)


# ── Контекстный менеджер подключения ──────────────────────────

@contextmanager
def get_connection():
    """
    Контекстный менеджер для SQLite.
    Автоматический commit при успехе, rollback при ошибке.
    """
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # включаем FK
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


# ── Миграции ──────────────────────────────────────────────────

def _migrate(conn):
    """Добавляет недостающие колонки в существующие таблицы"""
    c = conn.cursor()

    # athletes → updated_at
    c.execute("PRAGMA table_info(athletes)")
    columns = {row[1] for row in c.fetchall()}
    if "updated_at" not in columns:
        c.execute("ALTER TABLE athletes ADD COLUMN updated_at TEXT")
        c.execute("UPDATE athletes SET updated_at = created_at")
        logger.info("Migration: added updated_at to athletes")

    # plans → focus
    c.execute("PRAGMA table_info(plans)")
    plan_columns = {row[1] for row in c.fetchall()}
    if "focus" not in plan_columns:
        c.execute("ALTER TABLE plans ADD COLUMN focus TEXT DEFAULT 'общая подготовка'")
        logger.info("Migration: added focus to plans")


# ── Инициализация БД ──────────────────────────────────────────

def init_db():
    """Создаёт все таблицы и применяет миграции"""
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS athletes (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL UNIQUE,
                age               INTEGER,
                sport             TEXT,
                level             TEXT,
                goal              TEXT,
                sessions_per_week INTEGER,
                created_at        TEXT,
                updated_at        TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id INTEGER NOT NULL,
                plan_text  TEXT,
                weeks      INTEGER,
                focus      TEXT DEFAULT 'общая подготовка',
                created_at TEXT,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id    INTEGER NOT NULL,
                results       TEXT,
                fatigue       INTEGER,
                sleep_quality INTEGER,
                pain          TEXT,
                analysis      TEXT,
                created_at    TEXT,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS nutrition_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id     INTEGER NOT NULL,
                training_day   TEXT,
                specific_goal  TEXT,
                recommendation TEXT,
                created_at     TEXT,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id   INTEGER NOT NULL,
                user_message TEXT,
                agent_answer TEXT,
                tools_used   TEXT,
                duration_ms  REAL,
                created_at   TEXT,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS training_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                athlete_id  INTEGER NOT NULL,
                plan_id     INTEGER,
                log_date    TEXT,
                day_name    TEXT,
                status      TEXT,
                rpe         INTEGER,
                notes       TEXT,
                created_at  TEXT,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)

        # Индексы для частых запросов
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_plans_athlete
            ON plans(athlete_id, created_at DESC)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_athlete
            ON sessions(athlete_id, created_at DESC)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_log_athlete
            ON training_log(athlete_id, log_date DESC)
        """)

        _migrate(conn)

    logger.info("Database initialized successfully")


# ══════════════════════════════════════════════════════════════
# ATHLETES — CRUD спортсменов
# ══════════════════════════════════════════════════════════════

def save_athlete(athlete: dict) -> int:
    """Сохраняет (INSERT или UPDATE) профиль спортсмена. Возвращает ID."""
    with get_connection() as conn:
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        c.execute("SELECT id FROM athletes WHERE name = ?", (athlete["name"],))
        existing = c.fetchone()

        if existing:
            c.execute("""
                UPDATE athletes
                SET age=?, sport=?, level=?, goal=?, sessions_per_week=?, updated_at=?
                WHERE name=?
            """, (
                athlete["age"], athlete["sport"], athlete["level"],
                athlete["goal"], athlete["sessions_per_week"],
                now, athlete["name"],
            ))
            athlete_id = existing["id"]
            logger.info(f"Updated athlete: {athlete['name']} (id={athlete_id})")
        else:
            c.execute("""
                INSERT INTO athletes
                    (name, age, sport, level, goal, sessions_per_week, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                athlete["name"], athlete["age"], athlete["sport"],
                athlete["level"], athlete["goal"],
                athlete["sessions_per_week"], now, now,
            ))
            athlete_id = c.lastrowid
            logger.info(f"Created athlete: {athlete['name']} (id={athlete_id})")

        return athlete_id


def get_all_athletes() -> list:
    """Возвращает всех спортсменов, отсортированных по имени"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM athletes ORDER BY name")
        return c.fetchall()


def get_athlete_by_id(athlete_id: int) -> Optional[dict]:
    """Возвращает профиль спортсмена по ID или None"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,))
        row = c.fetchone()
        return dict(row) if row else None


def delete_athlete(athlete_id: int) -> bool:
    """
    Удаляет спортсмена и ВСЕ связанные данные.

    ИСПРАВЛЕНО: добавлено удаление training_log
    (ранее записи журнала оставались «сиротами» в БД).
    """
    # Список ВСЕХ таблиц со связью athlete_id
    _DEPENDENT_TABLES = (
        "sessions",
        "plans",
        "nutrition_logs",
        "agent_logs",
        "training_log",      # ← БЫЛО ПРОПУЩЕНО
    )

    with get_connection() as conn:
        c = conn.cursor()
        for table in _DEPENDENT_TABLES:
            c.execute(f"DELETE FROM {table} WHERE athlete_id = ?", (athlete_id,))
        c.execute("DELETE FROM athletes WHERE id = ?", (athlete_id,))
        logger.info(f"Deleted athlete id={athlete_id} and all related data")
        return True


# ══════════════════════════════════════════════════════════════
# PLANS — Тренировочные планы
# ══════════════════════════════════════════════════════════════

def save_plan(athlete_id: int, plan_text: str, weeks: int, focus: str = "общая подготовка"):
    """Сохраняет тренировочный план"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO plans (athlete_id, plan_text, weeks, focus, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (athlete_id, plan_text, weeks, focus, datetime.now().strftime("%Y-%m-%d %H:%M")))
        logger.info(f"Saved plan for athlete_id={athlete_id}, weeks={weeks}, focus={focus}")


def get_athlete_plans(athlete_id: int, limit: int = 5) -> list:
    """Возвращает последние планы спортсмена"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT plan_text, weeks, created_at, focus
            FROM plans WHERE athlete_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (athlete_id, limit))
        return c.fetchall()


# ══════════════════════════════════════════════════════════════
# SESSIONS — Записи тренировочных сессий
# ══════════════════════════════════════════════════════════════

def save_session(athlete_id: int, results: str, fatigue: int,
                 sleep_quality: int, pain: str, analysis: str):
    """Сохраняет результаты и анализ тренировочной сессии"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO sessions
                (athlete_id, results, fatigue, sleep_quality, pain, analysis, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            athlete_id, results, fatigue, sleep_quality, pain, analysis,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))


def get_athlete_sessions(athlete_id: int, limit: int = 20) -> list:
    """Возвращает последние сессии (для графиков и анализа)"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT fatigue, sleep_quality, created_at, pain
            FROM sessions WHERE athlete_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (athlete_id, limit))
        return c.fetchall()


# ══════════════════════════════════════════════════════════════
# NUTRITION — Рекомендации по питанию
# ══════════════════════════════════════════════════════════════

def save_nutrition(athlete_id: int, training_day: str, specific_goal: str, recommendation: str):
    """Сохраняет рекомендацию по питанию"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO nutrition_logs
                (athlete_id, training_day, specific_goal, recommendation, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            athlete_id, training_day, specific_goal, recommendation,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))


def get_athlete_nutrition(athlete_id: int, limit: int = 5) -> list:
    """Возвращает последние рекомендации по питанию"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT recommendation, training_day, created_at
            FROM nutrition_logs WHERE athlete_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (athlete_id, limit))
        return c.fetchall()


# ══════════════════════════════════════════════════════════════
# AGENT LOGS — Логи агента
# ══════════════════════════════════════════════════════════════

def save_agent_log(athlete_id: int, user_message: str, answer: str,
                   tools_used: list, duration_ms: float):
    """Сохраняет запрос и ответ агента для аналитики"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO agent_logs
                (athlete_id, user_message, agent_answer, tools_used, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            athlete_id, user_message, answer,
            ",".join(tools_used), duration_ms,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))


def get_agent_stats(athlete_id: int) -> dict:
    """Статистика использования агента: запросы, время, инструменты"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) AS total, ROUND(AVG(duration_ms), 0) AS avg_dur
            FROM agent_logs WHERE athlete_id = ?
        """, (athlete_id,))
        row = c.fetchone()

        c.execute("""
            SELECT tools_used FROM agent_logs
            WHERE athlete_id = ? AND tools_used != ''
        """, (athlete_id,))
        rows = c.fetchall()

    tool_counts: dict = {}
    for r in rows:
        if r["tools_used"]:
            for t in r["tools_used"].split(","):
                t = t.strip()
                if t:
                    tool_counts[t] = tool_counts.get(t, 0) + 1

    return {
        "total_queries":   row["total"] if row else 0,
        "avg_duration_ms": row["avg_dur"] if row else 0,
        "tool_counts":     tool_counts,
    }


def get_agent_logs(athlete_id: int, limit: int = 20) -> list:
    """Возвращает историю запросов к агенту"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_message, agent_answer, tools_used, duration_ms, created_at
            FROM agent_logs WHERE athlete_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (athlete_id, limit))
        return c.fetchall()


# ══════════════════════════════════════════════════════════════
# TRAINING LOG — Журнал выполнения тренировок
# ══════════════════════════════════════════════════════════════

def save_training_log(
    athlete_id: int,
    log_date: str,
    day_name: str,
    status: str,
    rpe: int,
    notes: str,
    plan_id: int = None,
):
    """Сохраняет запись о выполнении тренировки"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO training_log
                (athlete_id, plan_id, log_date, day_name, status, rpe, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            athlete_id, plan_id, log_date, day_name, status, rpe, notes,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ))
    logger.info(f"Saved training log: athlete_id={athlete_id}, date={log_date}, status={status}")


def get_training_logs(athlete_id: int, limit: int = 14) -> list:
    """Возвращает последние записи журнала тренировок"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT log_date, day_name, status, rpe, notes, created_at
            FROM training_log WHERE athlete_id = ?
            ORDER BY log_date DESC LIMIT ?
        """, (athlete_id, limit))
        return c.fetchall()


# ══════════════════════════════════════════════════════════════
# ATHLETE STATE — Состояние для умной логики UI
# ══════════════════════════════════════════════════════════════

def get_athlete_state(athlete_id: int) -> dict:
    """
    Возвращает текущее состояние спортсмена для UI.

    Состояния:
      no_plan     — нет ни одного плана
      no_sessions — есть план, но нет записей тренировок
      active      — есть план и есть записи
    """
    with get_connection() as conn:
        c = conn.cursor()

        c.execute(
            "SELECT COUNT(*) as cnt FROM plans WHERE athlete_id = ?",
            (athlete_id,),
        )
        plans_count = c.fetchone()["cnt"]

        c.execute(
            "SELECT COUNT(*) as cnt FROM training_log WHERE athlete_id = ?",
            (athlete_id,),
        )
        logs_count = c.fetchone()["cnt"]

        c.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE athlete_id = ?",
            (athlete_id,),
        )
        sessions_count = c.fetchone()["cnt"]

        c.execute("""
            SELECT id, weeks, focus, created_at FROM plans
            WHERE athlete_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (athlete_id,))
        last_plan = c.fetchone()

    has_any_data = logs_count > 0 or sessions_count > 0

    if plans_count == 0:
        state = "no_plan"
    elif not has_any_data:
        state = "no_sessions"
    else:
        state = "active"

    return {
        "state":          state,
        "plans_count":    plans_count,
        "logs_count":     logs_count,
        "sessions_count": sessions_count,
        "has_data":       has_any_data,
        "last_plan":      dict(last_plan) if last_plan else None,
    }


# ══════════════════════════════════════════════════════════════
# СТАТИСТИКА — Расширенная статистика спортсмена
# ══════════════════════════════════════════════════════════════

def get_athlete_stats(athlete_id: int) -> dict:
    """Базовая статистика: количество планов, сессий, средние показатели"""
    with get_connection() as conn:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) as cnt FROM plans WHERE athlete_id = ?", (athlete_id,))
        plans_count = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) as cnt FROM sessions WHERE athlete_id = ?", (athlete_id,))
        sessions_count = c.fetchone()["cnt"]

        c.execute("""
            SELECT
                ROUND(AVG(fatigue), 1)       AS avg_fatigue,
                ROUND(AVG(sleep_quality), 1) AS avg_sleep
            FROM sessions WHERE athlete_id = ?
        """, (athlete_id,))
        row = c.fetchone()

        return {
            "plans_count":    plans_count,
            "sessions_count": sessions_count,
            "avg_fatigue":    row["avg_fatigue"] or 0,
            "avg_sleep":      row["avg_sleep"] or 0,
        }


def get_training_adherence(athlete_id: int, days: int = 14) -> dict:
    """
    Рассчитывает процент выполнения плана за последние N дней.
    НОВОЕ: важная метрика для диплома.
    """
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT status, COUNT(*) as cnt
            FROM training_log
            WHERE athlete_id = ?
            GROUP BY status
            ORDER BY cnt DESC
        """, (athlete_id,))
        rows = c.fetchall()

    counts = {r["status"]: r["cnt"] for r in rows}
    total = sum(counts.values())

    if total == 0:
        return {"adherence": 0, "total": 0, "done": 0, "partial": 0, "skipped": 0}

    done = counts.get("выполнено", 0)
    partial = counts.get("частично", 0)
    skipped = counts.get("пропущено", 0)
    adherence = round((done + partial * 0.5) / total * 100)

    return {
        "adherence": adherence,
        "total":     total,
        "done":      done,
        "partial":   partial,
        "skipped":   skipped,
    }
