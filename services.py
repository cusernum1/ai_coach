# ============================================================
# services.py — Сервисный слой (бизнес-логика)
# ============================================================
# Связывает агента, БД, метрики и валидацию в единое API.
# Обеспечивает разделение ответственности:
#   app.py (UI) → services.py (логика) → database.py (данные)
#                                      → agent.py (ИИ)
#                                      → metrics.py (аналитика)
# ============================================================

from typing import Tuple, Dict, Optional, List
from loguru import logger
from pydantic import ValidationError

from models import AthleteProfile, SessionRecord, TrainingLogEntry
from database import (
    save_athlete, get_athlete_stats, save_session,
    save_plan, get_training_logs, get_athlete_state,
    save_training_log, save_nutrition, save_agent_log,
    get_training_adherence, get_agent_logs,
)
from agent import run_agent, TOOL_NAMES_RU
from metrics import (
    calculate_wellness_score, wellness_label,
    evaluate_response, get_athlete_summary,
    calculate_training_load, calculate_acwr,
)


class CoachService:
    """
    Фасад бизнес-логики приложения.

    Все операции проходят через этот класс, что гарантирует:
    - Валидацию данных (Pydantic)
    - Логирование
    - Единообразную обработку ошибок
    - Разделение UI и логики
    """

    # ── Управление профилями ──────────────────────────────────

    @staticmethod
    def register_athlete(data: dict) -> Tuple[int, dict]:
        """
        Валидирует и сохраняет профиль спортсмена.

        Args:
            data: Сырые данные из формы UI

        Returns:
            (athlete_id, validated_dict)

        Raises:
            ValidationError: при невалидных данных
        """
        profile = AthleteProfile(**data)
        athlete_dict = profile.to_dict()
        aid = save_athlete(athlete_dict)
        logger.info(f"Service: registered athlete '{profile.name}' (id={aid})")
        return aid, athlete_dict

    # ── Генерация плана ───────────────────────────────────────

    @staticmethod
    def generate_plan(
        athlete: dict,
        weeks: int,
        focus: str,
        chat_history: list = None,
    ) -> Tuple[str, list, Dict]:
        """
        Генерирует план и оценивает качество ответа.

        Returns:
            (answer, agent_steps, quality_metrics)
        """
        prompt = (
            f"Составь детальный план тренировок на {weeks} недель. "
            f"Акцент: {focus}"
        )
        answer, steps = run_agent(prompt, athlete, chat_history)

        # Оценка качества
        quality = evaluate_response("generate_training_plan", answer)
        logger.info(
            f"Service: plan generated | quality={quality['score']}% "
            f"({quality['grade']})"
        )

        return answer, steps, quality

    # ── Анализ прогресса ──────────────────────────────────────

    @staticmethod
    def analyze_results(
        athlete: dict,
        athlete_id: int,
        results_text: str,
        chat_history: list = None,
    ) -> Tuple[str, list, Dict]:
        """
        Анализирует результаты и сохраняет в БД.

        Returns:
            (answer, agent_steps, quality_metrics)
        """
        # Добавляем контекст из журнала
        logs = get_training_logs(athlete_id, limit=5)
        journal_context = ""
        if logs:
            lines = []
            for l in logs[:5]:
                icon = {"выполнено": "✅", "частично": "⚠️", "пропущено": "❌"}.get(l[2], "❓")
                line = f"{icon} {l[0]}: {l[1]}, {l[2]}"
                if l[3]:
                    line += f", RPE {l[3]}/10"
                lines.append(line)
            journal_context = "\n\nДанные из журнала тренировок:\n" + "\n".join(lines)

        prompt = f"Проанализируй результаты спортсмена:\n{results_text}{journal_context}"
        answer, steps = run_agent(prompt, athlete, chat_history)

        quality = evaluate_response("analyze_progress", answer)
        return answer, steps, quality

    # ── Оценка восстановления ─────────────────────────────────

    @staticmethod
    def evaluate_recovery(
        athlete: dict,
        fatigue: int,
        sleep_quality: int,
        pain: str = "",
        chat_history: list = None,
    ) -> Tuple[str, list, float]:
        """
        Оценивает восстановление и рассчитывает Wellness Score.

        Returns:
            (answer, agent_steps, wellness_score)
        """
        prompt = (
            f"Оцени восстановление. "
            f"Усталость: {fatigue}/10, сон: {sleep_quality}/10, "
            f"жалобы: {pain or 'нет'}"
        )
        answer, steps = run_agent(prompt, athlete, chat_history)
        wellness = calculate_wellness_score(fatigue, sleep_quality)

        return answer, steps, wellness

    # ── Журнал тренировок ─────────────────────────────────────

    @staticmethod
    def log_training(
        athlete_id: int,
        log_date: str,
        day_name: str,
        status: str,
        rpe: int,
        notes: str,
    ) -> bool:
        """
        Валидирует и сохраняет запись в журнал тренировок.

        Returns:
            True при успешном сохранении

        Raises:
            ValidationError: при невалидных данных
        """
        entry = TrainingLogEntry(
            athlete_id=athlete_id,
            log_date=log_date,
            day_name=day_name,
            status=status,
            rpe=rpe if status != "пропущено" else 0,
            notes=notes,
        )
        save_training_log(
            athlete_id=entry.athlete_id,
            log_date=entry.log_date,
            day_name=entry.day_name,
            status=entry.status,
            rpe=entry.rpe,
            notes=entry.notes,
        )
        return True

    # ── Анализ нагрузки ───────────────────────────────────────

    @staticmethod
    def get_workload_analysis(athlete_id: int) -> Dict:
        """
        НОВОЕ: Комплексный анализ тренировочной нагрузки.

        Возвращает:
        - training_load: средний RPE, монотонность, интенсивность
        - acwr: Acute:Chronic Workload Ratio
        - adherence: процент выполнения плана
        """
        logs = get_training_logs(athlete_id, limit=28)
        rpe_values = [l[3] for l in logs if l[3] and l[3] > 0]

        return {
            "training_load": calculate_training_load(rpe_values),
            "acwr":          calculate_acwr(rpe_values),
            "adherence":     get_training_adherence(athlete_id),
            "total_logs":    len(logs),
        }

    # ── Дашборд ───────────────────────────────────────────────

    @staticmethod
    def get_dashboard_data(athlete_id: int) -> Dict:
        """
        Собирает все данные для дашборда.
        Один вызов — вся информация для UI.
        """
        stats     = get_athlete_stats(athlete_id)
        state     = get_athlete_state(athlete_id)
        summary   = get_athlete_summary(athlete_id)
        workload  = CoachService.get_workload_analysis(athlete_id)

        wellness = None
        wellness_emoji = ""
        wellness_label_text = ""
        if stats["sessions_count"] > 0:
            wellness = calculate_wellness_score(
                stats["avg_fatigue"] or 5,
                stats["avg_sleep"] or 7,
            )
            wellness_emoji, wellness_label_text = wellness_label(wellness)

        return {
            "stats":               stats,
            "state":               state,
            "summary":             summary,
            "workload":            workload,
            "wellness":            wellness,
            "wellness_emoji":      wellness_emoji,
            "wellness_label":      wellness_label_text,
        }

    # ── Анализ журнала (через агента) ─────────────────────────

    @staticmethod
    def analyze_training_journal(
        athlete: dict,
        athlete_id: int,
        chat_history: list = None,
    ) -> Tuple[str, list]:
        """
        Формирует сводку журнала и отправляет агенту на анализ.
        """
        logs = get_training_logs(athlete_id, limit=7)
        if not logs:
            return "Нет данных в журнале для анализа.", []

        summary_lines = []
        for l in logs:
            icon = {"выполнено": "✅", "частично": "⚠️", "пропущено": "❌"}.get(l[2], "❓")
            line = f"{icon} {l[0]} — {l[1]}: {l[2]}"
            if l[3]:
                line += f" (RPE {l[3]}/10)"
            if l[4]:
                line += f". {l[4]}"
            summary_lines.append(line)

        summary = "\n".join(summary_lines)
        prompt = (
            f"Проанализируй мой журнал тренировок за последние дни:\n\n"
            f"{summary}\n\n"
            f"Оцени прогресс, выполнение плана, уровень нагрузки по RPE. "
            f"Дай рекомендации на следующую неделю."
        )

        answer, steps = run_agent(prompt, athlete, chat_history)
        return answer, steps
