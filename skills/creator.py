from __future__ import annotations

import logging
import yaml
from typing import Optional

from agent.llm_router import LLMRouter
from skills.loader import SkillLoader

logger = logging.getLogger(__name__)

SKILL_CREATION_PROMPT = """You are a skill configuration generator for Slack-Booty, a personal AI agent.

Given a natural language description from the user, generate a valid YAML skill configuration.

The YAML must include these fields:
- name: a kebab-case identifier
- description: brief description
- trigger: one of "scheduled", "mention", or "command"
- channel: "dm" for direct messages, or "#channel-name"
- llm: "local" or "cloud" (use "cloud" for nuanced multi-turn conversations, "local" for simple tasks)
- context: detailed instructions for the LLM when executing this skill

Optional fields:
- schedule: cron expression (required if trigger is "scheduled"), e.g. "0 16 * * *" for 4 PM daily
- target_user: username for DM skills
- participants: list of usernames
- fixed_questions: list of questions to always ask
- rotating_questions: list of questions to rotate through
- escalation_threshold: number of turns before escalating to cloud LLM
- max_turns: maximum conversation turns
- output:
    format: markdown or text
    save_to: file path pattern with {date} or {week} placeholders
    post_to_channel: true/false

Respond with ONLY the YAML content, no explanation or markdown fences."""


class SkillCreator:
    def __init__(self, llm_router: LLMRouter, skill_loader: SkillLoader):
        self.llm = llm_router
        self.loader = skill_loader

    async def create_from_description(self, description: str) -> Optional[dict]:
        messages = [{"role": "user", "content": description}]

        response, _ = await self.llm.get_response(
            messages,
            system_prompt=SKILL_CREATION_PROMPT,
            skill_config={"llm": "cloud"},
        )

        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])

        try:
            skill_config = yaml.safe_load(response)
        except yaml.YAMLError:
            logger.error("Failed to parse generated YAML:\n%s", response)
            return None

        if not isinstance(skill_config, dict) or "name" not in skill_config:
            logger.error("Generated config missing 'name' field")
            return None

        self.loader.save_skill(skill_config)
        return skill_config

    async def modify_skill(self, skill_name: str, modification: str) -> Optional[dict]:
        skill = self.loader.get_skill(skill_name)
        if not skill:
            return None

        current_yaml = yaml.dump(skill, default_flow_style=False)
        prompt = (
            f"Here is the current skill configuration:\n\n{current_yaml}\n\n"
            f"Modify it according to this request: {modification}\n\n"
            "Respond with ONLY the complete updated YAML."
        )

        messages = [{"role": "user", "content": prompt}]
        response, _ = await self.llm.get_response(
            messages,
            system_prompt=SKILL_CREATION_PROMPT,
            skill_config={"llm": "cloud"},
        )

        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])

        try:
            updated = yaml.safe_load(response)
        except yaml.YAMLError:
            logger.error("Failed to parse updated YAML:\n%s", response)
            return None

        if isinstance(updated, dict) and "name" in updated:
            self.loader.save_skill(updated)
            return updated
        return None
