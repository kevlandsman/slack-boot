from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.core import AgentCore
from agent.state import ConversationStateManager
from skills.loader import SkillLoader


@pytest.fixture
def state_manager(tmp_path):
    return ConversationStateManager(str(tmp_path / "test.db"))


@pytest.fixture
def mock_llm_router():
    mock = MagicMock()
    mock.get_response = AsyncMock(return_value=("I can help with that!", "local"))
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def skill_loader(tmp_path):
    loader = SkillLoader(str(tmp_path / "skills"))
    loader.ensure_dir()
    return loader


@pytest.fixture
def agent(state_manager, mock_llm_router, skill_loader):
    return AgentCore(
        state_manager=state_manager,
        llm_router=mock_llm_router,
        skill_loader=skill_loader,
        bot_user_id="U_BOT",
    )


class TestAgentCore:
    @pytest.mark.asyncio
    async def test_handle_general_message(self, agent, mock_llm_router):
        event = {"text": "What's the weather?", "channel": "D123", "user": "U1"}
        response = await agent.handle_message(event)
        assert response == "I can help with that!"
        mock_llm_router.get_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_continuation(self, agent, state_manager, mock_llm_router, skill_loader):
        # Save the skill so the loader can find it
        skill_loader.save_skill({
            "name": "daily-checkin",
            "description": "Check-in",
            "trigger": "scheduled",
            "llm": "cloud",
            "max_turns": 8,
            "context": "Check-in bot",
        })
        skill_loader.load_all()

        # Create an active conversation
        conv_id = state_manager.create_conversation(
            slack_thread="1234.5678",
            channel_id="C123",
            user_id="U1",
            skill_name="daily-checkin",
            state={"phase": "active", "turn": 1},
        )
        state_manager.add_message(conv_id, "system", "You are a check-in bot.")
        state_manager.add_message(conv_id, "assistant", "How was your day?")

        mock_llm_router.get_response = AsyncMock(
            return_value=("Thanks for sharing!", "cloud")
        )

        event = {
            "text": "Pretty good, thanks!",
            "thread_ts": "1234.5678",
            "channel": "C123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert response == "Thanks for sharing!"

    @pytest.mark.asyncio
    async def test_handle_command_creates_skill(self, agent, mock_llm_router):
        import yaml
        skill_yaml = yaml.dump({
            "name": "test-reminder",
            "description": "Test reminder",
            "trigger": "scheduled",
            "schedule": "0 17 * * *",
            "context": "Remind the user",
        })
        mock_llm_router.get_response = AsyncMock(
            return_value=(skill_yaml, "cloud")
        )

        event = {
            "text": "Please start reminding me every day at 5pm",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "test-reminder" in response
        assert "scheduled" in response

    @pytest.mark.asyncio
    async def test_handle_command_failure(self, agent, mock_llm_router):
        mock_llm_router.get_response = AsyncMock(
            return_value=("not valid yaml [[[", "cloud")
        )
        event = {
            "text": "Please create a check-in skill for me",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "rephrase" in response.lower()

    @pytest.mark.asyncio
    async def test_handle_modification(self, agent, skill_loader, mock_llm_router):
        skill_loader.save_skill({
            "name": "daily-checkin",
            "description": "Daily check-in",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Check in daily",
        })
        skill_loader.load_all()

        import yaml
        updated = yaml.dump({
            "name": "daily-checkin",
            "description": "Updated check-in",
            "trigger": "scheduled",
            "schedule": "0 17 * * *",
            "context": "Check in at new time",
        })
        mock_llm_router.get_response = AsyncMock(return_value=(updated, "cloud"))

        event = {
            "text": "Change the daily check-in schedule to 5 PM",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "Updated" in response or "daily-checkin" in response

    @pytest.mark.asyncio
    async def test_trigger_scheduled_skill(self, agent, mock_llm_router):
        mock_llm_router.get_response = AsyncMock(
            return_value=("Time for your check-in!", "cloud")
        )
        skill_config = {
            "name": "daily-checkin",
            "description": "Check-in",
            "trigger": "scheduled",
            "llm": "cloud",
            "context": "Daily check-in",
            "max_turns": 8,
        }
        response, conv_id = await agent.trigger_scheduled_skill(
            skill_config, "C123", "U456"
        )
        assert response == "Time for your check-in!"
        assert conv_id is not None

    @pytest.mark.asyncio
    async def test_command_registers_schedule_immediately(self, state_manager, mock_llm_router, skill_loader):
        mock_scheduler = MagicMock()
        agent = AgentCore(
            state_manager=state_manager,
            llm_router=mock_llm_router,
            skill_loader=skill_loader,
            bot_user_id="U_BOT",
            scheduler=mock_scheduler,
        )

        import yaml
        skill_yaml = yaml.dump({
            "name": "live-skill",
            "description": "Live scheduled skill",
            "trigger": "scheduled",
            "schedule": "0 9 * * *",
            "context": "Good morning!",
        })
        mock_llm_router.get_response = AsyncMock(return_value=(skill_yaml, "cloud"))

        event = {
            "text": "Please start a morning check-in every day at 9am",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "active now" in response
        mock_scheduler.add_skill_job.assert_called_once()
        call_arg = mock_scheduler.add_skill_job.call_args[0][0]
        assert call_arg["name"] == "live-skill"

    @pytest.mark.asyncio
    async def test_modification_updates_schedule(self, state_manager, mock_llm_router, skill_loader):
        mock_scheduler = MagicMock()
        agent = AgentCore(
            state_manager=state_manager,
            llm_router=mock_llm_router,
            skill_loader=skill_loader,
            bot_user_id="U_BOT",
            scheduler=mock_scheduler,
        )

        skill_loader.save_skill({
            "name": "daily-checkin",
            "description": "Daily check-in",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Check in daily",
        })
        skill_loader.load_all()

        import yaml
        updated = yaml.dump({
            "name": "daily-checkin",
            "description": "Updated check-in",
            "trigger": "scheduled",
            "schedule": "0 17 * * *",
            "context": "Check in at new time",
        })
        mock_llm_router.get_response = AsyncMock(return_value=(updated, "cloud"))

        event = {
            "text": "Change the daily check-in schedule to 5 PM",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "Updated" in response or "daily-checkin" in response
        mock_scheduler.add_skill_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_no_scheduler_still_works(self, agent, mock_llm_router):
        """Creating a scheduled skill without a scheduler should not error."""
        import yaml
        skill_yaml = yaml.dump({
            "name": "no-sched",
            "description": "No scheduler present",
            "trigger": "scheduled",
            "schedule": "0 12 * * *",
            "context": "Noon check",
        })
        mock_llm_router.get_response = AsyncMock(return_value=(skill_yaml, "cloud"))

        event = {
            "text": "Please start a noon check-in",
            "channel": "D123",
            "user": "U1",
        }
        response = await agent.handle_message(event)
        assert "no-sched" in response

    @pytest.mark.asyncio
    async def test_close(self, agent, mock_llm_router):
        await agent.close()
        mock_llm_router.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_general_with_google_services(self, state_manager, mock_llm_router, skill_loader):
        mock_google = MagicMock()
        mock_google.available = True
        agent = AgentCore(
            state_manager=state_manager,
            llm_router=mock_llm_router,
            skill_loader=skill_loader,
            bot_user_id="U_BOT",
            google_services=mock_google,
        )
        # LLM returns a response with no action blocks
        mock_llm_router.get_response = AsyncMock(
            return_value=("I can check your email!", "local")
        )
        event = {"text": "Check my email", "channel": "D123", "user": "U1"}
        response = await agent.handle_message(event)
        assert response == "I can check your email!"

        # Verify system prompt included Google capabilities
        call_args = mock_llm_router.get_response.call_args
        system_prompt = call_args[0][1]
        assert "Gmail" in system_prompt or "Google" in system_prompt

    @pytest.mark.asyncio
    async def test_general_without_google_services(self, agent, mock_llm_router):
        """Without google_services, system prompt has no Google mention."""
        event = {"text": "What's the weather?", "channel": "D123", "user": "U1"}
        await agent.handle_message(event)
        call_args = mock_llm_router.get_response.call_args
        system_prompt = call_args[0][1]
        assert "Gmail" not in system_prompt

    @pytest.mark.asyncio
    async def test_general_processes_action_blocks(self, state_manager, mock_llm_router, skill_loader):
        mock_google = MagicMock()
        mock_google.available = True
        mock_google.search_email = AsyncMock(return_value=[
            {"id": "m1", "from": "alice@test.com", "subject": "Test Email"},
        ])
        agent = AgentCore(
            state_manager=state_manager,
            llm_router=mock_llm_router,
            skill_loader=skill_loader,
            bot_user_id="U_BOT",
            google_services=mock_google,
        )
        mock_llm_router.get_response = AsyncMock(
            return_value=("Here are results: [[ACTION:search_email|query=from:alice]]", "cloud")
        )
        event = {"text": "Search for emails from alice", "channel": "D123", "user": "U1"}
        response = await agent.handle_message(event)
        assert "alice@test.com" in response
        assert "[[ACTION:" not in response
