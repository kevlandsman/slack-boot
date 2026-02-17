from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OutputHandler:
    def __init__(self, slack_client=None):
        self.slack_client = slack_client

    async def handle(
        self,
        skill_config: dict,
        messages: list[dict],
        channel_id: str | None = None,
    ) -> Optional[str]:
        output_config = skill_config.get("output")
        if not output_config:
            return None

        content = self._format_output(messages, output_config.get("format", "text"))

        save_path = output_config.get("save_to")
        if save_path:
            path = self._resolve_path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            logger.info("Saved output to %s", path)

        if output_config.get("post_to_channel") and self.slack_client and channel_id:
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id, text=content
                )
                logger.info("Posted output to channel %s", channel_id)
            except Exception:
                logger.error(
                    "Failed to post output to channel %s", channel_id, exc_info=True
                )

        if save_path:
            return str(self._resolve_path(save_path))

        return content

    def _format_output(self, messages: list[dict], fmt: str) -> str:
        if fmt == "markdown":
            return self._to_markdown(messages)
        return self._to_text(messages)

    def _to_markdown(self, messages: list[dict]) -> str:
        lines = [f"# Session - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
        for msg in messages:
            if msg["role"] == "system":
                continue
            role_label = "**Bot**" if msg["role"] == "assistant" else "**User**"
            lines.append(f"{role_label}: {msg['content']}\n")
        return "\n".join(lines)

    def _to_text(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            if msg["role"] == "system":
                continue
            role = "Bot" if msg["role"] == "assistant" else "User"
            lines.append(f"{role}: {msg['content']}")
        return "\n\n".join(lines)

    def _resolve_path(self, path_template: str) -> Path:
        now = datetime.now()
        path_str = path_template.replace("{date}", now.strftime("%Y-%m-%d"))

        # Calculate ISO week string
        year, week, _ = now.isocalendar()
        path_str = path_str.replace("{week}", f"{year}-W{week:02d}")

        # Expand ~ to home directory
        return Path(path_str).expanduser()
