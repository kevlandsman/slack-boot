from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.state import ConversationStateManager
from skills.executor import SkillExecutor
from skills.loader import SkillLoader
from skills.output import OutputHandler


@pytest.fixture
def state_manager(tmp_path):
    return ConversationStateManager(str(tmp_path / "test.db"))


@pytest.fixture
def mock_llm_router():
    mock = MagicMock()
    mock.get_response = AsyncMock(return_value=("Hello! How was your day?", "cloud"))
    return mock


@pytest.fixture
def mock_output_handler():
    mock = MagicMock(spec=OutputHandler)
    mock.handle = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def skill_loader(tmp_path):
    loader = SkillLoader(str(tmp_path / "skills"))
    loader.ensure_dir()
    return loader


@pytest.fixture
def executor(state_manager, mock_llm_router, mock_output_handler, skill_loader):
    return SkillExecutor(state_manager, mock_llm_router, mock_output_handler, skill_loader)


CHECKIN_SKILL = {
    "name": "daily-checkin",
    "description": "Daily check-in",
    "trigger": "scheduled",
    "schedule": "0 16 * * *",
    "channel": "dm",
    "target_user": "kevin",
    "llm": "cloud",
    "escalation_threshold": 6,
    "context": "You are conducting a friendly daily check-in.",
    "fixed_questions": ["What did you accomplish today?", "Energy level (1-10)?"],
    "rotating_questions": ["What are you grateful for?"],
    "output": {"format": "markdown", "save_to": "~/checkins/{date}.md"},
    "max_turns": 8,
}


class TestSkillExecutor:
    def test_build_system_prompt_basic(self, executor):
        prompt = executor.build_system_prompt(CHECKIN_SKILL)
        assert "friendly daily check-in" in prompt
        assert "What did you accomplish today?" in prompt
        assert "Energy level (1-10)?" in prompt
        assert "grateful" in prompt
        assert "markdown" in prompt
        assert "8 turns" in prompt

    def test_build_system_prompt_minimal(self, executor):
        minimal = {
            "name": "simple",
            "description": "Simple",
            "trigger": "command",
            "context": "You are a simple bot.",
        }
        prompt = executor.build_system_prompt(minimal)
        assert "simple bot" in prompt
        assert "8 turns" in prompt  # default

    def test_build_system_prompt_with_participants(self, executor):
        config = {
            "name": "team-skill",
            "description": "Team skill",
            "trigger": "mention",
            "context": "Help the team.",
            "participants": ["alice", "bob"],
        }
        prompt = executor.build_system_prompt(config)
        assert "alice" in prompt
        assert "bob" in prompt

    @pytest.mark.asyncio
    async def test_start_skill(self, executor, state_manager, mock_llm_router):
        response, conv_id = await executor.start_skill(
            skill_config=CHECKIN_SKILL,
            channel_id="C123",
            user_id="U456",
            slack_thread="1234.5678",
        )
        assert response == "Hello! How was your day?"
        assert conv_id is not None

        # Verify conversation was created
        conv = state_manager.get_conversation(conv_id)
        assert conv is not None
        assert conv["skill_name"] == "daily-checkin"
        assert conv["llm_provider"] == "cloud"

        # Verify messages were stored
        messages = state_manager.get_messages(conv_id)
        assert len(messages) == 2  # system + assistant
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_continue_skill(self, executor, state_manager, mock_llm_router, skill_loader):
        # Save the skill so the loader can find it
        skill_loader.save_skill(CHECKIN_SKILL)
        skill_loader.load_all()

        # Start a skill
        mock_llm_router.get_response = AsyncMock(
            return_value=("First question!", "cloud")
        )
        _, conv_id = await executor.start_skill(
            skill_config=CHECKIN_SKILL,
            channel_id="C123",
            user_id="U456",
            slack_thread="1234.5678",
        )

        # Continue it
        mock_llm_router.get_response = AsyncMock(
            return_value=("Great! Next question.", "cloud")
        )
        response = await executor.continue_skill(conv_id, "I finished the report")
        assert response == "Great! Next question."

        # Verify user message was stored
        messages = state_manager.get_messages(conv_id)
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "I finished the report"

    @pytest.mark.asyncio
    async def test_continue_skill_not_found(self, executor):
        result = await executor.continue_skill("nonexistent", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_continue_skill_no_skill_loader(self, state_manager, mock_llm_router, mock_output_handler):
        # Executor without a skill_loader
        executor = SkillExecutor(state_manager, mock_llm_router, mock_output_handler, None)
        conv_id = state_manager.create_conversation(
            slack_thread="t1", channel_id="C1", user_id="U1",
            skill_name="some-skill", state={"phase": "active", "turn": 0},
        )
        state_manager.add_message(conv_id, "system", "System prompt")
        state_manager.add_message(conv_id, "assistant", "First message")

        mock_llm_router.get_response = AsyncMock(return_value=("Response", "local"))
        response = await executor.continue_skill(conv_id, "user reply")
        assert response == "Response"


# ------------------------------------------------------------------
# Google service integration tests
# ------------------------------------------------------------------


@pytest.fixture
def mock_google_services():
    mock = MagicMock()
    mock.available = True
    mock.search_email = AsyncMock(return_value=[
        {"id": "msg1", "from": "alice@test.com", "subject": "Hello", "snippet": "Hi there"},
    ])
    mock.read_email = AsyncMock(return_value={
        "id": "msg1", "from": "alice@test.com", "subject": "Hello",
        "date": "Mon, 1 Jan 2025", "body": "Full body content",
    })
    mock.list_unread_email = AsyncMock(return_value=[
        {"id": "u1", "from": "bob@test.com", "subject": "Urgent", "snippet": "Please read"},
    ])
    mock.create_document = AsyncMock(return_value={
        "id": "doc1", "title": "Notes", "url": "https://docs.google.com/document/d/doc1/edit",
    })
    mock.list_drive_files = AsyncMock(return_value=[
        {"name": "Report.docx", "mimeType": "application/vnd.google-apps.document",
         "webViewLink": "https://docs.google.com/doc/123"},
    ])
    return mock


@pytest.fixture
def executor_with_google(state_manager, mock_llm_router, mock_output_handler, skill_loader, mock_google_services):
    return SkillExecutor(
        state_manager, mock_llm_router, mock_output_handler, skill_loader,
        google_services=mock_google_services,
    )


GMAIL_SKILL = {
    "name": "email-summary",
    "description": "Summarize emails",
    "trigger": "scheduled",
    "llm": "cloud",
    "context": "Summarize unread emails.",
    "services": ["gmail"],
    "auto_fetch_unread": True,
    "max_turns": 2,
}


class TestServiceActions:
    @pytest.mark.asyncio
    async def test_process_no_actions(self, executor):
        """No action blocks = passthrough."""
        result = await executor.process_service_actions("Just a normal response")
        assert result == "Just a normal response"

    @pytest.mark.asyncio
    async def test_process_no_google(self, executor):
        """No google_services = passthrough even with action blocks."""
        response = "Here: [[ACTION:search_email|query=test]]"
        result = await executor.process_service_actions(response)
        assert result == response  # unchanged

    @pytest.mark.asyncio
    async def test_search_email_action(self, executor_with_google, mock_google_services):
        response = "Let me check: [[ACTION:search_email|query=from:alice]]"
        result = await executor_with_google.process_service_actions(response)
        assert "alice@test.com" in result
        assert "Hello" in result
        mock_google_services.search_email.assert_called_once_with("from:alice")

    @pytest.mark.asyncio
    async def test_read_email_action(self, executor_with_google, mock_google_services):
        response = "Reading: [[ACTION:read_email|id=msg1]]"
        result = await executor_with_google.process_service_actions(response)
        assert "alice@test.com" in result
        assert "Full body content" in result
        mock_google_services.read_email.assert_called_once_with("msg1")

    @pytest.mark.asyncio
    async def test_create_doc_action(self, executor_with_google, mock_google_services):
        response = "Creating: [[ACTION:create_doc|title=Meeting Notes|content=Hello world]]"
        result = await executor_with_google.process_service_actions(response)
        assert "Notes" in result
        assert "docs.google.com" in result
        mock_google_services.create_document.assert_called_once_with(
            title="Meeting Notes", content="Hello world"
        )

    @pytest.mark.asyncio
    async def test_list_files_action(self, executor_with_google, mock_google_services):
        response = "Files: [[ACTION:list_files|query=name contains 'report']]"
        result = await executor_with_google.process_service_actions(response)
        assert "Report.docx" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self, executor_with_google):
        response = "Do: [[ACTION:send_email|to=evil@hack.com]]"
        result = await executor_with_google.process_service_actions(response)
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_action_error_handled(self, executor_with_google, mock_google_services):
        mock_google_services.search_email = AsyncMock(side_effect=Exception("API down"))
        response = "Check: [[ACTION:search_email|query=test]]"
        result = await executor_with_google.process_service_actions(response)
        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_multiple_actions(self, executor_with_google, mock_google_services):
        response = (
            "Email: [[ACTION:search_email|query=test]] "
            "and doc: [[ACTION:create_doc|title=Test|content=Hi]]"
        )
        result = await executor_with_google.process_service_actions(response)
        assert "alice@test.com" in result
        assert "docs.google.com" in result

    @pytest.mark.asyncio
    async def test_search_email_empty_results(self, executor_with_google, mock_google_services):
        mock_google_services.search_email = AsyncMock(return_value=[])
        response = "Check: [[ACTION:search_email|query=nonexistent]]"
        result = await executor_with_google.process_service_actions(response)
        assert "No emails found" in result

    @pytest.mark.asyncio
    async def test_list_files_empty_results(self, executor_with_google, mock_google_services):
        mock_google_services.list_drive_files = AsyncMock(return_value=[])
        response = "Files: [[ACTION:list_files|query=nothing]]"
        result = await executor_with_google.process_service_actions(response)
        assert "No files found" in result


class TestServiceContext:
    @pytest.mark.asyncio
    async def test_build_service_context_no_services(self, executor):
        config = {"name": "test", "context": "Test"}
        result = await executor._build_service_context(config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_service_context_no_google(self, executor):
        config = {"name": "test", "context": "Test", "services": ["gmail"]}
        result = await executor._build_service_context(config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_service_context_gmail(self, executor_with_google):
        config = {
            "name": "test", "context": "Test",
            "services": ["gmail"],
        }
        result = await executor_with_google._build_service_context(config)
        assert "Gmail" in result
        assert "read-only" in result
        assert "CANNOT send" in result

    @pytest.mark.asyncio
    async def test_build_service_context_drive(self, executor_with_google):
        config = {
            "name": "test", "context": "Test",
            "services": ["drive"],
        }
        result = await executor_with_google._build_service_context(config)
        assert "Drive" in result
        assert "CANNOT share" in result

    @pytest.mark.asyncio
    async def test_build_service_context_prefetch_unread(self, executor_with_google, mock_google_services):
        config = {
            "name": "test", "context": "Test",
            "services": ["gmail"],
            "auto_fetch_unread": True,
        }
        result = await executor_with_google._build_service_context(config)
        assert "bob@test.com" in result
        assert "Urgent" in result
        mock_google_services.list_unread_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_service_context_prefetch_empty(self, executor_with_google, mock_google_services):
        mock_google_services.list_unread_email = AsyncMock(return_value=[])
        config = {
            "name": "test", "context": "Test",
            "services": ["gmail"],
            "auto_fetch_unread": True,
        }
        result = await executor_with_google._build_service_context(config)
        assert "No unread emails" in result

    @pytest.mark.asyncio
    async def test_build_service_context_prefetch_error(self, executor_with_google, mock_google_services):
        mock_google_services.list_unread_email = AsyncMock(side_effect=Exception("API error"))
        config = {
            "name": "test", "context": "Test",
            "services": ["gmail"],
            "auto_fetch_unread": True,
        }
        # Should not raise — error is logged and swallowed
        result = await executor_with_google._build_service_context(config)
        assert "Gmail" in result

    @pytest.mark.asyncio
    async def test_start_skill_with_services(self, executor_with_google, mock_llm_router, mock_google_services):
        mock_llm_router.get_response = AsyncMock(
            return_value=("Here's your email summary!", "cloud")
        )
        response, conv_id = await executor_with_google.start_skill(
            skill_config=GMAIL_SKILL,
            channel_id="C123",
            user_id="U456",
            slack_thread="t1",
        )
        assert "email summary" in response
        # Should have pre-fetched unread emails
        mock_google_services.list_unread_email.assert_called_once()
