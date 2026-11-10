import os
import uuid
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1. Абстрактный интерфейс (контракт для всех LLM-провайдеров)
# -----------------------------------------------------------------------------
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, context: str, system_prompt: str) -> str:
        pass


# -----------------------------------------------------------------------------
# 2. Реализация: GigaChat (Online)
# -----------------------------------------------------------------------------
class GigaChatProvider(LLMProvider):
    def __init__(self, credentials: str, scope: str, verify_ssl: bool = False):
        self.credentials = credentials
        self.scope = scope
        self.verify_ssl = verify_ssl
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self._token: Optional[str] = None

    def _refresh_token(self) -> None:
        headers = {
            "Authorization": f"Basic {self.credentials}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        resp = requests.post(self.auth_url, headers=headers, data={"scope": self.scope},
                             verify=self.verify_ssl, timeout=10)
        resp.raise_for_status()
        self._token = resp.json().get("access_token")
        logger.info("✅ GigaChat: токен успешно получен/обновлен")

    def generate(self, context: str, system_prompt: str) -> str:
        if not self._token:
            self._refresh_token()

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "model": "GigaChat",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": context}],
            "temperature": 0.7
        }

        resp = requests.post(self.chat_url, headers=headers, json=payload,
                             verify=self.verify_ssl, timeout=120)

        # Автоматический рефреш токена при истечении срока (401)
        if resp.status_code == 401:
            logger.warning("⚠️ GigaChat: токен истек, получаем новый...")
            self._refresh_token()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = requests.post(self.chat_url, headers=headers, json=payload,
                                 verify=self.verify_ssl, timeout=120)

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# -----------------------------------------------------------------------------
# 3. Реализация: Ollama (Offline / Local)
# -----------------------------------------------------------------------------
class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.verify_ssl = verify_ssl

    def generate(self, context: str, system_prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            "stream": False,
            "options": {"temperature": 0.7}
        }
        resp = requests.post(url, json=payload, verify=self.verify_ssl, timeout=180)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "Модель не вернула ответ")


# -----------------------------------------------------------------------------
# 4. Роутер / Оркестратор
# -----------------------------------------------------------------------------
class LLMAnalyzer:
    def __init__(self, online: Optional[LLMProvider] = None, offline: Optional[LLMProvider] = None):
        self.online = online
        self.offline = offline

    def generate_report(self, context: str, custom_prompt: str = "", mode: str = "online") -> str:
        if mode == "online" and self.online:
            provider = self.online
        elif mode == "offline" and self.offline:
            provider = self.offline
        else:
            available = []
            if self.online: available.append("online")
            if self.offline: available.append("offline")
            raise RuntimeError(f"Режим '{mode}' не настроен. Доступные: {', '.join(available) or 'нет'}")

        default_prompt = (
            "Ты — опытный HR-аналитик и эксперт по рынку труда. "
            "Проанализируй предоставленные данные и сформулируй краткий, структурированный отчет.\n"
            "Включи: 1) Ключевые тренды рынка. 2) Анализ зарплат. 3) Конкретные рекомендации.\n"
            "Отвечай на русском, используй маркированные списки."
        )
        full_system = f"{default_prompt}\n\n{custom_prompt}" if custom_prompt else default_prompt
        return provider.generate(context, full_system)


# -----------------------------------------------------------------------------
# 5. Фабрика (читает .env и собирает провайдеров)
# -----------------------------------------------------------------------------
def create_analyzer_from_env() -> LLMAnalyzer:
    verify_ssl = os.getenv("VERIFY_SSL", "False").lower() == "true"

    # --- ONLINE ---
    online_type = os.getenv("LLM_ONLINE_TYPE", "gigachat").lower()
    online_creds = os.getenv("LLM_ONLINE_CREDENTIALS")
    online_scope = os.getenv("LLM_ONLINE_SCOPE", "GIGACHAT_API_PERS")

    online_provider = None
    if online_creds and online_type == "gigachat":
        online_provider = GigaChatProvider(online_creds, online_scope, verify_ssl)

    # --- OFFLINE ---
    offline_url = os.getenv("LLM_OFFLINE_URL", "http://localhost:11434")
    offline_model = os.getenv("LLM_OFFLINE_MODEL", "llama3")
    offline_provider = OllamaProvider(offline_url, offline_model,
                                      verify_ssl=False)  # Ollama локальный, SSL обычно не нужен

    return LLMAnalyzer(online=online_provider, offline=offline_provider)