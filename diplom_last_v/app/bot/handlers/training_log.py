# ============================================================
# app/bot/handlers/training_log.py — Журнал тренировок
# ============================================================

from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards import athlete_main_kb, scale_kb, training_status_kb
from app.bot.states import TrainingLogFlow
from app.db import get_session
from app.db.models import Role, User
from app.db.repo import add_training_log, get_athlete_by_user_id, list_training_logs

router = Router(name="training_log")


@router.message(Command("log"))
@router.message(F.text == "📓 Журнал")
async def cmd_log(message: Message, state: FSMContext, user: User | None) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Только для спортсменов.")
        return

    # Короткая форма: "/log" → показать последние + спросить, добавить ли
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1 and parts[0].lower() != "📓 журнал":
        async with get_session() as s:
            athlete = await get_athlete_by_user_id(s, user.id)
            logs = await list_training_logs(s, athlete.id, days=7) if athlete else []
        if logs:
            lines = ["<b>Журнал за неделю:</b>"]
            for log in logs:
                lines.append(
                    f"• {log.log_date} — {log.day_name}: {log.status} (RPE {log.rpe})"
                )
            await message.answer("\n".join(lines))

    await message.answer(
        "Как называлась тренировка? (или /cancel чтобы отменить)",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(TrainingLogFlow.waiting_name)


@router.message(Command("cancel"), TrainingLogFlow.waiting_name)
@router.message(Command("cancel"), TrainingLogFlow.waiting_status)
@router.message(Command("cancel"), TrainingLogFlow.waiting_rpe)
@router.message(Command("cancel"), TrainingLogFlow.waiting_notes)
async def cancel_log(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=athlete_main_kb())


@router.message(TrainingLogFlow.waiting_name)
async def log_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Нужно название (например: «Силовая — верх»).")
        return
    await state.update_data(day_name=name)
    await message.answer("Как выполнена?", reply_markup=training_status_kb())
    await state.set_state(TrainingLogFlow.waiting_status)


@router.callback_query(TrainingLogFlow.waiting_status, F.data.startswith("log_status:"))
async def log_status(cb: CallbackQuery, state: FSMContext) -> None:
    status = cb.data.split(":", 1)[1]
    await state.update_data(status=status)
    await cb.message.edit_text(f"Статус: <b>{status}</b>")
    await cb.message.answer("Оцени RPE — воспринимаемое усилие (1–10):",
                             reply_markup=scale_kb("rpe"))
    await state.set_state(TrainingLogFlow.waiting_rpe)
    await cb.answer()


@router.callback_query(TrainingLogFlow.waiting_rpe, F.data.startswith("rpe:"))
async def log_rpe(cb: CallbackQuery, state: FSMContext) -> None:
    rpe = int(cb.data.split(":")[1])
    await state.update_data(rpe=rpe)
    await cb.message.edit_text(f"RPE: <b>{rpe}/10</b>")
    await cb.message.answer("Короткая заметка? /skip чтобы пропустить.")
    await state.set_state(TrainingLogFlow.waiting_notes)
    await cb.answer()


@router.message(TrainingLogFlow.waiting_notes)
async def log_notes(message: Message, state: FSMContext, user: User) -> None:
    notes = "" if (message.text or "").strip() in ("/skip", "-") else (message.text or "").strip()
    data = await state.get_data()
    await state.clear()

    async with get_session() as s:
        athlete = await get_athlete_by_user_id(s, user.id)
        if athlete is None:
            await message.answer("Нет профиля спортсмена.", reply_markup=athlete_main_kb())
            return
        await add_training_log(
            s, athlete.id,
            log_date=date.today(),
            day_name=data["day_name"],
            status=data["status"],
            rpe=int(data["rpe"]),
            notes=notes,
            source="manual",
        )
    await message.answer("✅ Запись в журнал добавлена.", reply_markup=athlete_main_kb())
