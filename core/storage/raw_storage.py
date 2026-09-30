import os
import json
import logging
import requests
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class RawStorage:
    """Базовый интерфейс для хранения сырых данных."""

    def save(self, query: str, vacancies: List[Dict[str, Any]]) -> str:
        raise NotImplementedError("Метод save должен быть реализован в наследнике")


class LocalRawStorage(RawStorage):
    """Сохраняет сырые JSON-данные локально на диск."""

    def __init__(self, base_dir: str = "vacancies_data"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def save(self, query: str, vacancies: List[Dict[str, Any]]) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        # ✅ ЗАМЕНА: заменяем все недопустимые символы и пробелы на нижнее подчеркивание
        safe_query = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in query).strip('_')
        filename = f"vacancies_{safe_query}_{timestamp}.json"
        filepath = os.path.join(self.base_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(vacancies, f, ensure_ascii=False, indent=2)

        # ✅ ЗАМЕНА: убраны эмодзи, чтобы избежать UnicodeEncodeError в Windows консоли
        logger.info(f"[OK] Сырые данные сохранены локально: {filepath}")
        return filepath


class YandexDiskStorage(RawStorage):
    """Загружает сырые JSON-данные на Яндекс.Диск через REST API."""

    def __init__(self, token: str, remote_dir: str = "/job_analytics/raw_data"):
        self.token = token
        self.remote_dir = remote_dir
        self.api_url = "https://cloud-api.yandex.net/v1/disk/resources"

    def save(self, query: str, vacancies: List[Dict[str, Any]]) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        safe_query = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in query).strip('_')
        filename = f"vacancies_{safe_query}_{timestamp}.json"
        remote_path = f"{self.remote_dir}/{filename}"

        headers = {"Authorization": f"OAuth {self.token}"}

        try:
            # 1. Получаем временную ссылку (href) для загрузки файла
            upload_url = f"{self.api_url}/upload?path={remote_path}&overwrite=true"
            response = requests.get(upload_url, headers=headers, timeout=10)
            response.raise_for_status()
            href = response.json().get("href")

            if not href:
                raise ValueError("Не удалось получить ссылку для загрузки с Яндекс.Диска")

            # 2. Загружаем файл по полученной ссылке (Яндекс требует PUT запрос с телом файла)
            file_content = json.dumps(vacancies, ensure_ascii=False).encode('utf-8')
            upload_response = requests.put(href, data=file_content, timeout=30)
            upload_response.raise_for_status()

            logger.info(f"[OK] Сырые данные успешно загружены на Яндекс.Диск: {remote_path}")
            return remote_path

        except requests.exceptions.RequestException as e:
            # ✅ ЗАМЕНА: убран эмодзи
            logger.error(f"[ERROR] Ошибка при загрузке на Яндекс.Диск: {e}")
            raise