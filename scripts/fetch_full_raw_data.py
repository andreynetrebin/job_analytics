import os
import sys
import logging
from dotenv import load_dotenv

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.ingest.hh_client import HHClient
from core.storage.raw_storage import YandexDiskStorage
from hh_auth import HHAuthManager

# Настраиваем логирование (INFO для продакшена, чтобы не спамить в консоль)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    load_dotenv()

    # 1. Проверка обязательных переменных окружения
    yandex_token = os.getenv("YANDEX_DISK_TOKEN")
    if not yandex_token:
        logger.error("❌ Не найден YANDEX_DISK_TOKEN в переменных окружения")
        sys.exit(1)

    # Настраиваемый поисковый запрос (по умолчанию Data Engineer)
    search_query = os.getenv("TARGET_QUERY", "Data Engineer")
    
    logger.info("="*60)
    logger.info(f"🚀 ЗАПУСК ПОЛНОГО СБОРА ДАННЫХ")
    logger.info(f"🔍 Поисковый запрос: '{search_query}'")
    logger.info(f"⚙️ Параметры: per_page=100, max_pages=20 (лимит API ~2000 вакансий)")
    logger.info("="*60)

    # 2. Авторизация в HeadHunter
    auth_manager = HHAuthManager()
    try:
        hh_token = auth_manager.get_valid_token()
        logger.info("🔑 Токен HH успешно получен/обновлен")
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации HH: {e}")
        sys.exit(1)

    # 3. Инициализация клиента сбора данных
    hh_user_agent = os.getenv("HH_USER_AGENT", "JobAnalytics/1.0 (andrew89s@mail.ru)")
    client = HHClient(user_agent=hh_user_agent)
    client.set_token(hh_token)

    # 4. Сбор сырых данных (максимальные разрешенные лимиты)
    logger.info("📡 Начинаем масштабный запрос к API HeadHunter (это может занять 1-2 минуты)...")
    result = client.fetch_raw_vacancies(
        query=search_query, 
        per_page=100,      # Максимум для HH API
        max_pages=20       # 100 * 20 = 2000 (абсолютный лимит выдачи HH)
    )

    if not result.success:
        logger.error(f"❌ Критическая ошибка при сборе данных: {result.error_message}")
        sys.exit(1)

    logger.info(f"✅ Успешно собрано {result.total_fetched} вакансий из {result.total_found} доступных")

    if result.total_fetched == 0:
        logger.warning("⚠️ Вакансии не найдены. Проверьте поисковый запрос.")
        sys.exit(0)

    # 5. Сохранение в Яндекс.Диск
    logger.info("☁️ Начинаем загрузку сырых данных на Яндекс.Диск...")
    storage = YandexDiskStorage(
        token=yandex_token,
        remote_dir=os.getenv("YANDEX_DISK_DIR", "/job_analytics/raw_data")
    )

    try:
        remote_path = storage.save(query=search_query, vacancies=result.raw_vacancies)
        logger.info("="*60)
        logger.info("🎉 ПОЛНЫЙ СБОР ЗАВЕРШЕН УСПЕШНО!")
        logger.info(f"📁 Файл сохранен: {remote_path}")
        logger.info(f"🔗 Ссылка для проверки: https://disk.yandex.ru/client/disk{remote_path}")
        logger.info("="*60)
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке на Яндекс.Диск: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
