from __future__ import annotations

import logging
import re

from agent.state import ConversationStateManager
from skills.loader import SkillLoader

logger = logging.getLogger(__name__)

# Patterns that suggest a command / skill-creation request
COMMAND_PATTERNS = [
    r"\bplease\b.*\b(start|begin|create|set up|schedule)\b",
    r"\b(remind|check in|contact|notify)\b.*\b(me|us)\b.*\b(every|daily|weekly)\b",
    r"\b(make|generate|build|create)\b.*\b(a |the )?(skill|routine|workflow|list|plan)\b",
    r"\b(can you|could you|would you)\b.*\b(start|begin|set up)\b",
]

SKILL_MODIFICATION_PATTERNS = [
    r"\b(change|modify|update|edit|adjust)\b.*\b(skill|routine|check-?in|schedule)\b",
    r"\badd a question\b",
    r"\bchange it to\b",
    r"\bremove the\b.*\bquestion\b",
]


class MessageType:
    COMMAND = "command"
    CONTINUATION = "continuation"
    CHANNEL_INTERACTION = "channel_interaction"
    SKILL_MODIFICATION = "skill_modification"
    GENERAL = "general"


class MessageRouter:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        skill_loader: SkillLoader,
        bot_user_id: str,
    ):
        self.state = state_manager
        self.skills = skill_loader
        self.bot_user_id = bot_user_id

    def classify(self, event: dict) -> tuple[str, dict]:
        """Classify an incoming Slack message.

        Returns (message_type, context_dict) where context_dict contains
        relevant information like the active conversation or matching skill.
        """
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")
        channel = event.get("channel", "")

        # Check if this is a reply in an existing conversation thread
        if thread_ts:
            conv = self.state.get_conversation_by_thread(thread_ts)
            if conv:
                return MessageType.CONTINUATION, {"conversation": conv}

        # Check for skill modification patterns
        if self._matches_patterns(text, SKILL_MODIFICATION_PATTERNS):
            return MessageType.SKILL_MODIFICATION, {"text": text}

        # Check for new command / skill-creation request
        if self._matches_patterns(text, COMMAND_PATTERNS):
            return MessageType.COMMAND, {"text": text}

        # Check for channel interactions where the bot is mentioned
        if f"<@{self.bot_user_id}>" in text:
            channel_refs = [channel]
            channel_name = event.get("channel_name")
            if channel_name:
                channel_refs.append(f"#{channel_name}")
            channel_skills: list[dict] = []
            seen_names: set[str] = set()
            for ref in channel_refs:
                for skill in self.skills.get_channel_skills(ref):
                    if skill["name"] not in seen_names:
                        channel_skills.append(skill)
                        seen_names.add(skill["name"])
            if channel_skills:
                return MessageType.CHANNEL_INTERACTION, {
                    "skills": channel_skills,
                    "text": self._strip_mention(text),
                }

        # Check if there's an active skill in this channel
        active = self.state.get_active_conversations_for_channel(channel)
        if active:
            return MessageType.CHANNEL_INTERACTION, {
                "conversation": active[0],
                "text": text,
            }

        return MessageType.GENERAL, {"text": text}

    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in patterns)

    def _strip_mention(self, text: str) -> str:
        return re.sub(r"<@\w+>\s*", "", text).strip()
