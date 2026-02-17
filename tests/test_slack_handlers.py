from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from slack.handlers import setup_scheduled_skill_callback


@pytest.mark.asyncio
async def test_scheduled_dm_lookup_paginates_users():
    agent = MagicMock()
    agent.trigger_scheduled_skill = AsyncMock(return_value=("hello", "conv-1"))
    agent.state = MagicMock()

    app = MagicMock()
    app.client = MagicMock()
    app.client.users_list = AsyncMock(
        side_effect=[
            {
                "members": [{"id": "U100", "name": "someone-else"}],
                "response_metadata": {"next_cursor": "next-page"},
            },
            {
                "members": [{"id": "U200", "name": "target-user"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )
    app.client.conversations_open = AsyncMock(return_value={"channel": {"id": "D200"}})
    app.client.chat_postMessage = AsyncMock(return_value={"ts": "123.456"})

    callback = setup_scheduled_skill_callback(agent, app)
    skill_config = {"name": "daily-dm", "channel": "dm", "target_user": "target-user"}
    await callback(skill_config)

    assert app.client.users_list.await_count == 2
    app.client.conversations_open.assert_awaited_once_with(users=["U200"])
    agent.trigger_scheduled_skill.assert_awaited_once_with(skill_config, "D200", "U200")
    app.client.chat_postMessage.assert_awaited_once_with(channel="D200", text="hello")
    agent.state.update_conversation.assert_called_once_with("conv-1", slack_thread="123.456")


@pytest.mark.asyncio
async def test_scheduled_channel_lookup_paginates_channels():
    agent = MagicMock()
    agent.trigger_scheduled_skill = AsyncMock(return_value=("channel hello", "conv-2"))
    agent.state = MagicMock()

    app = MagicMock()
    app.client = MagicMock()
    app.client.conversations_list = AsyncMock(
        side_effect=[
            {
                "channels": [{"id": "C100", "name": "general"}],
                "response_metadata": {"next_cursor": "next-page"},
            },
            {
                "channels": [{"id": "C200", "name": "ops"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )
    app.client.chat_postMessage = AsyncMock(return_value={"ts": "999.111"})

    callback = setup_scheduled_skill_callback(agent, app)
    skill_config = {"name": "ops-checkin", "channel": "#ops"}
    await callback(skill_config)

    assert app.client.conversations_list.await_count == 2
    agent.trigger_scheduled_skill.assert_awaited_once_with(skill_config, "C200", "system")
    app.client.chat_postMessage.assert_awaited_once_with(channel="C200", text="channel hello")
    agent.state.update_conversation.assert_called_once_with("conv-2", slack_thread="999.111")
