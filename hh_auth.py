"""
hh_auth.py
Авторизация типа APPLICATION через client_credentials.
Согласно документации HH, /vacancies доступны только для application и employer.
Браузер и redirect больше не нужны.
"""

import os
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TOKEN_FILE = 'hh_tokens.json'
TOKEN_URL = 'https://api.hh.ru/token'


class HHAuthManager:
    def __init__(self):
        self.client_id = os.getenv('CLIENT_ID')
        self.client_secret = os.getenv('CLIENT_SECRET')

        if not self.client_id or not self.client_secret:
            raise ValueError("CLIENT_ID и CLIENT_SECRET должны быть указаны в .env")

    def get_valid_token(self) -> str:
        """
        Возвращает валидный application-токен.
        Если токена нет или он истек — запрашивает новый через client_credentials.
        """
        tokens = self._load_tokens()

        # Используем сохраненный токен, только если он application-типа и не истек
        if (tokens
                and tokens.get('auth_type') == 'application'
                and time.time() < tokens.get('expires_at', 0) - 60):
            return tokens['access_token']

        # Иначе запрашиваем новый application-токен
        return self._request_token()

    def _request_token(self) -> str:
        """Запрашивает токен авторизации приложения (client_credentials)."""
        payload = {
            'grant_type': 'client_credentials',   # ← ключевое отличие
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        logger.info("Запрашиваю application-токен (client_credentials)...")
        resp = requests.post(TOKEN_URL, data=payload, timeout=15)

        if resp.status_code != 200:
            logger.error(f"Ошибка получения токена: {resp.status_code} - {resp.text}")
            raise Exception(f"Failed to get application token: {resp.text}")

        token_data = resp.json()
        token_data['auth_type'] = 'application'   # маркер типа авторизации
        self._save_tokens(token_data)
        logger.info("✅ Application-токен получен и сохранен")
        return token_data['access_token']

    def _load_tokens(self) -> dict | None:
        if not os.path.exists(TOKEN_FILE):
            return None
        try:
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _save_tokens(self, token_data: dict):
        token_data['expires_at'] = time.time() + token_data.get('expires_in', 7200) - 60
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)

    def get_token_info(self) -> dict:
        """Статус текущего токена для /token_status."""
        tokens = self._load_tokens()
        if not tokens:
            return {'status': 'no_tokens'}

        remaining = int(tokens.get('expires_at', 0) - time.time())
        return {
            'status': 'valid' if remaining > 0 else 'expired',
            'auth_type': tokens.get('auth_type', 'unknown (старый файл — будет перезаписан)'),
            'expires_in_seconds': remaining,
        }
