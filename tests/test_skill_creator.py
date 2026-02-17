from __future__ import annotations

import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock
from skills.creator import SkillCreator
from skills.loader import SkillLoader


@pytest.fixture
def skill_loader(tmp_path):
    loader = SkillLoader(str(tmp_path / "skills"))
    loader.ensure_dir()
    return loader


@pytest.fixture
def mock_llm_router():
    return MagicMock()


VALID_YAML_RESPONSE = """
name: daily-reminder
description: Remind Kevin to take a break
trigger: scheduled
schedule: "0 17 * * *"
channel: dm
target_user: kevin
llm: local
context: |
  Remind the user to take a short break.
  Be friendly and encouraging.
max_turns: 2
"""


class TestSkillCreator:
    @pytest.mark.asyncio
    async def test_create_from_description(self, mock_llm_router, skill_loader):
        mock_llm_router.get_response = AsyncMock(
            return_value=(VALID_YAML_RESPONSE, "cloud")
        )
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.create_from_description(
            "Remind me every day at 5pm to take a break"
        )
        assert result is not None
        assert result["name"] == "daily-reminder"
        assert result["trigger"] == "scheduled"
        assert skill_loader.get_skill("daily-reminder") is not None

    @pytest.mark.asyncio
    async def test_create_strips_markdown_fences(self, mock_llm_router, skill_loader):
        fenced = f"```yaml\n{VALID_YAML_RESPONSE}\n```"
        mock_llm_router.get_response = AsyncMock(return_value=(fenced, "cloud"))
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.create_from_description("test")
        assert result is not None
        assert result["name"] == "daily-reminder"

    @pytest.mark.asyncio
    async def test_create_invalid_yaml(self, mock_llm_router, skill_loader):
        mock_llm_router.get_response = AsyncMock(
            return_value=("this is not: valid: yaml: [[[", "cloud")
        )
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.create_from_description("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_missing_name(self, mock_llm_router, skill_loader):
        mock_llm_router.get_response = AsyncMock(
            return_value=("description: No name field\ntrigger: command", "cloud")
        )
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.create_from_description("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_modify_skill(self, mock_llm_router, skill_loader):
        # First create a skill
        skill_loader.save_skill({
            "name": "my-skill",
            "description": "Original",
            "trigger": "command",
            "context": "Original context",
        })

        updated_yaml = """
name: my-skill
description: Updated
trigger: command
context: Updated context
schedule: "0 17 * * *"
"""
        mock_llm_router.get_response = AsyncMock(
            return_value=(updated_yaml, "cloud")
        )
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.modify_skill("my-skill", "change the time to 5 PM")
        assert result is not None
        assert result["description"] == "Updated"

    @pytest.mark.asyncio
    async def test_modify_skill_not_found(self, mock_llm_router, skill_loader):
        creator = SkillCreator(mock_llm_router, skill_loader)
        result = await creator.modify_skill("nonexistent", "change something")
        assert result is None
