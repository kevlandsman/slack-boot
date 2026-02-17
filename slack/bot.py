from __future__ import annotations

import logging

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

logger = logging.getLogger(__name__)


def create_app(bot_token: str) -> AsyncApp:
    app = AsyncApp(token=bot_token)
    return app


async def start_socket_mode(app: AsyncApp, app_token: str):
    handler = AsyncSocketModeHandler(app, app_token)
    await handler.start_async()
