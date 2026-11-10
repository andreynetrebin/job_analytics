import os
import json
import pytest
import responses
from unittest.mock import patch
from core.llm.llm_analyzer import GigaChatProvider, OllamaProvider, LLMAnalyzer, create_analyzer_from_env


class TestGigaChatProvider:
    @responses.activate
    def test_generate_success(self):
        """Успешный запрос к GigaChat (получение токена + чат)."""
        responses.add(
            responses.POST, "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            json={"access_token": "test_giga_token"}, status=200
        )
        responses.add(
            responses.POST, "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            json={"choices": [{"message": {"content": "Анализ от GigaChat"}}]}, status=200
        )

        provider = GigaChatProvider(credentials="base64_creds", scope="GIGACHAT_API_PERS", verify_ssl=False)
        result = provider.generate(context="Data", system_prompt="Be an analyst")

        assert result == "Анализ от GigaChat"
        assert len(responses.calls) == 2


class TestOllamaProvider:
    @responses.activate
    def test_generate_success(self):
        """Успешный запрос к локальному Ollama."""
        responses.add(
            responses.POST, "http://localhost:11434/api/chat",
            json={"message": {"content": "Анализ от Ollama"}}, status=200
        )

        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3")
        result = provider.generate(context="Data", system_prompt="Be an analyst")

        assert result == "Анализ от Ollama"
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["model"] == "llama3"


class TestLLMAnalyzerRouter:
    def test_routes_to_online(self):
        mock_online = GigaChatProvider("creds", "scope")
        mock_offline = OllamaProvider("http://localhost:11434", "llama3")
        analyzer = LLMAnalyzer(online=mock_online, offline=mock_offline)

        # Патчим метод generate, чтобы не делать реальных запросов
        with patch.object(mock_online, "generate", return_value="online_result") as mock_gen:
            result = analyzer.generate_report("ctx", mode="online")
            mock_gen.assert_called_once()
            assert result == "online_result"

    def test_routes_to_offline(self):
        mock_online = GigaChatProvider("creds", "scope")
        mock_offline = OllamaProvider("http://localhost:11434", "llama3")
        analyzer = LLMAnalyzer(online=mock_online, offline=mock_offline)

        with patch.object(mock_offline, "generate", return_value="offline_result") as mock_gen:
            result = analyzer.generate_report("ctx", mode="offline")
            mock_gen.assert_called_once()
            assert result == "offline_result"

    def test_fallback_if_provider_missing(self):
        analyzer = LLMAnalyzer(online=None, offline=None)
        with pytest.raises(RuntimeError, match="Режим 'online' не настроен"):
            analyzer.generate_report("ctx", mode="online")


class TestFactory:
    @patch.dict(os.environ, {
        "LLM_ONLINE_TYPE": "gigachat",
        "LLM_ONLINE_CREDENTIALS": "test_creds",
        "LLM_OFFLINE_URL": "http://localhost:11434",
        "LLM_OFFLINE_MODEL": "mistral"
    }, clear=True)
    def test_create_analyzer_from_env(self):
        analyzer = create_analyzer_from_env()
        assert analyzer.online is not None
        assert isinstance(analyzer.online, GigaChatProvider)
        assert analyzer.offline is not None
        assert isinstance(analyzer.offline, OllamaProvider)
        assert analyzer.offline.model == "mistral"