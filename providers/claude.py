from __future__ import annotations

import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


class ClaudeProvider:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-20250414"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def get_response(
        self, messages: list[dict], system_prompt: Optional[str] = None
    ) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = await self.client.messages.create(**kwargs)
            return response.content[0].text
        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            raise

    async def close(self):
        await self.client.close()
