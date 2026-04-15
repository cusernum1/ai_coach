# ============================================================
# pdf_export.py — Экспорт данных в PDF и TXT
# ============================================================
# Поддерживает:
# - Экспорт тренировочного плана (PDF + TXT)
# - Полный отчёт по спортсмену (НОВОЕ)
# - Кириллическая типографика через DejaVuSans
# ============================================================

import os
import traceback
from datetime import datetime
from typing import Optional
from loguru import logger

from config import config

# Хранение последней ошибки для отображения в UI
_last_pdf_error: Optional[str] = None


def get_last_pdf_error() -> Optional[str]:
    """Возвращает текст последней ошибки генерации PDF (для UI)."""
    return _last_pdf_error


# ── Helpers для безопасного вывода текста ─────────────────────

def _safe_multi_cell(pdf, h: float, text: str) -> None:
    """
    Безопасный вывод параграфа через multi_cell.

    Исправляет баг fpdf2: в новых версиях multi_cell не переводит
    курсор в начало следующей строки после отрисовки, и следующий
    вызов multi_cell(0, ...) пытается рисовать от текущего X,
    где места может уже не остаться. Решение:
      1. Явно сбрасываем X на левый margin перед каждым вызовом
      2. Передаём явную ширину (не 0), чтобы использовать
         всю доступную ширину страницы
      3. Используем wrapmode="CHAR" для переноса по символам
         (справляется с длинными словами без пробелов)
      4. Fallback: если всё ещё падает — режем текст на куски
    """
    if not text:
        return

    # Доступная ширина = ширина страницы минус margins
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_x(pdf.l_margin)

    try:
        pdf.multi_cell(usable_width, h, text, wrapmode="CHAR")
    except Exception:
        # Крайний случай: режем на куски и пытаемся отрисовать каждый
        try:
            chunk_size = 60
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                pdf.set_x(pdf.l_margin)
                try:
                    pdf.multi_cell(usable_width, h, chunk, wrapmode="CHAR")
                except Exception:
                    # Совсем крайний случай — ascii only
                    safe = chunk.encode("ascii", "ignore").decode("ascii") or " "
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(usable_width, h, safe, wrapmode="CHAR")
        except Exception as e:
            logger.warning(f"_safe_multi_cell fallback failed: {e}")


def export_to_txt(athlete: dict, content: str, title: str = "Отчёт") -> str:
    """Форматирует и возвращает текстовый экспорт"""
    sep = "=" * 65
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    header = (
        f"\n{sep}\n"
        f"{title.upper():^65}\n"
        f"{sep}\n"
        f"Спортсмен : {athlete.get('name', '—')}\n"
        f"Возраст   : {athlete.get('age', '—')} лет\n"
        f"Вид спорта: {athlete.get('sport', '—')}\n"
        f"Уровень   : {athlete.get('level', '—')}\n"
        f"Цель      : {athlete.get('goal', '—')}\n"
        f"Создано   : {now}\n"
        f"{sep}\n\n"
    )
    return header + content


def export_full_report_txt(athlete: dict, athlete_id: int) -> str:
    """
    НОВОЕ: Полный текстовый отчёт по спортсмену.
    Включает: профиль, планы, журнал, статистику, метрики.
    """
    from database import get_athlete_plans, get_training_logs, get_athlete_stats
    from metrics import get_athlete_summary, calculate_training_load, calculate_acwr

    sep = "=" * 65
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    summary = get_athlete_summary(athlete_id)
    stats = get_athlete_stats(athlete_id)

    report = f"\n{sep}\n{'ПОЛНЫЙ ОТЧЁТ СПОРТСМЕНА':^65}\n{sep}\n"
    report += f"Дата создания: {now}\n{sep}\n\n"

    # ── Профиль ───────────────────────────────────────────────
    report += "ПРОФИЛЬ СПОРТСМЕНА\n" + "-" * 40 + "\n"
    report += f"  Имя:              {athlete.get('name', '—')}\n"
    report += f"  Возраст:          {athlete.get('age', '—')} лет\n"
    report += f"  Вид спорта:       {athlete.get('sport', '—')}\n"
    report += f"  Уровень:          {athlete.get('level', '—')}\n"
    report += f"  Цель:             {athlete.get('goal', '—')}\n"
    report += f"  Тренировок/нед.:  {athlete.get('sessions_per_week', '—')}\n\n"

    # ── Статистика ────────────────────────────────────────────
    report += "СТАТИСТИКА\n" + "-" * 40 + "\n"
    report += f"  Планов создано:   {stats['plans_count']}\n"
    report += f"  Сессий записано:  {stats['sessions_count']}\n"

    if summary.get("has_data"):
        report += f"  Средняя усталость: {summary['avg_fatigue']} {summary.get('fatigue_trend', '')}\n"
        report += f"  Средний сон:       {summary['avg_sleep']} {summary.get('sleep_trend', '')}\n"
        report += f"  Самочувствие:      {summary.get('avg_wellness', '—')}/100\n"

    # ── Нагрузка ──────────────────────────────────────────────
    logs = get_training_logs(athlete_id, limit=28)
    rpe_values = [l[3] for l in logs if l[3] and l[3] > 0]

    if rpe_values:
        report += "\nТРЕНИРОВОЧНАЯ НАГРУЗКА\n" + "-" * 40 + "\n"
        load = calculate_training_load(rpe_values)
        report += f"  Средний RPE:      {load['avg_rpe']}\n"
        report += f"  Интенсивность:    {load['intensity']}\n"
        report += f"  Тренд нагрузки:   {load['load_trend']}\n"

        acwr = calculate_acwr(rpe_values)
        if acwr.get("acwr"):
            report += f"  ACWR:             {acwr['acwr']} ({acwr['zone']})\n"
            report += f"  Рекомендация:     {acwr['recommendation']}\n"

    # ── Журнал ────────────────────────────────────────────────
    if logs:
        report += f"\nЖУРНАЛ ТРЕНИРОВОК (последние {min(len(logs), 14)} записей)\n"
        report += "-" * 40 + "\n"
        for l in logs[:14]:
            status_icon = {"выполнено": "[+]", "частично": "[~]", "пропущено": "[-]"}.get(l[2], "[?]")
            rpe_str = f" | RPE {l[3]}/10" if l[3] else ""
            report += f"  {l[0]} {status_icon} {l[1]}{rpe_str}\n"
            if l[4]:
                report += f"           {l[4][:60]}\n"

    # ── Планы ─────────────────────────────────────────────────
    plans = get_athlete_plans(athlete_id, limit=3)
    if plans:
        report += f"\nПОСЛЕДНИЕ ПЛАНЫ\n" + "-" * 40 + "\n"
        for plan in plans:
            report += f"\n--- {plan[2]} | {plan[1]} нед. | {plan[3]} ---\n"
            report += plan[0][:500]
            if len(plan[0]) > 500:
                report += "\n... (сокращено)"
            report += "\n"

    report += f"\n{sep}\n"
    report += f"Создано системой «ИИ-агент спортивного тренера» v{config.APP_VERSION}\n"
    report += f"{sep}\n"

    return report


def export_to_pdf(
    athlete: dict,
    plan_text: str,
    weeks: int,
    focus: str = "",
) -> Optional[bytes]:
    """
    Экспортирует план в PDF с поддержкой кириллицы.

    Требуется: fonts/DejaVuSans.ttf и fonts/DejaVuSans-Bold.ttf
    Скачать: https://dejavu-fonts.github.io/

    Returns:
        bytes: PDF-файл или None при ошибке.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        logger.error("fpdf2 не установлен. Запустите: pip install fpdf2")
        return None

    # Проверка шрифта ДО создания PDF
    has_custom_font = os.path.exists(config.FONT_REGULAR)
    if not has_custom_font:
        logger.warning(
            "Шрифт DejaVuSans.ttf не найден в папке fonts/. "
            "Кириллица может отображаться некорректно. "
            "Запустите: python download_fonts.py"
        )

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # ── Шрифты ────────────────────────────────────────────
        if has_custom_font:
            pdf.add_font("DejaVu", "",  config.FONT_REGULAR)
            bold_path = (
                config.FONT_BOLD
                if os.path.exists(config.FONT_BOLD)
                else config.FONT_REGULAR
            )
            pdf.add_font("DejaVu", "B", bold_path)
            fn = "DejaVu"
        else:
            fn = "Helvetica"

        now_str = datetime.now().strftime("%d.%m.%Y")

        # ── Заголовок ─────────────────────────────────────────
        pdf.set_fill_color(30, 60, 114)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(fn, "B", 18)
        pdf.cell(0, 14, "Тренировочный план", ln=True, align="C", fill=True)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font(fn, "", 11)
        sub = f"{weeks} нед."
        if focus:
            sub += f"  |  Акцент: {focus}"
        pdf.cell(0, 8, sub, ln=True, align="C")
        pdf.ln(4)

        # ── Профиль спортсмена ────────────────────────────────
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font(fn, "B", 12)
        pdf.cell(0, 8, "Профиль спортсмена", ln=True, fill=True)
        pdf.set_font(fn, "", 10)
        info = [
            f"Имя: {athlete.get('name', '—')}",
            f"Возраст: {athlete.get('age', '—')} лет   |   Вид спорта: {athlete.get('sport', '—')}",
            f"Уровень: {athlete.get('level', '—')}   |   Цель: {athlete.get('goal', '—')}",
            f"Тренировок в неделю: {athlete.get('sessions_per_week', '—')}",
        ]
        for line in info:
            pdf.cell(0, 6, line, ln=True)
        pdf.ln(3)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

        # ── Текст плана ───────────────────────────────────────
        clean = plan_text.replace("**", "").replace("*", "")

        for line in clean.split("\n"):
            line = line.rstrip()
            if not line:
                pdf.ln(2)
                continue

            if line.startswith("# "):
                pdf.set_font(fn, "B", 14)
                _safe_multi_cell(pdf, 8, line[2:])
                pdf.set_font(fn, "", 10)
            elif line.startswith("## "):
                pdf.set_font(fn, "B", 12)
                pdf.ln(2)
                _safe_multi_cell(pdf, 7, line[3:])
                pdf.set_font(fn, "", 10)
            elif line.startswith("### "):
                pdf.set_font(fn, "B", 11)
                _safe_multi_cell(pdf, 6, line[4:])
                pdf.set_font(fn, "", 10)
            else:
                _safe_multi_cell(pdf, 5, line)

        # ── Footer ────────────────────────────────────────────
        pdf.set_y(-18)
        pdf.set_font(fn, "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0, 5,
            f"Создано: {now_str} | ИИ-агент спортивного тренера v{config.APP_VERSION}",
            ln=True, align="C",
        )

        result = bytes(pdf.output())
        logger.info(f"PDF exported for {athlete.get('name')}")
        return result

    except Exception as e:
        global _last_pdf_error
        _last_pdf_error = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        logger.exception(f"PDF export error: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# ПОЛНЫЙ ОТЧЁТ В PDF (НОВОЕ)
# ══════════════════════════════════════════════════════════════

def export_full_report_pdf(athlete: dict, athlete_id: int) -> Optional[bytes]:
    """
    Полный отчёт по спортсмену в PDF.

    Включает: профиль, статистику, нагрузку, ACWR, журнал, планы.
    Использует те же шрифты DejaVu, что и export_to_pdf.

    Returns:
        bytes: PDF-файл или None при ошибке.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        logger.error("fpdf2 не установлен")
        return None

    # Импорты внутри функции, чтобы избежать циклических зависимостей
    from database import get_athlete_plans, get_training_logs, get_athlete_stats
    from metrics import (
        get_athlete_summary,
        calculate_training_load,
        calculate_acwr,
    )

    has_custom_font = os.path.exists(config.FONT_REGULAR)
    if not has_custom_font:
        logger.warning("Шрифт DejaVuSans.ttf не найден — кириллица может не отобразиться")

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # ── Шрифты ────────────────────────────────────────────
        if has_custom_font:
            pdf.add_font("DejaVu", "", config.FONT_REGULAR)
            bold_path = (
                config.FONT_BOLD
                if os.path.exists(config.FONT_BOLD)
                else config.FONT_REGULAR
            )
            pdf.add_font("DejaVu", "B", bold_path)
            fn = "DejaVu"
        else:
            fn = "Helvetica"

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        summary = get_athlete_summary(athlete_id)
        stats   = get_athlete_stats(athlete_id)

        # ── Заголовок ─────────────────────────────────────────
        pdf.set_fill_color(30, 60, 114)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(fn, "B", 18)
        pdf.cell(0, 14, "Полный отчёт спортсмена", ln=True, align="C", fill=True)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font(fn, "", 10)
        pdf.cell(0, 6, f"Дата создания: {now_str}", ln=True, align="C")
        pdf.ln(4)

        # ── 1. Профиль ────────────────────────────────────────
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font(fn, "B", 12)
        pdf.cell(0, 8, "1. Профиль спортсмена", ln=True, fill=True)
        pdf.set_font(fn, "", 10)
        pdf.cell(0, 6, f"Имя: {athlete.get('name', '—')}", ln=True)
        pdf.cell(0, 6, f"Возраст: {athlete.get('age', '—')} лет   |   Вид спорта: {athlete.get('sport', '—')}", ln=True)
        pdf.cell(0, 6, f"Уровень: {athlete.get('level', '—')}   |   Цель: {athlete.get('goal', '—')}", ln=True)
        pdf.cell(0, 6, f"Тренировок в неделю: {athlete.get('sessions_per_week', '—')}", ln=True)
        pdf.ln(4)

        # ── 2. Статистика ─────────────────────────────────────
        pdf.set_font(fn, "B", 12)
        pdf.cell(0, 8, "2. Общая статистика", ln=True, fill=True)
        pdf.set_font(fn, "", 10)
        pdf.cell(0, 6, f"Планов создано: {stats['plans_count']}", ln=True)
        pdf.cell(0, 6, f"Сессий записано: {stats['sessions_count']}", ln=True)

        if summary.get("has_data"):
            pdf.cell(0, 6,
                f"Средняя усталость: {summary['avg_fatigue']} {summary.get('fatigue_trend', '')}",
                ln=True)
            pdf.cell(0, 6,
                f"Средний сон: {summary['avg_sleep']} {summary.get('sleep_trend', '')}",
                ln=True)
            pdf.cell(0, 6,
                f"Самочувствие (Wellness Score): {summary.get('avg_wellness', '—')}/100",
                ln=True)
        pdf.ln(4)

        # ── 3. Тренировочная нагрузка ─────────────────────────
        logs = get_training_logs(athlete_id, limit=28)
        rpe_values = [l[3] for l in logs if l[3] and l[3] > 0]

        if rpe_values:
            pdf.set_font(fn, "B", 12)
            pdf.cell(0, 8, "3. Тренировочная нагрузка", ln=True, fill=True)
            pdf.set_font(fn, "", 10)

            load = calculate_training_load(rpe_values)
            pdf.cell(0, 6, f"Средний RPE: {load['avg_rpe']}/10", ln=True)
            pdf.cell(0, 6, f"Категория интенсивности: {load['intensity']}", ln=True)
            pdf.cell(0, 6, f"Монотонность нагрузки: {load['monotony']}", ln=True)
            pdf.cell(0, 6, f"Общая напряжённость (strain): {load['strain']}", ln=True)

            acwr = calculate_acwr(rpe_values)
            if acwr.get("acwr") is not None:
                pdf.ln(2)
                pdf.set_font(fn, "B", 10)
                pdf.cell(0, 6, f"ACWR (Acute:Chronic Workload Ratio):", ln=True)
                pdf.set_font(fn, "", 10)
                pdf.cell(0, 6, f"  • Значение: {acwr['acwr']}", ln=True)
                pdf.cell(0, 6, f"  • Зона: {acwr['zone']}", ln=True)
                pdf.cell(0, 6, f"  • Острая нагрузка (7 дн): {acwr['acute_load']}", ln=True)
                pdf.cell(0, 6, f"  • Хроническая нагрузка (28 дн): {acwr['chronic_load']}", ln=True)
                _safe_multi_cell(pdf, 6, f"  • Рекомендация: {acwr['recommendation']}")
            pdf.ln(4)

        # ── 4. Выполнение плана ───────────────────────────────
        adherence = summary.get("adherence", {})
        if adherence.get("total", 0) > 0:
            pdf.set_font(fn, "B", 12)
            pdf.cell(0, 8, "4. Выполнение плана", ln=True, fill=True)
            pdf.set_font(fn, "", 10)
            pdf.cell(0, 6, f"Всего записей: {adherence['total']}", ln=True)
            pdf.cell(0, 6, f"Выполнено: {adherence['done']}", ln=True)
            pdf.cell(0, 6, f"Частично: {adherence['partial']}", ln=True)
            pdf.cell(0, 6, f"Пропущено: {adherence['skipped']}", ln=True)
            pdf.set_font(fn, "B", 10)
            pdf.cell(0, 6, f"Процент приверженности плану: {adherence['adherence']}%", ln=True)
            pdf.ln(4)

        # ── 5. Журнал тренировок ──────────────────────────────
        if logs:
            # Проверяем место на странице
            if pdf.get_y() > 230:
                pdf.add_page()

            pdf.set_font(fn, "B", 12)
            pdf.cell(0, 8, f"5. Журнал тренировок (последние {min(len(logs), 14)})", ln=True, fill=True)
            pdf.set_font(fn, "", 9)

            for l in logs[:14]:
                log_date_str, day_n, log_status, log_rpe, log_notes, _ = l
                status_map = {
                    "выполнено": "[+]",
                    "частично":  "[~]",
                    "пропущено": "[-]",
                }
                icon = status_map.get(log_status, "[?]")
                rpe_str = f" | RPE {log_rpe}/10" if log_rpe and log_rpe > 0 else ""

                try:
                    pdf.set_font(fn, "B", 9)
                    pdf.cell(0, 5, f"{log_date_str} {icon} {day_n}{rpe_str}", ln=True)
                    if log_notes:
                        pdf.set_font(fn, "", 8)
                        notes_short = log_notes[:120] + "..." if len(log_notes) > 120 else log_notes
                        _safe_multi_cell(pdf, 4, f"   {notes_short}")
                    pdf.ln(1)
                except Exception:
                    continue
            pdf.ln(3)

        # ── 6. Последние планы (заголовки) ────────────────────
        plans = get_athlete_plans(athlete_id, limit=3)
        if plans:
            if pdf.get_y() > 240:
                pdf.add_page()

            pdf.set_font(fn, "B", 12)
            pdf.cell(0, 8, "6. Последние планы", ln=True, fill=True)
            pdf.set_font(fn, "", 9)

            for plan in plans:
                plan_text, p_weeks, p_date, p_focus = plan
                pdf.set_font(fn, "B", 10)
                pdf.cell(0, 6, f"• {p_date} — {p_weeks} нед. | акцент: {p_focus}", ln=True)
                pdf.set_font(fn, "", 8)
                # Превью первых ~200 символов
                preview = plan_text.replace("**", "").replace("*", "")[:250]
                try:
                    _safe_multi_cell(pdf, 4, f"   {preview}...")
                except Exception:
                    pass
                pdf.ln(2)

        # ── Footer ────────────────────────────────────────────
        pdf.set_y(-15)
        pdf.set_font(fn, "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0, 5,
            f"ИИ-агент спортивного тренера v{config.APP_VERSION} | {now_str}",
            ln=True, align="C",
        )

        result = bytes(pdf.output())
        logger.info(f"Full report PDF generated for {athlete.get('name')}")
        return result

    except Exception as e:
        global _last_pdf_error
        _last_pdf_error = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        logger.exception(f"Full report PDF error: {e}")
        return None