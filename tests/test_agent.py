# ============================================================
# tests/test_agent.py — Тесты агента с моком LLM API
# ============================================================
import pytest
import json
from unittest.mock import patch, MagicMock


# ── Хелпер для мок-ответов ───────────────────────────────────

def make_mock_response(
    content: str = "Тестовый ответ",
    tool_name: str = None,
    tool_args: str = "{}",
    finish_reason: str = "stop",
) -> MagicMock:
    """Создаёт мок-ответ LLM API"""
    mock_resp   = MagicMock()
    mock_msg    = MagicMock()
    mock_choice = MagicMock()

    mock_msg.content        = content
    mock_choice.message     = mock_msg
    mock_choice.finish_reason = finish_reason

    if tool_name:
        mock_choice.finish_reason = "tool_calls"
        tool_call                 = MagicMock()
        tool_call.id              = "call_test_123"
        tool_call.function.name   = tool_name
        tool_call.function.arguments = tool_args
        mock_msg.tool_calls       = [tool_call]
    else:
        mock_msg.tool_calls = None

    mock_resp.choices = [mock_choice]
    return mock_resp


# ══════════════════════════════════════════════════════════════
# Тесты run_agent
# ══════════════════════════════════════════════════════════════

@patch("agent.client.chat.completions.create")
def test_agent_direct_answer(mock_create, sample_athlete):
    """Агент отвечает напрямую без использования инструментов"""
    mock_create.return_value = make_mock_response("Прямой ответ на вопрос")

    from agent import run_agent
    answer, steps = run_agent("Расскажи про разминку", sample_athlete)

    assert answer == "Прямой ответ на вопрос"
    assert any(s["type"] == "final" for s in steps)
    assert not any(s["type"] == "thinking" for s in steps)


@patch("agent.execute_tool")
@patch("agent.client.chat.completions.create")
def test_agent_uses_training_plan_tool(mock_create, mock_execute, sample_athlete):
    """Агент вызывает инструмент generate_training_plan"""
    tool_response = make_mock_response(
        tool_name="generate_training_plan",
        tool_args=json.dumps({"weeks": "1", "focus": "выносливость"}),
        finish_reason="tool_calls",
    )
    final_response = make_mock_response("Вот план тренировок!")

    mock_create.side_effect = [tool_response, final_response]
    mock_execute.return_value = "ПЛАН: День 1 — лёгкий бег 30 мин..."

    from agent import run_agent
    answer, steps = run_agent("Составь план на неделю", sample_athlete)

    mock_execute.assert_called_once_with(
        "generate_training_plan",
        {"weeks": "1", "focus": "выносливость"},
        sample_athlete,
    )

    thinking_steps = [s for s in steps if s["type"] == "thinking"]
    result_steps   = [s for s in steps if s["type"] == "result"]
    assert len(thinking_steps) >= 1
    assert len(result_steps)   >= 1
    assert thinking_steps[0]["tool_name"] == "generate_training_plan"


@patch("agent.client.chat.completions.create")
def test_agent_handles_api_error(mock_create, sample_athlete):
    """Агент корректно обрабатывает ошибку API"""
    mock_create.side_effect = Exception("Connection timeout")

    from agent import run_agent
    answer, steps = run_agent("Составь план", sample_athlete)

    assert "ошибка" in answer.lower() or "error" in answer.lower()
    assert any(s["type"] == "final" for s in steps)


@patch("agent.client.chat.completions.create")
def test_agent_fallback_on_empty_content(mock_create, sample_athlete):
    """Агент возвращает резервный ответ при пустом content"""
    mock_create.return_value = make_mock_response(content="")

    from agent import run_agent
    answer, steps = run_agent("Тест", sample_athlete)

    assert answer, "Ответ не должен быть пустым"
    assert any(s["type"] == "final" for s in steps)


@patch("agent.client.chat.completions.create")
def test_agent_with_chat_history(mock_create, sample_athlete):
    """НОВОЕ: Агент принимает историю чата (memory)"""
    mock_create.return_value = make_mock_response("Ответ с контекстом")

    from agent import run_agent
    history = [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Здравствуйте!"},
    ]
    answer, steps = run_agent("Продолжи", sample_athlete, chat_history=history)

    assert answer == "Ответ с контекстом"
    # Проверяем, что history была добавлена в messages
    call_args = mock_create.call_args
    messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
    # Должно быть: system + 2 history + user = минимум 4
    assert len(messages) >= 4


@patch("agent.execute_tool")
@patch("agent.client.chat.completions.create")
def test_agent_prevents_duplicate_tool_calls(mock_create, mock_execute, sample_athlete):
    """НОВОЕ: Агент не вызывает один инструмент дважды"""
    tool_resp_1 = make_mock_response(
        tool_name="generate_training_plan",
        tool_args=json.dumps({"weeks": "1"}),
    )
    tool_resp_2 = make_mock_response(
        tool_name="generate_training_plan",
        tool_args=json.dumps({"weeks": "2"}),
    )
    final = make_mock_response("Готово!")

    mock_create.side_effect = [tool_resp_1, tool_resp_2, final]
    mock_execute.return_value = "План готов"

    from agent import run_agent
    answer, steps = run_agent("Составь план", sample_athlete)

    # execute_tool должен быть вызван только 1 раз
    assert mock_execute.call_count == 1


# ══════════════════════════════════════════════════════════════
# Тесты execute_tool
# ══════════════════════════════════════════════════════════════

@patch("agent.client.chat.completions.create")
def test_execute_tool_training_plan(mock_create, sample_athlete):
    """execute_tool корректно вызывает generate_training_plan"""
    mock_create.return_value = make_mock_response("Детальный план...")

    from agent import execute_tool
    result = execute_tool(
        "generate_training_plan",
        {"weeks": "2", "focus": "сила"},
        sample_athlete,
    )
    assert "Детальный план..." in result
    mock_create.assert_called_once()


@patch("agent.client.chat.completions.create")
def test_execute_tool_analyze_empty_results(mock_create, sample_athlete):
    """execute_tool возвращает предупреждение при пустых результатах"""
    from agent import execute_tool
    result = execute_tool("analyze_progress", {"results": ""}, sample_athlete)
    assert "не" in result.lower() or "⚠️" in result
    mock_create.assert_not_called()


def test_execute_tool_unknown_tool(sample_athlete):
    """execute_tool возвращает ошибку для неизвестного инструмента"""
    from agent import execute_tool
    result = execute_tool("unknown_tool_xyz", {}, sample_athlete)
    assert "⚠️" in result or "не найден" in result.lower()


@patch("agent.client.chat.completions.create")
def test_execute_tool_api_error_handled(mock_create, sample_athlete):
    """execute_tool возвращает понятное сообщение при ошибке API"""
    mock_create.side_effect = Exception("API unavailable")

    from agent import execute_tool
    result = execute_tool(
        "recovery_recommendation",
        {"fatigue_level": "7"},
        sample_athlete,
    )
    assert "⚠️" in result


@patch("agent.client.chat.completions.create")
def test_execute_tool_workload_analysis(mock_create, sample_athlete):
    """НОВОЕ: Тест нового инструмента analyze_workload"""
    mock_create.return_value = make_mock_response("Анализ нагрузки выполнен")

    from agent import execute_tool
    result = execute_tool(
        "analyze_workload",
        {"logs_summary": "День 1: RPE 6, День 2: RPE 7"},
        sample_athlete,
    )
    assert "Анализ нагрузки" in result


def test_execute_tool_workload_empty(sample_athlete):
    """НОВОЕ: analyze_workload с пустыми данными"""
    from agent import execute_tool
    result = execute_tool(
        "analyze_workload",
        {"logs_summary": ""},
        sample_athlete,
    )
    assert "⚠️" in result


# ══════════════════════════════════════════════════════════════
# Тесты метрик
# ══════════════════════════════════════════════════════════════

def test_wellness_score_calculation():
    """Тест расчёта wellness score"""
    from metrics import calculate_wellness_score
    assert calculate_wellness_score(1, 10) == 95.0
    assert calculate_wellness_score(10, 1) == 5.0
    assert calculate_wellness_score(5, 7) == 60.0


def test_trend_arrow():
    """Тест определения тренда"""
    from metrics import trend_arrow
    assert trend_arrow([3, 4, 6]) == "↑"
    assert trend_arrow([6, 5, 3]) == "↓"
    assert trend_arrow([5, 5, 5]) == "→"
    assert trend_arrow([5])       == "→"


def test_training_load_calculation():
    """НОВОЕ: Тест расчёта тренировочной нагрузки"""
    from metrics import calculate_training_load
    result = calculate_training_load([6, 7, 5, 8, 6])
    assert result["avg_rpe"] == 6.4
    assert result["intensity"] == "высокая"
    assert result["load_trend"] in ("↑", "↓", "→")


def test_training_load_empty():
    """НОВОЕ: Тест нагрузки с пустыми данными"""
    from metrics import calculate_training_load
    result = calculate_training_load([])
    assert result["avg_rpe"] == 0
    assert result["intensity"] == "нет данных"


def test_acwr_calculation():
    """НОВОЕ: Тест расчёта ACWR"""
    from metrics import calculate_acwr
    # 14 значений: 7 острых + 7 хронических
    rpe_values = [6, 7, 5, 6, 7, 6, 5, 4, 4, 5, 4, 5, 4, 4]
    result = calculate_acwr(rpe_values)
    assert result["acwr"] is not None
    assert result["zone"] in ("недотренированность", "оптимальная зона", "зона внимания", "опасная зона")


def test_acwr_insufficient_data():
    """НОВОЕ: ACWR с недостаточными данными"""
    from metrics import calculate_acwr
    result = calculate_acwr([5, 6, 7])
    assert result["acwr"] is None
    assert "недостаточно" in result["zone"]


def test_evaluate_response():
    """НОВОЕ: Тест оценки качества ответа"""
    from metrics import evaluate_response
    response = "День 1: разминка 10 минут, приседания 3 подхода по 10 повторений. Отдых между подходами."
    result = evaluate_response("generate_training_plan", response)
    assert result["score"] > 0
    assert result["grade"] in ("отлично", "хорошо", "удовлетворительно", "плохо")
    assert len(result["found"]) > 0


def test_evaluate_response_empty():
    """НОВОЕ: Оценка пустого ответа"""
    from metrics import evaluate_response
    result = evaluate_response("generate_training_plan", "")
    assert result["score"] == 0
