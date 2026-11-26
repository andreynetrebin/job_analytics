import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


def upload_json_to_yandex(filename: str, data: dict, folder_path: str = "/data/job_analytics") -> bool:
    """
    Загружает словарь данных в виде JSON-файла на Яндекс.Диск.
    """
    token = os.getenv("YANDEX_DISK_TOKEN")
    if not token:
        logger.warning("⚠️ YANDEX_DISK_TOKEN не найден в .env. Пропуск загрузки в облако.")
        return False

    headers = {"Authorization": f"OAuth {token}"}

    try:
        # 1. Гарантированно создаем папку (игнорируем ошибку 409, если она уже есть)
        mkdir_url = "https://cloud-api.yandex.net/v1/disk/resources"
        requests.put(mkdir_url, headers=headers, params={"path": folder_path}, verify=False)

        # 2. Получаем ссылку для загрузки файла
        remote_path = f"{folder_path}/{filename}"
        upload_url = "https://cloud-api.yandex.net/v1/disk/resources/upload"
        resp = requests.get(upload_url, headers=headers, params={"path": remote_path, "overwrite": "true"},
                            verify=False)

        if resp.status_code not in (200, 201):
            logger.error(f"❌ Яндекс.Диск отказал в выдаче ссылки: {resp.text}")
            return False

        href = resp.json().get("href")
        if not href:
            logger.error(f"❌ В ответе Яндекса нет ссылки href: {resp.text}")
            return False

        # 3. Загружаем сам файл
        file_content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        put_resp = requests.put(href, data=file_content, verify=False)
        put_resp.raise_for_status()

        logger.info(f"✅ Файл '{filename}' успешно загружен в {remote_path}")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки '{filename}' в облако: {e}")

        # 🛡️ FALLBACK: Сохраняем локально, чтобы данные не потерялись
        local_filename = f"local_backup_{filename}"
        try:
            with open(local_filename, "wb") as f:
                f.write(file_content)
            logger.info(f"💾 Сохранена локальная резервная копия: {os.path.abspath(local_filename)}")
        except Exception as local_err:
            logger.error(f"❌ Не удалось сохранить даже локальную копию: {local_err}")

        return False