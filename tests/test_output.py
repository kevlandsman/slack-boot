from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from skills.output import OutputHandler


@pytest.fixture
def handler():
    return OutputHandler()


@pytest.fixture
def sample_messages():
    return [
        {"role": "system", "content": "You are a bot."},
        {"role": "assistant", "content": "How was your day?"},
        {"role": "user", "content": "Pretty good!"},
        {"role": "assistant", "content": "Glad to hear it."},
    ]


class TestOutputHandler:
    @pytest.mark.asyncio
    async def test_handle_no_output_config(self, handler, sample_messages):
        result = await handler.handle({"name": "test"}, sample_messages)
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_save_to_file(self, handler, sample_messages, tmp_path):
        path = str(tmp_path / "output.md")
        skill_config = {
            "name": "test",
            "output": {"format": "markdown", "save_to": path},
        }
        result = await handler.handle(skill_config, sample_messages)
        assert result == path
        content = Path(path).read_text()
        assert "# Session" in content
        assert "How was your day?" in content
        assert "Pretty good!" in content

    @pytest.mark.asyncio
    async def test_handle_save_text_format(self, handler, sample_messages, tmp_path):
        path = str(tmp_path / "output.txt")
        skill_config = {
            "name": "test",
            "output": {"format": "text", "save_to": path},
        }
        result = await handler.handle(skill_config, sample_messages)
        content = Path(path).read_text()
        assert "Bot: How was your day?" in content
        assert "User: Pretty good!" in content

    def test_to_markdown_excludes_system(self, handler, sample_messages):
        result = handler._to_markdown(sample_messages)
        assert "You are a bot" not in result
        assert "**Bot**" in result
        assert "**User**" in result

    def test_to_text_excludes_system(self, handler, sample_messages):
        result = handler._to_text(sample_messages)
        assert "You are a bot" not in result

    def test_resolve_path_date(self, handler):
        path = handler._resolve_path("~/output/{date}.md")
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in str(path)

    def test_resolve_path_week(self, handler):
        path = handler._resolve_path("~/output/{week}.md")
        year, week, _ = datetime.now().isocalendar()
        assert f"{year}-W{week:02d}" in str(path)

    def test_resolve_path_expands_tilde(self, handler):
        path = handler._resolve_path("~/test/file.md")
        assert "~" not in str(path)
        assert str(Path.home()) in str(path)

    @pytest.mark.asyncio
    async def test_handle_creates_parent_dirs(self, handler, sample_messages, tmp_path):
        path = str(tmp_path / "nested" / "deep" / "output.md")
        skill_config = {
            "name": "test",
            "output": {"format": "markdown", "save_to": path},
        }
        result = await handler.handle(skill_config, sample_messages)
        assert Path(path).exists()

    @pytest.mark.asyncio
    async def test_post_to_channel(self, sample_messages):
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock()
        handler = OutputHandler(slack_client=mock_client)

        skill_config = {
            "name": "test",
            "output": {"format": "text", "post_to_channel": True},
        }
        await handler.handle(skill_config, sample_messages, channel_id="C123")
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["channel"] == "C123"
        assert "How was your day?" in call_kwargs.kwargs["text"]

    @pytest.mark.asyncio
    async def test_post_to_channel_and_save(self, sample_messages, tmp_path):
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock()
        handler = OutputHandler(slack_client=mock_client)

        path = str(tmp_path / "output.md")
        skill_config = {
            "name": "test",
            "output": {
                "format": "markdown",
                "save_to": path,
                "post_to_channel": True,
            },
        }
        result = await handler.handle(skill_config, sample_messages, channel_id="C123")
        # Both file saved and channel posted
        assert Path(path).exists()
        mock_client.chat_postMessage.assert_called_once()
        assert result == path

    @pytest.mark.asyncio
    async def test_post_to_channel_no_client(self, handler, sample_messages):
        """post_to_channel is a no-op when no slack_client is provided."""
        skill_config = {
            "name": "test",
            "output": {"format": "text", "post_to_channel": True},
        }
        # Should not raise — just skips posting
        result = await handler.handle(skill_config, sample_messages, channel_id="C123")
        assert result is not None  # returns content

    @pytest.mark.asyncio
    async def test_post_to_channel_no_channel_id(self, sample_messages):
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock()
        handler = OutputHandler(slack_client=mock_client)

        skill_config = {
            "name": "test",
            "output": {"format": "text", "post_to_channel": True},
        }
        # No channel_id passed — should not post
        await handler.handle(skill_config, sample_messages)
        mock_client.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_to_channel_error_does_not_raise(self, sample_messages):
        mock_client = MagicMock()
        mock_client.chat_postMessage = AsyncMock(side_effect=Exception("Slack error"))
        handler = OutputHandler(slack_client=mock_client)

        skill_config = {
            "name": "test",
            "output": {"format": "text", "post_to_channel": True},
        }
        # Should not raise even if posting fails
        result = await handler.handle(skill_config, sample_messages, channel_id="C123")
        assert result is not None
