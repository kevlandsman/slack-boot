from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.llm_router import LLMRouter


@pytest.fixture
def mock_ollama():
    mock = MagicMock()
    mock.get_response = AsyncMock(return_value="local response")
    mock.is_available = AsyncMock(return_value=True)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_claude():
    mock = MagicMock()
    mock.get_response = AsyncMock(return_value="cloud response")
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def router(mock_ollama, mock_claude):
    return LLMRouter(mock_ollama, mock_claude)


class TestLLMRouter:
    @pytest.mark.asyncio
    async def test_default_routes_to_local(self, router):
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(messages)
        assert text == "local response"
        assert provider == "local"

    @pytest.mark.asyncio
    async def test_skill_config_cloud(self, router):
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(
            messages, skill_config={"llm": "cloud"}
        )
        assert text == "cloud response"
        assert provider == "cloud"

    @pytest.mark.asyncio
    async def test_skill_config_local(self, router):
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(
            messages, skill_config={"llm": "local"}
        )
        assert text == "local response"
        assert provider == "local"

    @pytest.mark.asyncio
    async def test_escalation_threshold(self, router):
        messages = [
            {"role": "user", "content": f"msg {i}"} for i in range(6)
        ] + [
            {"role": "assistant", "content": f"reply {i}"} for i in range(5)
        ]
        skill_config = {"llm": "local", "escalation_threshold": 4}
        text, provider = await router.get_response(
            messages, skill_config=skill_config
        )
        assert provider == "cloud"

    @pytest.mark.asyncio
    async def test_below_escalation_threshold(self, router):
        messages = [
            {"role": "user", "content": "msg 1"},
            {"role": "assistant", "content": "reply 1"},
        ]
        skill_config = {"llm": "local", "escalation_threshold": 4}
        text, provider = await router.get_response(
            messages, skill_config=skill_config
        )
        assert provider == "local"

    @pytest.mark.asyncio
    async def test_global_override_cloud(self, mock_ollama, mock_claude):
        router = LLMRouter(mock_ollama, mock_claude, global_override="cloud")
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(messages)
        assert text == "cloud response"
        assert provider == "cloud"

    @pytest.mark.asyncio
    async def test_global_override_local(self, mock_ollama, mock_claude):
        router = LLMRouter(mock_ollama, mock_claude, global_override="local")
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(messages)
        assert text == "local response"
        assert provider == "local"

    @pytest.mark.asyncio
    async def test_fallback_when_ollama_unavailable(self, mock_ollama, mock_claude):
        mock_ollama.is_available = AsyncMock(return_value=False)
        router = LLMRouter(mock_ollama, mock_claude)
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(messages)
        assert text == "cloud response"
        assert provider == "cloud"

    @pytest.mark.asyncio
    async def test_fallback_when_ollama_errors(self, mock_ollama, mock_claude):
        mock_ollama.is_available = AsyncMock(return_value=True)
        mock_ollama.get_response = AsyncMock(side_effect=Exception("Ollama down"))
        router = LLMRouter(mock_ollama, mock_claude)
        messages = [{"role": "user", "content": "hello"}]
        text, provider = await router.get_response(messages)
        assert text == "cloud response"
        assert provider == "cloud"

    @pytest.mark.asyncio
    async def test_system_prompt_passed(self, router, mock_ollama):
        messages = [{"role": "user", "content": "hello"}]
        await router.get_response(messages, system_prompt="Be helpful")
        mock_ollama.get_response.assert_called_once_with(messages, "Be helpful")

    @pytest.mark.asyncio
    async def test_close(self, router, mock_ollama, mock_claude):
        await router.close()
        mock_ollama.close.assert_called_once()
        mock_claude.close.assert_called_once()
