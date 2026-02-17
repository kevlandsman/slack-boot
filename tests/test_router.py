from __future__ import annotations

import pytest
from agent.router import MessageRouter, MessageType
from agent.state import ConversationStateManager
from skills.loader import SkillLoader


@pytest.fixture
def state_manager(tmp_path):
    return ConversationStateManager(str(tmp_path / "test.db"))


@pytest.fixture
def skill_loader(tmp_path):
    loader = SkillLoader(str(tmp_path / "skills"))
    loader.ensure_dir()
    return loader


@pytest.fixture
def router(state_manager, skill_loader):
    return MessageRouter(state_manager, skill_loader, bot_user_id="U_BOT")


class TestMessageRouter:
    def test_classify_continuation_with_active_thread(self, router, state_manager):
        state_manager.create_conversation(
            slack_thread="1234.5678",
            channel_id="C123",
            user_id="U456",
            skill_name="daily-checkin",
        )
        event = {
            "text": "I'm doing fine",
            "thread_ts": "1234.5678",
            "channel": "C123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.CONTINUATION
        assert "conversation" in ctx

    def test_classify_command_imperative(self, router):
        event = {
            "text": "Please start checking in with me daily",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.COMMAND

    def test_classify_command_create_skill(self, router):
        event = {
            "text": "Can you set up a weekly meal planner for us?",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.COMMAND

    def test_classify_command_schedule(self, router):
        event = {
            "text": "Remind me every day at 5pm to take a break",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.COMMAND

    def test_classify_skill_modification(self, router):
        event = {
            "text": "Change the daily check-in schedule to 5 PM",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.SKILL_MODIFICATION

    def test_classify_skill_modification_add_question(self, router):
        event = {
            "text": "Add a question about exercise to the routine",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.SKILL_MODIFICATION

    def test_classify_channel_interaction_mention(self, router, skill_loader):
        skill_loader.save_skill({
            "name": "meal-planning",
            "description": "Meal planning",
            "trigger": "mention",
            "channel": "#C123",
            "context": "Help plan meals.",
        })
        event = {
            "text": "<@U_BOT> what should we have for dinner?",
            "channel": "C123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.CHANNEL_INTERACTION
        assert "skills" in ctx

    def test_classify_channel_interaction_mention_with_channel_name(self, router, skill_loader):
        skill_loader.save_skill({
            "name": "general-helper",
            "description": "General channel helper",
            "trigger": "mention",
            "channel": "#general",
            "context": "Help in general.",
        })
        event = {
            "text": "<@U_BOT> summarize this thread",
            "channel": "C123",
            "channel_name": "general",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.CHANNEL_INTERACTION
        assert ctx["skills"][0]["name"] == "general-helper"

    def test_classify_general_message(self, router):
        event = {
            "text": "What's the weather like today?",
            "channel": "D123",
        }
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.GENERAL

    def test_classify_thread_reply_no_active_conversation(self, router):
        event = {
            "text": "Some reply",
            "thread_ts": "9999.9999",
            "channel": "C123",
        }
        # No matching conversation, so falls through
        msg_type, ctx = router.classify(event)
        assert msg_type == MessageType.GENERAL

    def test_strip_mention(self, router):
        result = router._strip_mention("<@U_BOT> hello there")
        assert result == "hello there"

    def test_strip_mention_no_mention(self, router):
        result = router._strip_mention("hello there")
        assert result == "hello there"
