# ============================================================
# app/bot/utils.py — Вспомогательные утилиты для хэндлеров
# ============================================================

from __future__ import annotations

from typing import Iterable


def chunk_text(text: str, limit: int = 3800) -> list[str]:
    """
    Разбивает длинный текст на куски ≤limit символов — TG не пропускает
    сообщения >4096. Старается резать по двойным переносам строк.
    """
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = ""
    for block in text.split("\n\n"):
        if len(buf) + len(block) + 2 > limit:
            if buf:
                parts.append(buf.strip())
            # если блок сам больше limit — режем жёстко
            while len(block) > limit:
                parts.append(block[:limit])
                block = block[limit:]
            buf = block + "\n\n"
        else:
            buf += block + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def money(amount_minor: int, currency: str = "RUB") -> str:
    """Отформатировать сумму из минимальных единиц в рубли/доллары."""
    major = amount_minor / 100
    sign = "₽" if currency == "RUB" else currency
    return f"{major:,.2f} {sign}".replace(",", " ")


def join_lines(lines: Iterable[str]) -> str:
    return "\n".join(l for l in lines if l is not None)
