from __future__ import annotations

import logging

from agent.state import ConversationStateManager
from agent.router import MessageRouter, MessageType
from agent.llm_router import LLMRouter
from skills.loader import SkillLoader
from skills.executor import SkillExecutor
from skills.creator import SkillCreator
from skills.output import OutputHandler

logger = logging.getLogger(__name__)


class AgentCore:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        llm_router: LLMRouter,
        skill_loader: SkillLoader,
        bot_user_id: str,
    ):
        self.state = state_manager
        self.llm = llm_router
        self.skills = skill_loader
        self.bot_user_id = bot_user_id

        self.router = MessageRouter(state_manager, skill_loader, bot_user_id)
        self.output_handler = OutputHandler()
        self.executor = SkillExecutor(state_manager, llm_router, self.output_handler, skill_loader)
        self.creator = SkillCreator(llm_router, skill_loader)

    async def handle_message(self, event: dict) -> str | None:
        """Process an incoming Slack message and return a response, if any."""
        msg_type, context = self.router.classify(event)
        logger.info("Message classified as: %s", msg_type)

        if msg_type == MessageType.CONTINUATION:
            return await self._handle_continuation(event, context)
        elif msg_type == MessageType.COMMAND:
            return await self._handle_command(event, context)
        elif msg_type == MessageType.SKILL_MODIFICATION:
            return await self._handle_modification(event, context)
        elif msg_type == MessageType.CHANNEL_INTERACTION:
            return await self._handle_channel_interaction(event, context)
        elif msg_type == MessageType.GENERAL:
            return await self._handle_general(event, context)
        return None

    async def trigger_scheduled_skill(
        self, skill_config: dict, channel_id: str, user_id: str
    ) -> tuple[str, str]:
        """Trigger a skill from the scheduler. Returns (response, conversation_id)."""
        # Use a placeholder thread_ts; the Slack handler will update it
        # once the message is actually posted
        response, conv_id = await self.executor.start_skill(
            skill_config=skill_config,
            channel_id=channel_id,
            user_id=user_id,
            slack_thread="pending",
        )
        return response, conv_id

    async def _handle_continuation(self, event: dict, context: dict) -> str | None:
        conv = context["conversation"]
        user_text = event.get("text", "")
        return await self.executor.continue_skill(conv["id"], user_text)

    async def _handle_command(self, event: dict, context: dict) -> str | None:
        text = context["text"]
        skill_config = await self.creator.create_from_description(text)
        if skill_config:
            return (
                f"Got it! I've created a new skill: *{skill_config['name']}*\n"
                f"_{skill_config['description']}_\n"
                f"Trigger: `{skill_config['trigger']}`"
                + (f" | Schedule: `{skill_config.get('schedule', 'N/A')}`" if skill_config.get("schedule") else "")
                + "\nYou can modify this by telling me what to change."
            )
        return "I wasn't able to create that skill. Could you rephrase what you'd like?"

    async def _handle_modification(self, event: dict, context: dict) -> str | None:
        text = context["text"]
        # Try to find which skill the user is referring to
        all_skills = self.skills.get_all_skills()
        for name, skill in all_skills.items():
            if name.replace("-", " ") in text.lower():
                updated = await self.creator.modify_skill(name, text)
                if updated:
                    return f"Updated skill *{updated['name']}*. Changes saved."
                return f"I had trouble updating *{name}*. Could you try rephrasing?"

        return (
            "Which skill would you like to modify? Active skills: "
            + ", ".join(f"`{n}`" for n in all_skills.keys())
        )

    async def _handle_channel_interaction(self, event: dict, context: dict) -> str | None:
        text = context.get("text", event.get("text", ""))

        if "conversation" in context:
            conv = context["conversation"]
            return await self.executor.continue_skill(conv["id"], text)

        if "skills" in context:
            skill = context["skills"][0]
            channel_id = event.get("channel", "")
            user_id = event.get("user", "")
            thread_ts = event.get("ts", "")
            response, _ = await self.executor.start_skill(
                skill, channel_id, user_id, thread_ts
            )
            return response

        return None

    async def _handle_general(self, event: dict, context: dict) -> str | None:
        text = context["text"]
        messages = [{"role": "user", "content": text}]
        system_prompt = (
            "You are Slack-Booty, a helpful personal AI assistant. "
            "You communicate through Slack. Be concise and friendly. "
            "If the user seems to want to set up a recurring task or workflow, "
            "let them know they can ask you to create a skill for that."
        )
        response, _ = await self.llm.get_response(messages, system_prompt)
        return response

    async def close(self):
        await self.llm.close()
