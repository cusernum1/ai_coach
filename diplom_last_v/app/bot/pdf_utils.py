# ============================================================
# app/bot/pdf_utils.py — Генерация PDF из текста плана/питания
# ============================================================
# Использует fpdf2 + DejaVuSans (поддержка кириллицы).
# Если шрифт не найден — возвращает None, хэндлер шлёт текст.
# ============================================================

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fpdf import FPDF
from loguru import logger

# Ищем шрифты: сначала в папке проекта, потом в системе
_BASE = Path(__file__).resolve().parents[2]  # diplom_last_v/

FONT_REGULAR = str(_BASE / "fonts" / "DejaVuSans.ttf")
FONT_BOLD    = str(_BASE / "fonts" / "DejaVuSans-Bold.ttf")

_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _resolve_font(path: str, fallbacks: list[str]) -> Optional[str]:
    if Path(path).exists():
        return path
    for fb in fallbacks:
        if Path(fb).exists():
            return fb
    return None


def _parse_lines(content: str) -> list[tuple[str, str]]:
    """
    Разбирает текст на строки с тегом форматирования:
      'h1' / 'h2' / 'h3' / 'bold' / 'normal' / 'empty'
    Возвращает список (tag, text).
    """
    result: list[tuple[str, str]] = []
    for raw in content.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            result.append(("empty", ""))
            continue
        if line.startswith("### "):
            result.append(("h3", line[4:].strip()))
        elif line.startswith("## "):
            result.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            result.append(("h1", line[2:].strip()))
        else:
            # Убираем inline markdown: **bold**, *italic*, `code`
            cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
            cleaned = re.sub(r"\*(.*?)\*",     r"\1", cleaned)
            cleaned = re.sub(r"`(.*?)`",        r"\1", cleaned)
            result.append(("normal", cleaned))
    return result


def generate_pdf(title: str, content: str) -> Optional[bytes]:
    """
    Генерирует PDF из заголовка и текста (Markdown).
    Возвращает bytes или None если шрифт не найден.
    """
    reg = _resolve_font(FONT_REGULAR, _FALLBACK_FONTS)
    bold = _resolve_font(FONT_BOLD, _FALLBACK_FONTS)
    if not reg:
        logger.warning("PDF: шрифт с поддержкой кириллицы не найден — отправляем текстом")
        return None

    try:
        pdf = FPDF()
        pdf.set_margins(left=15, top=15, right=15)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Регистрируем шрифты
        pdf.add_font("regular", fname=reg)
        if bold and Path(bold).exists():
            pdf.add_font("bold", fname=bold)
            has_bold = True
        else:
            has_bold = False

        # Заголовок документа
        pdf.set_font("bold" if has_bold else "regular", size=16)
        pdf.multi_cell(0, 9, title, align="C")
        pdf.ln(4)

        # Горизонтальная линия
        pdf.set_draw_color(180, 180, 180)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(6)

        for tag, text in _parse_lines(content):
            if tag == "empty":
                pdf.ln(3)
            elif tag == "h1":
                pdf.set_font("bold" if has_bold else "regular", size=14)
                pdf.multi_cell(0, 8, text)
                pdf.ln(2)
            elif tag == "h2":
                pdf.set_font("bold" if has_bold else "regular", size=13)
                pdf.multi_cell(0, 7, text)
                pdf.ln(1)
            elif tag == "h3":
                pdf.set_font("bold" if has_bold else "regular", size=11)
                pdf.multi_cell(0, 6, text)
            else:
                pdf.set_font("regular", size=10)
                pdf.multi_cell(0, 5, text)

        return bytes(pdf.output())

    except Exception as e:  # noqa: BLE001
        logger.error(f"PDF generation failed: {e}")
        return None
