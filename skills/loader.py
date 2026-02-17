from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path.home() / ".slack-booty" / "skills"


class SkillLoader:
    def __init__(self, skills_dir: Optional[str] = None):
        self.skills_dir = Path(skills_dir) if skills_dir else DEFAULT_SKILLS_DIR
        self._skills: dict[str, dict] = {}

    def ensure_dir(self):
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict[str, dict]:
        self.ensure_dir()
        self._skills = {}
        for path in self.skills_dir.glob("*.yaml"):
            try:
                skill = self._load_file(path)
                self._skills[skill["name"]] = skill
                logger.info("Loaded skill: %s", skill["name"])
            except Exception:
                logger.error("Failed to load skill from %s", path, exc_info=True)
        return self._skills

    VALID_SERVICES = {"gmail", "drive"}

    def _load_file(self, path: Path) -> dict:
        with open(path) as f:
            data = yaml.safe_load(f)
        required = ["name", "description", "trigger", "context"]
        for field in required:
            if field not in data:
                raise ValueError(f"Skill {path.name} missing required field: {field}")

        # Warn on unknown service declarations (non-fatal)
        for svc in data.get("services", []):
            if svc not in self.VALID_SERVICES:
                logger.warning(
                    "Skill %s declares unknown service: %s", data["name"], svc
                )

        return data

    def get_skill(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def get_all_skills(self) -> dict[str, dict]:
        return dict(self._skills)

    def get_scheduled_skills(self) -> list[dict]:
        return [s for s in self._skills.values() if s.get("trigger") == "scheduled"]

    def get_channel_skills(self, channel: str) -> list[dict]:
        normalized = self._normalize_channel(channel)
        return [
            s
            for s in self._skills.values()
            if s.get("trigger") == "mention"
            and self._normalize_channel(s.get("channel", "")) == normalized
        ]

    def save_skill(self, skill_config: dict) -> Path:
        self.ensure_dir()
        path = self._build_skill_path(skill_config["name"])
        with open(path, "w") as f:
            yaml.dump(skill_config, f, default_flow_style=False, sort_keys=False)
        self._skills[skill_config["name"]] = skill_config
        logger.info("Saved skill: %s -> %s", skill_config["name"], path)
        return path

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        return str(channel).strip().lstrip("#").lower()

    def _build_skill_path(self, skill_name: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(skill_name)).strip(".-")
        if not safe:
            raise ValueError("Skill name must contain alphanumeric characters")
        path = (self.skills_dir / f"{safe}.yaml").resolve()
        if self.skills_dir.resolve() not in path.parents:
            raise ValueError(f"Refusing to write skill outside skills dir: {skill_name}")
        return path
