import os
import sys
import logging
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.ingest.hh_client import HHClient
from core.processing.vacancy_db_loader import upsert_vacancies_to_db
from database.database import Session
from hh_auth import HHAuthManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    load_dotenv()

    search_query = os.getenv("TARGET_QUERY", "Data Engineer")
    logger.info(f"🚀 Запуск полного пайплайна: Сбор -> БД для '{search_query}'")

    # 1. Авторизация
    auth_manager = HHAuthManager()
    try:
        hh_token = auth_manager.get_valid_token()
        logger.info("🔑 Токен HH получен")
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации: {e}")
        sys.exit(1)

    # 2. Сбор данных
    user_agent = os.getenv("HH_USER_AGENT", "JobAnalytics/1.0 (andrew89s@mail.ru)")
    logger.info(f"📌 Используем User-Agent: {user_agent}")
    client = HHClient(user_agent=user_agent)
    client.set_token(hh_token)

    logger.info("📡 Запрос к API HeadHunter (макс. 2000 вакансий)...")
    # Собираем данные. Внимание: search endpoint возвращает "короткие" вакансии.
    # Если key_skills и industries критичны, их нужно подгружать отдельно в цикле
    # (это займет много времени). Текущий loader безопасно пропустит отсутствующие поля.
    result = client.fetch_raw_vacancies(query=search_query, per_page=100, max_pages=20)

    if not result.success or result.total_fetched == 0:
        logger.error(f"❌ Не удалось получить данные: {result.error_message}")
        sys.exit(1)

    logger.info(f"✅ Собрано {result.total_fetched} вакансий. Сохранение в БД...")

    # 3. Сохранение в БД
    # Мы можем передать None вместо search_query_id, если не хотим линковать к конкретному запросу,
    # или найти ID запроса в БД. Для простоты пока None.
    db_session = Session()
    try:
        stats = upsert_vacancies_to_db(db_session, result.raw_vacancies, search_query_id=None)
        logger.info("=" * 50)
        logger.info("🎉 Пайплайн завершен успешно!")
        logger.info(
            f"📊 Статистика: Добавлено: {stats['inserted']}, Обновлено: {stats['updated']}, Ошибок: {stats['errors']}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении в БД: {e}")
        db_session.rollback()
        sys.exit(1)
    finally:
        db_session.close()


if __name__ == "__main__":
    main()