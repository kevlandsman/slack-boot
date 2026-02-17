from __future__ import annotations

import os
import tempfile
import pytest
from agent.state import ConversationStateManager


@pytest.fixture
def state_manager(tmp_path):
    db_path = str(tmp_path / "test.db")
    return ConversationStateManager(db_path)


class TestConversationStateManager:
    def test_create_conversation(self, state_manager):
        conv_id = state_manager.create_conversation(
            slack_thread="1234.5678",
            channel_id="C123",
            user_id="U456",
            skill_name="daily-checkin",
            state={"phase": "active"},
            llm_provider="cloud",
        )
        assert conv_id is not None
        assert len(conv_id) == 36  # UUID format

    def test_get_conversation(self, state_manager):
        conv_id = state_manager.create_conversation(
            slack_thread="1234.5678",
            channel_id="C123",
            user_id="U456",
        )
        conv = state_manager.get_conversation(conv_id)
        assert conv is not None
        assert conv["channel_id"] == "C123"
        assert conv["user_id"] == "U456"
        assert conv["slack_thread"] == "1234.5678"
        assert conv["llm_provider"] == "local"

    def test_get_conversation_not_found(self, state_manager):
        result = state_manager.get_conversation("nonexistent")
        assert result is None

    def test_get_conversation_by_thread(self, state_manager):
        state_manager.create_conversation(
            slack_thread="thread-abc",
            channel_id="C123",
            user_id="U456",
        )
        conv = state_manager.get_conversation_by_thread("thread-abc")
        assert conv is not None
        assert conv["slack_thread"] == "thread-abc"

    def test_get_conversation_by_thread_not_found(self, state_manager):
        result = state_manager.get_conversation_by_thread("nonexistent")
        assert result is None

    def test_update_conversation(self, state_manager):
        conv_id = state_manager.create_conversation(
            slack_thread="1234",
            channel_id="C123",
            user_id="U456",
            state={"phase": "active"},
        )
        state_manager.update_conversation(
            conv_id,
            state={"phase": "complete", "turn": 5},
            llm_provider="cloud",
        )
        conv = state_manager.get_conversation(conv_id)
        assert conv["state"]["phase"] == "complete"
        assert conv["state"]["turn"] == 5
        assert conv["llm_provider"] == "cloud"

    def test_add_and_get_messages(self, state_manager):
        conv_id = state_manager.create_conversation(
            slack_thread="1234",
            channel_id="C123",
            user_id="U456",
        )
        state_manager.add_message(conv_id, "system", "You are a helper.")
        state_manager.add_message(conv_id, "user", "Hello!")
        state_manager.add_message(conv_id, "assistant", "Hi there!")

        messages = state_manager.get_messages(conv_id)
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helper."
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    def test_get_messages_empty(self, state_manager):
        conv_id = state_manager.create_conversation(
            slack_thread="1234",
            channel_id="C123",
            user_id="U456",
        )
        messages = state_manager.get_messages(conv_id)
        assert messages == []

    def test_get_active_conversations_for_channel(self, state_manager):
        state_manager.create_conversation(
            slack_thread="t1",
            channel_id="C123",
            user_id="U1",
            skill_name="meal-planning",
        )
        state_manager.create_conversation(
            slack_thread="t2",
            channel_id="C123",
            user_id="U2",
            skill_name=None,  # No skill — shouldn't show
        )
        state_manager.create_conversation(
            slack_thread="t3",
            channel_id="C999",
            user_id="U3",
            skill_name="other-skill",  # Different channel
        )

        active = state_manager.get_active_conversations_for_channel("C123")
        assert len(active) == 1
        assert active[0]["skill_name"] == "meal-planning"

    def test_state_json_roundtrip(self, state_manager):
        original_state = {
            "phase": "active",
            "answers": ["good", "7"],
            "nested": {"key": "value"},
        }
        conv_id = state_manager.create_conversation(
            slack_thread="1234",
            channel_id="C123",
            user_id="U456",
            state=original_state,
        )
        conv = state_manager.get_conversation(conv_id)
        assert conv["state"] == original_state

    def test_multiple_conversations_same_channel(self, state_manager):
        id1 = state_manager.create_conversation(
            slack_thread="t1",
            channel_id="C123",
            user_id="U1",
            skill_name="skill-a",
        )
        id2 = state_manager.create_conversation(
            slack_thread="t2",
            channel_id="C123",
            user_id="U2",
            skill_name="skill-b",
        )
        assert id1 != id2
        active = state_manager.get_active_conversations_for_channel("C123")
        assert len(active) == 2
