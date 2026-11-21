import os
import sys
import logging
from dotenv import load_dotenv

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.ingest.hh_client import HHClient
from core.storage.raw_storage import YandexDiskStorage
from hh_auth import HHAuthManager  # Используем существующий менеджер авторизации

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    load_dotenv()

    yandex_token = os.getenv("YANDEX_DISK_TOKEN")
    if not yandex_token:
        logger.error("❌ Не найден YANDEX_DISK_TOKEN")
        sys.exit(1)

    test_query = "Data Engineer"
    logger.info(f"🚀 Запуск тестового пайплайна: '{test_query}'")

    # 1. Получаем валидный токен через ваш hh_auth (по CLIENT_ID/CLIENT_SECRET)
    auth_manager = HHAuthManager()
    try:
        hh_token = auth_manager.get_valid_token()
        logger.info("🔑 Токен HH успешно получен/обновлен")
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации HH: {e}")
        logger.info("💡 Убедитесь, что CLIENT_ID и CLIENT_SECRET указаны в .env или настройках PA")
        sys.exit(1)

    # 2. Инициализируем клиент с правильным User-Agent и токеном
    hh_user_agent = os.getenv("HH_USER_AGENT", "MyAnalytics/1.0 (dev@example.com)")
    client = HHClient(user_agent=hh_user_agent)
    client.set_token(hh_token)

    logger.info("📡 Запрос к API HeadHunter...")
    result = client.fetch_raw_vacancies(query=test_query, per_page=20, max_pages=2)

    if not result.success:
        logger.error(f"❌ Ошибка сбора: {result.error_message}")
        sys.exit(1)

    logger.info(f"✅ Собрано {result.total_fetched} вакансий из {result.total_found}")

    # 3. Загрузка в Яндекс.Диск
    logger.info("☁️ Загрузка на Яндекс.Диск...")
    storage = YandexDiskStorage(
        token=yandex_token,
        remote_dir=os.getenv("YANDEX_DISK_DIR", "/job_analytics/raw_data")
    )

    try:
        remote_path = storage.save(query=test_query, vacancies=result.raw_vacancies)
        logger.info(f"✅ Успешно сохранено: {remote_path}")
        logger.info(f"🔗 https://disk.yandex.ru/client/disk{remote_path}")
    except Exception as e:
        logger.error(f"❌ Ошибка Яндекс.Диск: {e}")
        sys.exit(1)

    logger.info("🏁 Тестовый пайплайн завершен!")

if __name__ == "__main__":
    main()
