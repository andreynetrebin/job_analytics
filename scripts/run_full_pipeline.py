import os
import sys
import json
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.ingest.hh_client import HHClient
from core.storage.raw_storage import YandexDiskStorage
from core.processing.vacancy_full_loader import upsert_full_batch
from database.database import Session
from hh_auth import HHAuthManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    # Настройки
    query_text = os.getenv("TARGET_QUERY", "Data Engineer")
    limit = int(os.getenv("LIMIT", "0"))  # 0 = без лимита
    yandex_token = os.getenv("YANDEX_DISK_TOKEN")

    logger.info(f"🚀 Старт полного пайплайна для: '{query_text}'")
    if limit > 0: logger.info(f"⚠️ Включен режим LIMIT={limit}")

    # 1. Авторизация
    auth_manager = HHAuthManager()
    hh_token = auth_manager.get_valid_token()

    correct_user_agent = os.getenv("HH_USER_AGENT", "JobAnalytics/1.0 (andrew89s@mail.ru)")
    logger.info(f"📌 Используем User-Agent: {correct_user_agent}")

    client = HHClient(user_agent=correct_user_agent)
    client.set_token(hh_token)

    # 2. Ingestion (Быстрый сбор списка)
    logger.info("📡 Этап 1: Сбор списка вакансий (Search API)...")
    search_result = client.fetch_raw_vacancies(query=query_text, per_page=100, max_pages=10)

    if not search_result.success:
        logger.error("❌ Ошибка сбора списка");
        sys.exit(1)

    vacancy_ids = [str(v['id']) for v in search_result.raw_vacancies]
    if limit > 0: vacancy_ids = vacancy_ids[:limit]
    logger.info(f"✅ Найдено {len(vacancy_ids)} вакансий для обогащения.")

    # 3. Enrichment (Детализация)
    logger.info("🔍 Этап 2: Обогащение данными (Details API)...")
    enriched_data = []

    for i, vid in enumerate(vacancy_ids):
        logger.info(f"[{i + 1}/{len(vacancy_ids)}] Загрузка деталей вакансии {vid}...")
        v_details = client.get_vacancy_details(vid)
        e_details = {}
        if v_details and 'employer' in v_details:
            e_details = client.get_employer_details(str(v_details['employer'].get('id')))

        enriched_data.append({'vacancy': v_details, 'employer': e_details})
        time.sleep(1.5)  # Rate Limit

    if not enriched_data:
        logger.warning("⚠️ Нет данных для сохранения");
        sys.exit(0)

    # 3. Сохранение в Облако (Один общий JSON)
    logger.info("☁️ Этап 3: Сохранение полного JSON в Яндекс.Диск...")
    if yandex_token:
        try:
            tmp_file = f"full_data_{query_text.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            remote_path = f"/data/job_analytics/full_data/{tmp_file}"

            headers = {"Authorization": f"OAuth {yandex_token}"}

            # 1. Гарантированное создание папок по очереди (используем params для надежности)
            for folder in ["/job_analytics", "/job_analytics/full_data"]:
                mkdir_url = "https://cloud-api.yandex.net/v1/disk/resources"
                resp = requests.put(mkdir_url, headers=headers, params={"path": folder}, verify=False)
                if resp.status_code in (201, 409):  # 201 = создано, 409 = уже существует
                    logger.info(f"📁 Папка {folder} готова (Статус API: {resp.status_code})")
                else:
                    logger.warning(f"⚠️ Не удалось создать/проверить папку {folder}. Ответ API: {resp.text}")

            # 2. Получаем ссылку на загрузку файла
            upload_url = "https://cloud-api.yandex.net/v1/disk/resources/upload"
            resp = requests.get(upload_url, headers=headers, params={"path": remote_path, "overwrite": "true"},
                                verify=False)

            if resp.status_code not in (200, 201):
                logger.error(f"❌ Яндекс.Диск отказал в выдаче ссылки. Статус: {resp.status_code}, Ответ: {resp.text}")
                raise Exception("Yandex Disk API refused upload link")

            href = resp.json().get("href")
            if not href:
                logger.error(f"❌ В ответе Яндекса нет ссылки href. Ответ: {resp.text}")
                raise Exception("No href in Yandex Disk response")

            # 3. Формируем итоговый JSON
            full_json_data = {
                "query": query_text,
                "timestamp": datetime.now().isoformat(),
                "count": len(enriched_data),
                "data": enriched_data
            }
            file_content = json.dumps(full_json_data, ensure_ascii=False, indent=2).encode('utf-8')

            # 4. Загружаем файл
            put_resp = requests.put(href, data=file_content, verify=False)
            put_resp.raise_for_status()

            logger.info(f"✅ Файл успешно загружен: {remote_path}")
            logger.info(f"🔗 Проверьте в браузере: https://disk.yandex.ru/client/disk{remote_path}")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки в облако: {e}")
            # 🛡️ FALLBACK: Сохраняем локально, чтобы данные не потерялись!
            local_path = f"backup_{tmp_file}"
            with open(local_path, 'wb') as f:
                f.write(file_content)
            logger.info(f"💾 ДАННЫЕ СОХРАНЕНЫ ЛОКАЛЬНО как резервная копия: {os.path.abspath(local_path)}")
    else:
        logger.warning("⚠️ Нет токена Яндекс.Диска, данные будут сохранены только в БД.")

    # 4. Укладка в БД
    logger.info("💾 Этап 4: Укладка данных в MySQL...")
    db_session = Session()
    try:
        upsert_full_batch(db_session, enriched_data)
        logger.info("🎉 Пайплайн успешно завершен! Данные в БД и Облаке.")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        db_session.rollback()
    finally:
        db_session.close()


if __name__ == "__main__":
    main()