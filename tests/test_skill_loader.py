from __future__ import annotations

import pytest
import yaml
from skills.loader import SkillLoader


@pytest.fixture
def skills_dir(tmp_path):
    return tmp_path / "skills"


@pytest.fixture
def loader(skills_dir):
    return SkillLoader(str(skills_dir))


def _write_skill(skills_dir, name, config):
    skills_dir.mkdir(parents=True, exist_ok=True)
    path = skills_dir / f"{name}.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)


class TestSkillLoader:
    def test_load_all_empty(self, loader, skills_dir):
        result = loader.load_all()
        assert result == {}

    def test_load_valid_skill(self, loader, skills_dir):
        config = {
            "name": "test-skill",
            "description": "A test skill",
            "trigger": "command",
            "context": "You are a test bot.",
        }
        _write_skill(skills_dir, "test-skill", config)
        result = loader.load_all()
        assert "test-skill" in result
        assert result["test-skill"]["description"] == "A test skill"

    def test_load_multiple_skills(self, loader, skills_dir):
        for i in range(3):
            config = {
                "name": f"skill-{i}",
                "description": f"Skill {i}",
                "trigger": "command",
                "context": f"Context {i}",
            }
            _write_skill(skills_dir, f"skill-{i}", config)
        result = loader.load_all()
        assert len(result) == 3

    def test_load_invalid_skill_skipped(self, loader, skills_dir):
        # Valid skill
        _write_skill(skills_dir, "good", {
            "name": "good",
            "description": "Good",
            "trigger": "command",
            "context": "Context",
        })
        # Invalid skill — missing required fields
        _write_skill(skills_dir, "bad", {
            "name": "bad",
        })
        result = loader.load_all()
        assert "good" in result
        assert "bad" not in result

    def test_get_skill(self, loader, skills_dir):
        _write_skill(skills_dir, "my-skill", {
            "name": "my-skill",
            "description": "Test",
            "trigger": "command",
            "context": "Context",
        })
        loader.load_all()
        skill = loader.get_skill("my-skill")
        assert skill is not None
        assert skill["name"] == "my-skill"

    def test_get_skill_not_found(self, loader, skills_dir):
        loader.load_all()
        assert loader.get_skill("nonexistent") is None

    def test_get_scheduled_skills(self, loader, skills_dir):
        _write_skill(skills_dir, "scheduled", {
            "name": "scheduled",
            "description": "Scheduled",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Context",
        })
        _write_skill(skills_dir, "manual", {
            "name": "manual",
            "description": "Manual",
            "trigger": "command",
            "context": "Context",
        })
        loader.load_all()
        scheduled = loader.get_scheduled_skills()
        assert len(scheduled) == 1
        assert scheduled[0]["name"] == "scheduled"

    def test_get_channel_skills(self, loader, skills_dir):
        _write_skill(skills_dir, "channel-skill", {
            "name": "channel-skill",
            "description": "Channel",
            "trigger": "mention",
            "channel": "#general",
            "context": "Context",
        })
        _write_skill(skills_dir, "dm-skill", {
            "name": "dm-skill",
            "description": "DM",
            "trigger": "command",
            "channel": "dm",
            "context": "Context",
        })
        loader.load_all()
        channel = loader.get_channel_skills("#general")
        assert len(channel) == 1
        assert channel[0]["name"] == "channel-skill"

    def test_save_skill(self, loader, skills_dir):
        config = {
            "name": "new-skill",
            "description": "New",
            "trigger": "command",
            "context": "New context",
        }
        path = loader.save_skill(config)
        assert path.exists()
        assert loader.get_skill("new-skill") is not None

        # Verify file content
        with open(path) as f:
            saved = yaml.safe_load(f)
        assert saved["name"] == "new-skill"

    def test_save_skill_overwrites(self, loader, skills_dir):
        config = {
            "name": "evolving",
            "description": "V1",
            "trigger": "command",
            "context": "Context V1",
        }
        loader.save_skill(config)
        config["description"] = "V2"
        loader.save_skill(config)
        skill = loader.get_skill("evolving")
        assert skill["description"] == "V2"
