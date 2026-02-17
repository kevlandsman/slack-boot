from __future__ import annotations

import logging
from typing import Optional

from agent.state import ConversationStateManager
from agent.llm_router import LLMRouter
from skills.loader import SkillLoader
from skills.output import OutputHandler

logger = logging.getLogger(__name__)


class SkillExecutor:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        llm_router: LLMRouter,
        output_handler: OutputHandler,
        skill_loader: SkillLoader | None = None,
    ):
        self.state = state_manager
        self.llm = llm_router
        self.output = output_handler
        self.skill_loader = skill_loader

    def build_system_prompt(self, skill_config: dict) -> str:
        parts = [skill_config["context"].strip()]

        if "fixed_questions" in skill_config:
            parts.append("\nFixed questions to ask:")
            for q in skill_config["fixed_questions"]:
                parts.append(f"  - {q}")

        if "rotating_questions" in skill_config:
            parts.append("\nRotating questions (pick one per session):")
            for q in skill_config["rotating_questions"]:
                parts.append(f"  - {q}")

        if "participants" in skill_config:
            parts.append(
                f"\nParticipants: {', '.join(skill_config['participants'])}"
            )

        if "output" in skill_config:
            out = skill_config["output"]
            parts.append(f"\nOutput format: {out.get('format', 'text')}")

        max_turns = skill_config.get("max_turns", 8)
        parts.append(
            f"\nThis conversation should complete within {max_turns} turns. "
            "When you've gathered enough information, summarize and wrap up."
        )

        return "\n".join(parts)

    async def start_skill(
        self,
        skill_config: dict,
        channel_id: str,
        user_id: str,
        slack_thread: str,
    ) -> tuple[str, str]:
        """Start a new skill conversation. Returns (response_text, conversation_id)."""
        system_prompt = self.build_system_prompt(skill_config)
        llm_provider = skill_config.get("llm", "local")

        conv_id = self.state.create_conversation(
            slack_thread=slack_thread,
            channel_id=channel_id,
            user_id=user_id,
            skill_name=skill_config["name"],
            state={"phase": "active", "turn": 0},
            llm_provider=llm_provider,
        )

        messages = [{"role": "user", "content": "Begin the conversation."}]
        response, provider_used = await self.llm.get_response(
            messages, system_prompt, skill_config
        )

        self.state.add_message(conv_id, "system", system_prompt)
        self.state.add_message(conv_id, "assistant", response)
        self.state.update_conversation(
            conv_id, llm_provider=provider_used, state={"phase": "active", "turn": 1}
        )

        return response, conv_id

    async def continue_skill(
        self, conversation_id: str, user_message: str
    ) -> Optional[str]:
        """Continue an existing skill conversation. Returns response or None if complete."""
        conv = self.state.get_conversation(conversation_id)
        if not conv:
            return None

        self.state.add_message(conversation_id, "user", user_message)

        history = self.state.get_messages(conversation_id)
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history
            if m["role"] != "system"
        ]

        system_prompt = None
        system_msgs = [m for m in history if m["role"] == "system"]
        if system_msgs:
            system_prompt = system_msgs[0]["content"]

        skill_config = None
        if conv.get("skill_name") and self.skill_loader:
            skill_config = self.skill_loader.get_skill(conv["skill_name"])

        response, provider_used = await self.llm.get_response(
            messages, system_prompt, skill_config
        )

        self.state.add_message(conversation_id, "assistant", response)

        current_state = conv.get("state", {})
        turn = current_state.get("turn", 0) + 1
        max_turns = skill_config.get("max_turns", 8) if skill_config else 8

        if turn >= max_turns:
            current_state["phase"] = "complete"
            if skill_config and "output" in skill_config:
                await self.output.handle(
                    skill_config,
                    history + [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": response},
                    ],
                    channel_id=conv.get("channel_id"),
                )

        current_state["turn"] = turn
        self.state.update_conversation(
            conversation_id,
            llm_provider=provider_used,
            state=current_state,
        )

        return response
