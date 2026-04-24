# ============================================================
# app/bot/handlers — хэндлеры, сгруппированные по темам
# ============================================================
from aiogram import Router

from . import agent_chat, athlete, coach, common, payments, poll, strava, training_log


def setup_routers() -> Router:
    """Собирает корневой router со всеми дочерними."""
    root = Router(name="root")
    # Порядок важен: сначала common (start/help), потом FSM-потоки.
    root.include_router(common.router)
    root.include_router(coach.router)
    root.include_router(athlete.router)
    root.include_router(poll.router)
    root.include_router(training_log.router)
    root.include_router(payments.router)
    root.include_router(strava.router)
    # agent_chat должен идти ПОСЛЕДНИМ — он ловит любой текст.
    root.include_router(agent_chat.router)
    return root
