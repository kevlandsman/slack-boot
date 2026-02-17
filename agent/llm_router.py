from __future__ import annotations

import logging
from typing import Optional

from providers.ollama import OllamaProvider
from providers.claude import ClaudeProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    def __init__(
        self,
        ollama: OllamaProvider,
        claude: ClaudeProvider,
        global_override: Optional[str] = None,
    ):
        self.ollama = ollama
        self.claude = claude
        self.global_override = global_override

    def _select_provider(
        self, skill_config: Optional[dict], messages: list[dict]
    ) -> str:
        if self.global_override:
            return self.global_override
        if skill_config:
            threshold = skill_config.get("escalation_threshold", 4)
            user_turns = sum(1 for m in messages if m["role"] == "user")
            if user_turns > threshold:
                return "cloud"
            return skill_config.get("llm", "local")
        return "local"

    async def get_response(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        skill_config: Optional[dict] = None,
    ) -> tuple[str, str]:
        """Returns (response_text, provider_used)."""
        provider = self._select_provider(skill_config, messages)

        if provider == "local":
            try:
                if await self.ollama.is_available():
                    text = await self.ollama.get_response(messages, system_prompt)
                    return text, "local"
                else:
                    logger.warning("Ollama unavailable, falling back to cloud")
                    provider = "cloud"
            except Exception:
                logger.warning("Ollama error, falling back to cloud", exc_info=True)
                provider = "cloud"

        text = await self.claude.get_response(messages, system_prompt)
        return text, "cloud"

    async def close(self):
        await self.ollama.close()
        await self.claude.close()
