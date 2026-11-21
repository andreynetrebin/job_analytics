import os
import uuid
import time
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional, List

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 1. Абстрактный интерфейс
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

        resp = requests.post(self.chat_url, headers=headers, json=payload, verify=self.verify_ssl, timeout=120)

        if resp.status_code == 401:
            logger.warning("⚠️ GigaChat: токен истек, получаем новый...")
            self._refresh_token()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = requests.post(self.chat_url, headers=headers, json=payload, verify=self.verify_ssl, timeout=120)

        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# -----------------------------------------------------------------------------
# 3. Реализация: OpenRouter (Online, Free Models с авто-перебором)
# -----------------------------------------------------------------------------
class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, referer: str, title: str, verify_ssl: bool = False):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.verify_ssl = verify_ssl
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": referer,
            "X-Title": title,
            "Content-Type": "application/json"
        }
        # Актуальные бесплатные модели (отсортированы по стабильности и качеству)
        self.free_models: List[str] = [
            "meta-llama/llama-3-8b-instruct:free",
            "qwen/qwen-2.5-7b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "nvidia/nemotron-3.5-lightning:free",
            "cohere/command-r:free"
        ]

    def generate(self, context: str, system_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context}
        ]

        last_error = "Неизвестная ошибка"
        for model in self.free_models:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7
                }
                resp = requests.post(self.base_url, headers=self.headers, json=payload, verify=self.verify_ssl,
                                     timeout=60)

                # Если лимит исчерпан (429) или модель перегружена (503), тихо пробуем следующую
                if resp.status_code in (429, 503):
                    logger.warning(f"⚠️ OpenRouter: Лимит или перегрузка для {model}, пробую следующую...")
                    last_error = f"Rate limit/Overload ({resp.status_code})"
                    time.sleep(1)
                    continue

                resp.raise_for_status()
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")

                if content:
                    logger.info(f"✅ OpenRouter: Успешный ответ от модели {model}")
                    return content
                else:
                    logger.warning(f"⚠️ OpenRouter: Пустой ответ от {model}")
                    last_error = "Empty response"

            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠️ OpenRouter: Сетевая ошибка с {model}: {e}. Пробую следующую...")
                last_error = str(e)
                time.sleep(1)

        # Если все бесплатные модели недоступны
        raise RuntimeError(f"Все бесплатные модели OpenRouter недоступны. Последняя ошибка: {last_error}")


# -----------------------------------------------------------------------------
# 4. Реализация: Ollama (Offline / Local)
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
# 5. Роутер / Оркестратор
# -----------------------------------------------------------------------------
class LLMAnalyzer:
    def __init__(self, gigachat: Optional[LLMProvider] = None, openrouter: Optional[LLMProvider] = None,
                 offline: Optional[LLMProvider] = None):
        self.gigachat = gigachat
        self.openrouter = openrouter
        self.offline = offline

    def generate_report(self, context: str, custom_prompt: str = "", mode: str = "online") -> str:
        # Выбор провайдера
        if mode == "gigachat" and self.gigachat:
            provider = self.gigachat
        elif mode == "openrouter" and self.openrouter:
            provider = self.openrouter
        elif mode == "offline" and self.offline:
            provider = self.offline
        elif mode == "online":  # Fallback логика: сначала GigaChat, если нет - OpenRouter
            provider = self.gigachat or self.openrouter
        else:
            available = []
            if self.gigachat: available.append("gigachat")
            if self.openrouter: available.append("openrouter")
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
# 6. Фабрика (читает .env и собирает провайдеров)
# -----------------------------------------------------------------------------
def create_analyzer_from_env() -> LLMAnalyzer:
    verify_ssl = os.getenv("VERIFY_SSL", "False").lower() == "true"

    # --- GIGACHAT ---
    gc_creds = os.getenv("LLM_ONLINE_CREDENTIALS")
    gc_scope = os.getenv("LLM_ONLINE_SCOPE", "GIGACHAT_API_PERS")
    gigachat_provider = GigaChatProvider(gc_creds, gc_scope, verify_ssl) if gc_creds else None

    # --- OPENROUTER ---
    or_key = os.getenv("OPENROUTER_API_KEY")
    or_type = os.getenv("LLM_ONLINE_TYPE_2", "").lower()
    openrouter_provider = None
    if or_key and or_type == "openrouter":
        openrouter_provider = OpenRouterProvider(
            api_key=or_key,
            referer=os.getenv("OPENROUTER_REFERER", "https://localhost"),
            title=os.getenv("OPENROUTER_TITLE", "LocalApp"),
            verify_ssl=verify_ssl
        )

    # --- OFFLINE (OLLAMA) ---
    offline_url = os.getenv("LLM_OFFLINE_URL", "http://localhost:11434")
    offline_model = os.getenv("LLM_OFFLINE_MODEL", "llama3")
    offline_provider = OllamaProvider(offline_url, offline_model, verify_ssl=False)

    return LLMAnalyzer(gigachat=gigachat_provider, openrouter=openrouter_provider, offline=offline_provider)