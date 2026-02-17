from __future__ import annotations

import logging
import re
from typing import Optional

from agent.state import ConversationStateManager
from agent.llm_router import LLMRouter
from skills.loader import SkillLoader
from skills.output import OutputHandler

logger = logging.getLogger(__name__)

# Matches [[ACTION:action_name|key=value|key=value]]
ACTION_PATTERN = re.compile(r"\[\[ACTION:(\w+)\|(.+?)\]\]")


class SkillExecutor:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        llm_router: LLMRouter,
        output_handler: OutputHandler,
        skill_loader: SkillLoader | None = None,
        google_services=None,
    ):
        self.state = state_manager
        self.llm = llm_router
        self.output = output_handler
        self.skill_loader = skill_loader
        self.google_services = google_services

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

    async def build_system_prompt_async(self, skill_config: dict) -> str:
        """Build system prompt with optional service context."""
        base_prompt = self.build_system_prompt(skill_config)
        service_context = await self._build_service_context(skill_config)
        return base_prompt + service_context

    async def _build_service_context(self, skill_config: dict) -> str:
        """Fetch data from declared services and format as context for the LLM."""
        services = skill_config.get("services", [])
        if (
            not services
            or not self.google_services
            or not self.google_services.available
        ):
            return ""

        parts = []

        if "gmail" in services:
            parts.append(
                "\n\nYou have access to Gmail (read-only). "
                "Available actions:\n"
                "  [[ACTION:search_email|query=GMAIL_QUERY]]\n"
                "  [[ACTION:read_email|id=MESSAGE_ID]]\n"
                "You CANNOT send emails, share, or delete anything."
            )
            # Pre-fetch unread emails if requested
            if skill_config.get("auto_fetch_unread"):
                try:
                    emails = await self.google_services.list_unread_email(
                        max_results=10
                    )
                    if emails:
                        parts.append("\nCurrent unread emails:")
                        for e in emails:
                            parts.append(
                                f"  - [{e['id']}] From: {e['from']} | "
                                f"Subject: {e['subject']} | {e['snippet']}"
                            )
                    else:
                        parts.append("\nNo unread emails.")
                except Exception:
                    logger.warning(
                        "Failed to pre-fetch unread emails", exc_info=True
                    )

        if "drive" in services:
            parts.append(
                "\n\nYou have access to Google Drive (create and read only). "
                "Available actions:\n"
                "  [[ACTION:create_doc|title=TITLE|content=CONTENT]]\n"
                "  [[ACTION:list_files|query=DRIVE_QUERY]]\n"
                "You CANNOT share documents, set permissions, or delete files."
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
        # Use async prompt builder if skill declares services
        if skill_config.get("services"):
            system_prompt = await self.build_system_prompt_async(skill_config)
        else:
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

        # Process any action blocks the LLM included
        response = await self.process_service_actions(response)

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

        # Process any action blocks the LLM included
        response = await self.process_service_actions(response)

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

    # ------------------------------------------------------------------
    # Service action processing
    # ------------------------------------------------------------------

    async def process_service_actions(self, response: str) -> str:
        """Parse ``[[ACTION:...]]`` blocks, execute them, and replace with results."""
        if not self.google_services or "[[ACTION:" not in response:
            return response

        matches = list(ACTION_PATTERN.finditer(response))
        if not matches:
            return response

        # Process in reverse order so replacements don't shift offsets
        for match in reversed(matches):
            replacement = await self._execute_action(
                match.group(1), match.group(2)
            )
            response = (
                response[: match.start()] + replacement + response[match.end() :]
            )

        return response

    async def _execute_action(self, action_name: str, params_str: str) -> str:
        """Execute a single service action and return a human-readable result."""
        try:
            params = dict(
                p.split("=", 1) for p in params_str.split("|") if "=" in p
            )
        except ValueError:
            return f"(Could not parse action parameters: {params_str})"

        try:
            if action_name == "search_email":
                query = params.get("query", "")
                results = await self.google_services.search_email(query)
                if not results:
                    return "No emails found."
                lines = [
                    f"- From: {e['from']} | Subject: {e['subject']} "
                    f"(ID: {e['id']})"
                    for e in results[:10]
                ]
                return "Email results:\n" + "\n".join(lines)

            elif action_name == "read_email":
                msg = await self.google_services.read_email(params["id"])
                body_preview = msg.get("body", "")[:500]
                return (
                    f"From: {msg['from']}\n"
                    f"Subject: {msg['subject']}\n"
                    f"Date: {msg['date']}\n\n"
                    f"{body_preview}"
                )

            elif action_name == "create_doc":
                result = await self.google_services.create_document(
                    title=params.get("title", "Untitled"),
                    content=params.get("content", ""),
                )
                return (
                    f"Created document: *{result['title']}*\n"
                    f"Link: {result['url']}"
                )

            elif action_name == "list_files":
                query = params.get("query")
                results = await self.google_services.list_drive_files(query=query)
                if not results:
                    return "No files found."
                lines = [
                    f"- {f['name']} ({f.get('mimeType', 'unknown')}) "
                    f"[link]({f.get('webViewLink', '')})"
                    for f in results[:10]
                ]
                return "Drive files:\n" + "\n".join(lines)

            else:
                return f"(Unknown action: {action_name})"

        except Exception as e:
            logger.error(
                "Service action %s failed: %s", action_name, e, exc_info=True
            )
            return f"(Action {action_name} failed: {e})"
