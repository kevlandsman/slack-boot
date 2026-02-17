from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path
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
