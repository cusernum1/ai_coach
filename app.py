# ============================================================
# app.py — Главный UI (Streamlit)
# ============================================================
# Архитектура: app.py (UI) → services.py → agent/database/metrics
# Все бизнес-операции идут через CoachService.
# ============================================================

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from dotenv import load_dotenv
from pydantic import ValidationError

from config import config
from services import CoachService
from agent import run_agent, TOOL_NAMES_RU
from database import (
    init_db, save_athlete, get_all_athletes, delete_athlete,
    save_plan, get_athlete_plans,
    save_session, get_athlete_sessions,
    save_nutrition, get_athlete_nutrition,
    get_athlete_stats, save_agent_log, get_agent_stats,
    save_training_log, get_training_logs, get_athlete_state,
)
from pdf_export import (
    export_to_pdf, export_to_txt,
    export_full_report_txt, export_full_report_pdf,
    get_last_pdf_error,
)
from metrics import (
    get_sessions_dataframe, get_athlete_summary,
    calculate_wellness_score, wellness_label, trend_arrow,
    evaluate_response, get_training_load_dataframe,
    calculate_training_load, calculate_acwr,
)

load_dotenv()
init_db()

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.tool-step {
    border-left: 4px solid #3b82f6;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    margin: 6px 0;
    font-size: 0.92rem;
    background-color: rgba(59, 130, 246, 0.08);
}
.metric-card {
    border-radius: 12px;
    padding: 16px 12px;
    text-align: center;
    margin-bottom: 8px;
    background: linear-gradient(135deg, #1e3c72, #2a5298);
    color: white !important;
}
.metric-val   { font-size: 2rem; font-weight: 800; line-height: 1; }
.metric-label { font-size: 0.75rem; opacity: 0.85; margin-top: 4px; }
.state-banner {
    padding: 14px 18px;
    border-radius: 10px;
    margin-bottom: 16px;
    font-size: 0.95rem;
}
.log-done     { border-left: 4px solid #22c55e; background: rgba(34,197,94,0.08); padding: 8px 12px; border-radius: 0 6px 6px 0; margin: 4px 0; }
.log-partial  { border-left: 4px solid #f59e0b; background: rgba(245,158,11,0.08); padding: 8px 12px; border-radius: 0 6px 6px 0; margin: 4px 0; }
.log-skipped  { border-left: 4px solid #ef4444; background: rgba(239,68,68,0.08);  padding: 8px 12px; border-radius: 0 6px 6px 0; margin: 4px 0; }
.quality-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
}
.acwr-zone {
    padding: 10px 16px;
    border-radius: 8px;
    margin: 8px 0;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)


# ── Вспомогательные функции ───────────────────────────────────

def display_agent_steps(steps: list):
    """Отображает шаги рассуждения агента"""
    thinking = [s for s in steps if s["type"] in ("thinking", "result")]
    if not thinking:
        return
    with st.expander("🧠 Ход рассуждений агента", expanded=False):
        for step in thinking:
            if step["type"] == "thinking":
                st.markdown(
                    f"<div class='tool-step'>🔧 {step['content']}</div>",
                    unsafe_allow_html=True,
                )
                if step.get("args"):
                    st.json(step["args"])
            elif step["type"] == "result":
                st.success(f"✅ Инструмент выполнен — {len(step['content'])} символов")
        final_step = next((s for s in steps if s["type"] == "final"), None)
        if final_step and final_step.get("duration_ms"):
            st.caption(f"⏱ Время: {final_step['duration_ms']:.0f} мс")


def display_quality_badge(quality: dict):
    """НОВОЕ: Отображает бейдж качества ответа"""
    score = quality.get("score", 0)
    grade = quality.get("grade", "")
    colors = {
        "отлично": "#22c55e",
        "хорошо": "#3b82f6",
        "удовлетворительно": "#f59e0b",
        "плохо": "#ef4444",
    }
    color = colors.get(grade, "#6b7280")
    st.markdown(
        f"<span class='quality-badge' style='background:{color}20; color:{color};'>"
        f"Качество ответа: {score}% ({grade})</span>",
        unsafe_allow_html=True,
    )


def metric_html(value, label: str) -> str:
    return (
        f"<div class='metric-card'>"
        f"<div class='metric-val'>{value}</div>"
        f"<div class='metric-label'>{label}</div>"
        f"</div>"
    )


def athlete_badge(athlete: dict) -> str:
    return (
        f"**{athlete['name']}** · {athlete['sport']} · "
        f"{athlete['level']} · 🎯 {athlete['goal']}"
    )


def log_status_icon(status: str) -> str:
    return {"выполнено": "✅", "частично": "⚠️", "пропущено": "❌"}.get(status, "❓")


# ── Session state ─────────────────────────────────────────────
_defaults = {
    "messages":           [],
    "athlete":            None,
    "athlete_id":         None,
    "last_plan":          "",
    "last_plan_weeks":    1,
    "last_plan_focus":    "",
    "last_plan_steps":    None,   # НОВОЕ: шаги агента для отображения после rerun
    "last_plan_quality":  None,   # НОВОЕ: качество ответа для отображения после rerun
    "pending_quick":      None,
    "athlete_state":      None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def refresh_state():
    """Обновляет состояние спортсмена"""
    if st.session_state.athlete_id:
        st.session_state.athlete_state = get_athlete_state(
            st.session_state.athlete_id
        )


# ══════════════════════════════════════════════════════════════
# САЙДБАР
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏋️ ИИ-тренер")
    st.caption(f"v{config.APP_VERSION} · {config.LLM_PROVIDER.upper()} · {config.MODEL_NAME}")
    st.markdown("---")

    with st.expander(
        "👤 Новый / изменить профиль",
        expanded=st.session_state.athlete is None,
    ):
        name = st.text_input("Имя спортсмена", placeholder="Иван Иванов")
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input("Возраст", min_value=10, max_value=80, value=25)
        with c2:
            sessions_pw = st.slider("Трен./нед.", 1, 7, 3)

        sport = st.selectbox("Вид спорта", [
            "Бег", "Плавание", "Велоспорт", "Футбол",
            "Баскетбол", "Тяжёлая атлетика", "Теннис", "Другое",
        ])
        level = st.selectbox("Уровень", [
            "Начинающий", "Любитель", "Полупрофессионал", "Профессионал",
        ])
        goal = st.selectbox("Цель", [
            "Похудение", "Набор мышечной массы", "Выносливость",
            "Подготовка к соревнованиям", "Общая физическая форма",
        ])

        if st.button("💾 Сохранить профиль", use_container_width=True, type="primary"):
            try:
                # Валидация через Pydantic (services.py)
                aid, athlete_dict = CoachService.register_athlete({
                    "name": name, "age": age, "sport": sport,
                    "level": level, "goal": goal,
                    "sessions_per_week": sessions_pw,
                })
                st.session_state.athlete    = athlete_dict
                st.session_state.athlete_id = aid
                st.session_state.messages   = []
                refresh_state()
                st.success(f"✅ Профиль «{athlete_dict['name']}» сохранён!")
                st.rerun()
            except ValidationError as e:
                errors = e.errors()
                for err in errors:
                    st.error(f"⚠️ {err['msg']}")

    if st.session_state.athlete:
        a = st.session_state.athlete
        st.markdown("---")
        st.markdown("#### Активный спортсмен")
        st.info(
            f"**{a['name']}**, {a['age']} лет\n\n"
            f"🏅 {a['sport']} · {a['level']}\n\n"
            f"🎯 {a['goal']}\n\n"
            f"📅 {a['sessions_per_week']} тренировок/нед."
        )

        if st.session_state.athlete_id:
            stats = get_athlete_stats(st.session_state.athlete_id)
            if stats["sessions_count"] > 0:
                w = calculate_wellness_score(
                    stats["avg_fatigue"] or 5,
                    stats["avg_sleep"] or 7,
                )
                em, label = wellness_label(w)
                st.progress(int(w), text=f"Самочувствие: {em} {w}/100 ({label})")

    st.markdown("---")
    st.markdown("#### 📁 Все спортсмены")
    athletes_list = get_all_athletes()
    if athletes_list:
        for a_row in athletes_list:
            a_id, a_name = a_row[0], a_row[1]
            is_active = st.session_state.athlete_id == a_id
            col_name, col_del = st.columns([5, 1])
            with col_name:
                lbl = f"{'✅' if is_active else '👤'} {a_name}"
                if st.button(lbl, key=f"sel_{a_id}", use_container_width=True):
                    st.session_state.athlete = {
                        "name": a_row[1], "age": a_row[2], "sport": a_row[3],
                        "level": a_row[4], "goal": a_row[5],
                        "sessions_per_week": a_row[6],
                    }
                    st.session_state.athlete_id = a_id
                    st.session_state.messages   = []
                    refresh_state()
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_{a_id}"):
                    delete_athlete(a_id)
                    if st.session_state.athlete_id == a_id:
                        st.session_state.athlete       = None
                        st.session_state.athlete_id    = None
                        st.session_state.messages      = []
                        st.session_state.athlete_state = None
                    st.rerun()
    else:
        st.caption("Нет спортсменов ☝️")

    if st.session_state.athlete:
        st.markdown("---")
        if st.button("🆕 Очистить чат", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ══════════════════════════════════════════════════════════════
# ПРИВЕТСТВЕННЫЙ ЭКРАН
# ══════════════════════════════════════════════════════════════
st.markdown(f"# 🏋️ {config.APP_TITLE}")

if not st.session_state.athlete:
    st.markdown("---")
    cols = st.columns(4)
    features = [
        ("💬", "Умный чат",          "Задавайте вопросы — агент сам выбирает инструмент."),
        ("📋", "Планы тренировок",    "Детальные планы на 1–4 недели с прогрессией."),
        ("📊", "Аналитика и ACWR",    "Мониторинг нагрузки, Wellness Score, тренды."),
        ("🍎", "Питание",             "Персональный рацион и КБЖУ."),
    ]
    for col, (icon, title, desc) in zip(cols, features):
        with col:
            st.markdown(f"### {icon} {title}")
            st.markdown(desc)
    st.info("👈 **Заполните профиль спортсмена** в боковой панели чтобы начать.")
    st.stop()

athlete    = st.session_state.athlete
athlete_id = st.session_state.athlete_id

if st.session_state.athlete_state is None:
    refresh_state()

a_state = st.session_state.athlete_state or {"state": "no_plan", "has_data": False}


# ══════════════════════════════════════════════════════════════
# ВКЛАДКИ
# ══════════════════════════════════════════════════════════════
tab_chat, tab_plan, tab_journal, tab_analysis, tab_nutrition, tab_history = st.tabs([
    "💬 Чат",
    "📋 План тренировок",
    "📓 Журнал тренировок",
    "📊 Анализ и восстановление",
    "🍎 Питание",
    "📈 История и аналитика",
])


# ══════════════════════════════════════════════════════════════
# TAB 1 — ЧАТ (с памятью контекста)
# ══════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown(f"Чат с агентом · {athlete_badge(athlete)}")
    st.markdown("---")

    # Баннер состояния
    state = a_state["state"]
    if state == "no_plan":
        st.warning(
            "👋 Добро пожаловать! Сначала **составьте тренировочный план** "
            "на вкладке «📋 План тренировок»."
        )
    elif state == "no_sessions":
        st.info(
            "✅ План создан! Теперь **отмечайте тренировки** в журнале."
        )
    else:
        logs = get_training_logs(athlete_id, limit=3)
        if logs:
            last_log = logs[0]
            icon = log_status_icon(last_log[2])
            st.success(
                f"Последняя запись: {icon} {last_log[0]} — {last_log[1]} "
                f"| RPE: {last_log[3]}/10"
            )

    st.markdown("---")

    # Быстрые запросы
    st.markdown("**⚡ Быстрые запросы:**")
    if state == "no_plan":
        q_cols = st.columns(3)
        quick_map = {
            "📋 Составить план":  "Составь план тренировок на 1 неделю",
            "🍎 Питание":         "Дай рекомендации по питанию на тренировочный день",
            "❓ Что умеет агент": "Расскажи что ты умеешь делать как ИИ-агент тренера",
        }
    elif state == "no_sessions":
        q_cols = st.columns(3)
        quick_map = {
            "📋 Обновить план":   "Составь план тренировок на 1 неделю",
            "🔋 Восстановление":  "Оцени восстановление, усталость 5/10, сон 7/10",
            "🍎 Питание":         "Дай рекомендации по питанию на тренировочный день",
        }
    else:
        q_cols = st.columns(4)
        quick_map = {
            "📋 Новый план":       "Составь план тренировок на 1 неделю",
            "📊 Анализ прогресса": "Проанализируй мой прогресс на основе последних тренировок",
            "🔋 Восстановление":   "Оцени состояние восстановления, усталость 6/10, сон 7/10",
            "🍎 Питание":          "Дай рекомендации по питанию на тренировочный день",
        }

    for i, (btn_lbl, q_prompt) in enumerate(quick_map.items()):
        if q_cols[i].button(btn_lbl, key=f"qb_{i}", use_container_width=True):
            st.session_state.pending_quick = q_prompt
            st.rerun()

    st.markdown("---")

    # История и ввод
    pending = st.session_state.get("pending_quick")
    if pending:
        st.session_state.pending_quick = None

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = pending or st.chat_input("Введите сообщение для агента...")

    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        with st.chat_message("assistant"):
            with st.spinner("⏳ Агент обрабатывает запрос..."):
                # Передаём историю чата для контекста (НОВОЕ)
                answer, steps = run_agent(
                    user_text,
                    athlete,
                    chat_history=st.session_state.messages[:-1],
                )
            display_agent_steps(steps)
            st.markdown(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})

        if athlete_id:
            tools_used = [
                s["tool_name"] for s in steps
                if s["type"] == "result" and s.get("tool_name")
            ]
            dur = next(
                (s.get("duration_ms", 0) for s in steps if s["type"] == "final"), 0
            )
            save_agent_log(athlete_id, user_text, answer, tools_used, dur)
            refresh_state()

        st.rerun()


# ══════════════════════════════════════════════════════════════
# TAB 2 — ПЛАН ТРЕНИРОВОК
# ══════════════════════════════════════════════════════════════
with tab_plan:
    st.markdown(f"#### 📋 Тренировочный план · {athlete['name']}")
    st.markdown("---")

    col_settings, col_result = st.columns([1, 2])

    with col_settings:
        weeks = st.radio("Длительность", [1, 2, 4], horizontal=True,
                         format_func=lambda w: f"{w} нед.")
        focus = st.selectbox("Акцент тренировок", [
            "Общая подготовка", "Сила и мощность", "Выносливость",
            "Скорость", "Восстановление", "Подготовка к соревнованиям",
        ])
        generate_btn = st.button(
            "🚀 Составить план", use_container_width=True, type="primary",
        )

        if st.session_state.last_plan:
            st.markdown("---")
            st.markdown("**📥 Скачать план:**")
            txt_data = export_to_txt(
                athlete, st.session_state.last_plan,
                title=f"Тренировочный план — {st.session_state.last_plan_weeks} нед.",
            )
            st.download_button(
                "📄 Скачать TXT", data=txt_data,
                file_name=f"plan_{athlete['name'].replace(' ', '_')}.txt",
                mime="text/plain", use_container_width=True,
            )
            pdf_data = export_to_pdf(
                athlete, st.session_state.last_plan,
                st.session_state.last_plan_weeks,
                st.session_state.last_plan_focus,
            )
            if pdf_data:
                st.download_button(
                    "📕 Скачать PDF", data=pdf_data,
                    file_name=f"plan_{athlete['name'].replace(' ', '_')}.pdf",
                    mime="application/pdf", use_container_width=True,
                )
            else:
                st.warning("⚠️ Не удалось создать PDF")
                err = get_last_pdf_error()
                if err:
                    with st.expander("🔍 Детали ошибки", expanded=True):
                        st.code(err, language="python")

    with col_result:
        if generate_btn:
            with st.spinner(f"⏳ Составляю план на {weeks} нед. Акцент: {focus}..."):
                answer, steps, quality = CoachService.generate_plan(
                    athlete, weeks, focus,
                    chat_history=st.session_state.messages,
                )

            # Сохраняем ВСЁ в session_state для отображения после rerun
            st.session_state.last_plan         = answer
            st.session_state.last_plan_weeks   = weeks
            st.session_state.last_plan_focus   = focus
            st.session_state.last_plan_steps   = steps
            st.session_state.last_plan_quality = quality

            if athlete_id:
                save_plan(athlete_id, answer, weeks, focus)
                refresh_state()

            # ИСПРАВЛЕНИЕ: force rerun чтобы все вкладки получили
            # обновлённое состояние (no_plan → no_sessions)
            st.rerun()

        elif st.session_state.last_plan:
            # Показываем сохранённые шаги и качество после rerun
            if st.session_state.get("last_plan_steps"):
                display_agent_steps(st.session_state.last_plan_steps)
            if st.session_state.get("last_plan_quality"):
                display_quality_badge(st.session_state.last_plan_quality)
            st.markdown(st.session_state.last_plan)
        else:
            st.info("👈 Выберите параметры и нажмите «Составить план»")


# ══════════════════════════════════════════════════════════════
# TAB 3 — ЖУРНАЛ ТРЕНИРОВОК
# ══════════════════════════════════════════════════════════════
with tab_journal:
    st.markdown(f"#### 📓 Журнал тренировок · {athlete['name']}")
    st.markdown("---")

    if a_state["state"] == "no_plan":
        st.warning("Сначала создайте тренировочный план на вкладке «📋 План тренировок»")
    else:
        col_form, col_history = st.columns([1, 1])

        with col_form:
            st.markdown("### ✏️ Записать тренировку")
            log_date = st.date_input(
                "Дата тренировки", value=date.today(), max_value=date.today(),
            )
            day_name = st.text_input(
                "Название тренировки", placeholder="Силовая, Кардио, Интервалы...",
            )
            status = st.radio(
                "Выполнение", ["выполнено", "частично", "пропущено"], horizontal=True,
            )
            rpe = 5
            if status != "пропущено":
                rpe = st.slider("RPE — воспринимаемое усилие (1=легко, 10=максимум)", 1, 10, 6)

            notes = st.text_area(
                "Заметки", placeholder="Что было сделано, как чувствовали себя...", height=100,
            )

            if st.button("💾 Сохранить запись", use_container_width=True, type="primary"):
                try:
                    CoachService.log_training(
                        athlete_id=athlete_id,
                        log_date=str(log_date),
                        day_name=day_name,
                        status=status,
                        rpe=rpe,
                        notes=notes,
                    )
                    refresh_state()
                    st.success("✅ Запись сохранена!")
                    st.rerun()
                except ValidationError as e:
                    for err in e.errors():
                        st.error(f"⚠️ {err['msg']}")

        with col_history:
            st.markdown("### 📋 История записей")
            logs = get_training_logs(athlete_id, limit=14)

            if logs:
                total = len(logs)
                done  = sum(1 for l in logs if l[2] == "выполнено")
                part  = sum(1 for l in logs if l[2] == "частично")
                skip  = sum(1 for l in logs if l[2] == "пропущено")

                s1, s2, s3 = st.columns(3)
                s1.metric("✅ Выполнено", done)
                s2.metric("⚠️ Частично",  part)
                s3.metric("❌ Пропущено", skip)

                if total > 0:
                    adherence = round((done + part * 0.5) / total * 100)
                    st.progress(adherence / 100, text=f"Выполнение плана: {adherence}%")

                st.markdown("---")

                for log in logs:
                    log_date_str, day_n, log_status, log_rpe, log_notes, created = log
                    icon = log_status_icon(log_status)
                    css_class = {
                        "выполнено": "log-done",
                        "частично":  "log-partial",
                        "пропущено": "log-skipped",
                    }.get(log_status, "log-done")
                    rpe_str = f" · RPE {log_rpe}/10" if log_rpe and log_rpe > 0 else ""
                    st.markdown(
                        f"<div class='{css_class}'>"
                        f"<strong>{icon} {log_date_str}</strong> — {day_n}{rpe_str}<br>"
                        f"<small>{log_notes[:80] + '...' if log_notes and len(log_notes) > 80 else log_notes or ''}</small>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("---")
                if st.button(
                    "🤖 Попросить агента проанализировать прогресс",
                    use_container_width=True,
                ):
                    with st.spinner("⏳ Агент анализирует журнал..."):
                        answer, steps = CoachService.analyze_training_journal(
                            athlete, athlete_id,
                            chat_history=st.session_state.messages,
                        )
                    display_agent_steps(steps)
                    st.markdown(answer)

                    if athlete_id:
                        save_agent_log(athlete_id, "[анализ журнала]", answer, ["analyze_progress"], 0)
            else:
                st.info("Записей пока нет. Добавьте первую тренировку слева ☝️")


# ══════════════════════════════════════════════════════════════
# TAB 4 — АНАЛИЗ И ВОССТАНОВЛЕНИЕ
# ══════════════════════════════════════════════════════════════
with tab_analysis:
    st.markdown(f"#### 📊 Анализ и восстановление · {athlete['name']}")
    st.markdown("---")

    # ИСПРАВЛЕНО: вместо st.stop() используем else-блок
    if a_state["state"] == "no_plan":
        st.warning("⏳ Сначала создайте тренировочный план.")
    elif a_state["state"] == "no_sessions":
        st.info(
            "📓 Анализ будет доступен после записи хотя бы одной тренировки в журнале."
        )
    else:
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### 📈 Анализ результатов")

            logs = get_training_logs(athlete_id, limit=5)
            if logs:
                st.caption("📓 Последние записи:")
                for l in logs[:3]:
                    icon = log_status_icon(l[2])
                    rpe_str = f" · RPE {l[3]}/10" if l[3] else ""
                    st.caption(f"{icon} {l[0]} — {l[1]}{rpe_str}")

            results_text = st.text_area(
                "Введите результаты тренировок",
                placeholder="Бег 5км: 25 мин (была 27 мин)\nПрисед: 80кг × 5",
                height=140,
            )

            if st.button("🔍 Анализировать", use_container_width=True, type="primary"):
                if results_text.strip():
                    with st.spinner("⏳ Анализирую..."):
                        answer, steps, quality = CoachService.analyze_results(
                            athlete, athlete_id, results_text,
                            chat_history=st.session_state.messages,
                        )
                    display_agent_steps(steps)
                    display_quality_badge(quality)
                    st.markdown(answer)
                    if athlete_id:
                        save_session(athlete_id, results_text, 5, 7, "", answer)
                        refresh_state()
                else:
                    st.error("Введите результаты для анализа")

        with col_right:
            st.markdown("### 🔋 Оценка восстановления")
            fatigue = st.slider("Усталость (1 — нет, 10 — истощение)", 1, 10, 5)
            sleep_q = st.slider("Качество сна (1 — плохой, 10 — отличный)", 1, 10, 7)
            pain    = st.text_input("Боли или дискомфорт", placeholder="Ноют колени...")

            w_score = calculate_wellness_score(fatigue, sleep_q)
            em, lbl = wellness_label(w_score)
            st.progress(int(w_score), text=f"Самочувствие: {em} {w_score}/100 ({lbl})")

            if st.button("💊 Получить рекомендации", use_container_width=True, type="primary"):
                with st.spinner("⏳ Оцениваю..."):
                    answer, steps, wellness = CoachService.evaluate_recovery(
                        athlete, fatigue, sleep_q, pain,
                        chat_history=st.session_state.messages,
                    )
                display_agent_steps(steps)
                st.markdown(answer)
                if athlete_id:
                    save_session(athlete_id, "", fatigue, sleep_q, pain, answer)
                    refresh_state()


# ══════════════════════════════════════════════════════════════
# TAB 5 — ПИТАНИЕ
# ══════════════════════════════════════════════════════════════
with tab_nutrition:
    st.markdown(f"#### 🍎 Питание · {athlete['name']}")
    st.markdown("---")

    col_nut_left, col_nut_right = st.columns([1, 2])

    with col_nut_left:
        day_type = st.radio("Тип дня", ["тренировочный", "день отдыха"])
        specific_goal = st.text_input(
            "Конкретная цель (необязательно)",
            placeholder=f"По умолчанию: {athlete['goal']}",
        )
        gen_nut = st.button(
            "🥗 Составить рацион", use_container_width=True, type="primary",
        )

        if athlete_id:
            nutrition_history = get_athlete_nutrition(athlete_id, limit=3)
            if nutrition_history:
                st.markdown("---")
                st.markdown("**🕒 Последние рекомендации:**")
                for rec in nutrition_history:
                    with st.expander(f"{rec[1].capitalize()} — {rec[2]}"):
                        st.markdown(rec[0])

    with col_nut_right:
        if gen_nut:
            with st.spinner("⏳ Составляю рацион..."):
                goal_str = specific_goal.strip() or athlete["goal"]
                prompt = (
                    f"Дай рекомендации по питанию на {day_type} день. "
                    f"Цель: {goal_str}"
                )
                answer, steps = run_agent(
                    prompt, athlete,
                    chat_history=st.session_state.messages,
                )
            display_agent_steps(steps)

            # Оценка качества
            quality = evaluate_response("nutrition_recommendation", answer)
            display_quality_badge(quality)

            st.markdown(answer)
            if athlete_id:
                save_nutrition(
                    athlete_id, day_type,
                    specific_goal.strip() or athlete["goal"],
                    answer,
                )
            txt = export_to_txt(athlete, answer, title=f"Питание — {day_type}")
            st.download_button(
                "📄 Скачать TXT", data=txt,
                file_name=f"nutrition_{athlete['name'].replace(' ', '_')}.txt",
                mime="text/plain",
            )
        else:
            st.info("👈 Выберите тип дня и нажмите «Составить рацион»")


# ══════════════════════════════════════════════════════════════
# TAB 6 — ИСТОРИЯ И АНАЛИТИКА (расширенная)
# ══════════════════════════════════════════════════════════════
with tab_history:
    st.markdown(f"#### 📈 История и аналитика · {athlete['name']}")
    st.markdown("---")

    summary = get_athlete_summary(athlete_id) if athlete_id else {"has_data": False}

    # ── Верхние метрики ───────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.html(metric_html(summary.get("plans_count", 0), "Планов создано"))
    with m2:
        st.html(metric_html(a_state.get("logs_count", 0), "Тренировок в журнале"))
    with m3:
        avg_f = summary.get("avg_fatigue", "—")
        trend = summary.get("fatigue_trend", "→")
        st.html(metric_html(f"{avg_f} {trend}", "Средняя усталость"))
    with m4:
        avg_w = summary.get("avg_wellness", "—")
        st.html(metric_html(f"{avg_w}", "Самочувствие avg"))

    st.markdown("---")

    # ── НОВОЕ: ACWR и нагрузка ────────────────────────────────
    acwr_data = summary.get("acwr")
    load_data = summary.get("training_load")
    adherence = summary.get("adherence", {})

    if load_data or acwr_data:
        st.markdown("#### 🏋️ Тренировочная нагрузка")
        lc1, lc2, lc3, lc4 = st.columns(4)

        if load_data:
            with lc1:
                st.metric("Средний RPE", f"{load_data['avg_rpe']}", load_data["load_trend"])
            with lc2:
                st.metric("Интенсивность", load_data["intensity"])

        if acwr_data and acwr_data.get("acwr"):
            with lc3:
                acwr_val = acwr_data["acwr"]
                st.metric("ACWR", acwr_val, acwr_data["zone"])
            with lc4:
                adh = adherence.get("adherence", 0)
                st.metric("Выполнение плана", f"{adh}%")

            # Баннер ACWR
            zone_colors = {
                "green": "rgba(34,197,94,0.15)",
                "blue": "rgba(59,130,246,0.15)",
                "orange": "rgba(245,158,11,0.15)",
                "red": "rgba(239,68,68,0.15)",
            }
            bg = zone_colors.get(acwr_data["color"], "rgba(0,0,0,0.05)")
            st.markdown(
                f"<div class='acwr-zone' style='background:{bg}'>"
                f"📊 ACWR = {acwr_val} — <strong>{acwr_data['zone']}</strong><br>"
                f"<small>{acwr_data['recommendation']}</small></div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

    # ── Графики ───────────────────────────────────────────────
    chart_col, stats_col = st.columns([3, 2])

    with chart_col:
        st.markdown("#### 📊 Динамика состояния")
        df = get_sessions_dataframe(athlete_id) if athlete_id else None
        if df is not None and len(df) >= 2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["Дата"], y=df["Усталость"], name="Усталость",
                mode="lines+markers", line=dict(color="#ef4444", width=2),
            ))
            fig.add_trace(go.Scatter(
                x=df["Дата"], y=df["Сон"], name="Сон",
                mode="lines+markers", line=dict(color="#3b82f6", width=2),
            ))
            fig.add_trace(go.Scatter(
                x=df["Дата"], y=df["Самочувствие"] / 10, name="Wellness/10",
                mode="lines+markers", line=dict(color="#22c55e", width=2, dash="dot"),
            ))
            fig.update_layout(
                xaxis_title="Дата", yaxis_title="Оценка (1–10)",
                yaxis=dict(range=[0, 10]), hovermode="x unified",
                legend=dict(orientation="h", y=-0.2),
                height=300, margin=dict(l=40, r=20, t=30, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

        # График RPE
        logs = get_training_logs(athlete_id, limit=14)
        if logs:
            rpe_logs = [(l[0], l[1], l[3]) for l in logs if l[3] and l[3] > 0]
            if len(rpe_logs) >= 2:
                rpe_df = pd.DataFrame(
                    list(reversed(rpe_logs)),
                    columns=["Дата", "Тренировка", "RPE"],
                )
                fig_rpe = px.bar(
                    rpe_df, x="Дата", y="RPE",
                    title="Динамика нагрузки (RPE)",
                    color="RPE",
                    color_continuous_scale=["#22c55e", "#f59e0b", "#ef4444"],
                    range_color=[1, 10],
                )
                fig_rpe.update_layout(
                    height=250, margin=dict(l=40, r=20, t=40, b=40),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                st.plotly_chart(fig_rpe, use_container_width=True)
        else:
            st.info("Добавьте записи в журнале чтобы увидеть графики")

    with stats_col:
        st.markdown("#### 🤖 Статистика агента")
        if athlete_id:
            ag = get_agent_stats(athlete_id)
            st.metric("Всего запросов", ag["total_queries"])
            avg_dur = ag["avg_duration_ms"] or 0
            st.metric("Среднее время", f"{avg_dur:.0f} мс")

            tool_counts = ag.get("tool_counts", {})
            if tool_counts:
                labels = [TOOL_NAMES_RU.get(k, k) for k in tool_counts]
                values = list(tool_counts.values())
                fig_pie = px.pie(
                    names=labels, values=values, hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_pie.update_layout(
                    height=250, margin=dict(t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_pie, use_container_width=True)

    # ── Экспорт данных (с выбором формата TXT/PDF) ────────────
    st.markdown("---")
    exp1, exp2 = st.columns(2)

    with exp1:
        st.markdown("#### 📥 Экспорт полного отчёта")
        report_format = st.radio(
            "Формат:",
            ["📄 TXT", "📕 PDF"],
            horizontal=True,
            key="full_report_format",
            label_visibility="collapsed",
        )

        if "TXT" in report_format:
            full_report = export_full_report_txt(athlete, athlete_id)
            st.download_button(
                "⬇️ Скачать TXT",
                data=full_report,
                file_name=f"report_{athlete['name'].replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
                type="primary",
            )
        else:
            with st.spinner("⏳ Формирую PDF..."):
                pdf_data = export_full_report_pdf(athlete, athlete_id)
            if pdf_data:
                st.download_button(
                    "⬇️ Скачать PDF",
                    data=pdf_data,
                    file_name=f"report_{athlete['name'].replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )
            else:
                st.warning(
                    "⚠️ Не удалось создать PDF. "
                    "Убедитесь что шрифты установлены: `python download_fonts.py`"
                )
                err = get_last_pdf_error()
                if err:
                    with st.expander("🔍 Детали ошибки", expanded=True):
                        st.code(err, language="python")

    with exp2:
        st.markdown("#### 📋 История планов")
        if athlete_id:
            plans = get_athlete_plans(athlete_id, limit=5)
            if plans:
                # Формат скачивания для всех планов
                plan_dl_format = st.radio(
                    "Формат скачивания планов:",
                    ["📄 TXT", "📕 PDF"],
                    horizontal=True,
                    key="plan_history_format",
                    label_visibility="collapsed",
                )

                for idx, plan in enumerate(plans):
                    plan_text, p_weeks, p_date, p_focus = plan
                    with st.expander(f"📅 {p_date} — {p_weeks} нед. | {p_focus}"):
                        st.markdown(
                            plan_text[:300] + "..." if len(plan_text) > 300 else plan_text
                        )

                        safe_date = p_date.replace(' ', '_').replace(':', '')

                        if "TXT" in plan_dl_format:
                            txt_data = export_to_txt(
                                athlete, plan_text, f"План {p_date}"
                            )
                            st.download_button(
                                "⬇️ Скачать TXT",
                                data=txt_data,
                                file_name=f"plan_{safe_date}.txt",
                                mime="text/plain",
                                key=f"dl_txt_{idx}_{safe_date}",
                                use_container_width=True,
                            )
                        else:
                            # PDF генерируем только когда expander открыт
                            pdf_bytes = export_to_pdf(
                                athlete, plan_text, p_weeks, p_focus
                            )
                            if pdf_bytes:
                                st.download_button(
                                    "⬇️ Скачать PDF",
                                    data=pdf_bytes,
                                    file_name=f"plan_{safe_date}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_{idx}_{safe_date}",
                                    use_container_width=True,
                                )
                            else:
                                st.warning("Не удалось создать PDF")
                                err = get_last_pdf_error()
                                if err:
                                    with st.expander("🔍 Детали ошибки", expanded=True):
                                        st.code(err, language="python")
            else:
                st.caption("Планов пока нет")