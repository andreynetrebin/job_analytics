import os
import sys
import time
import logging
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Session
from database.models import SearchQuery
from core.ingest.hh_client import HHClient
from core.processing.vacancy_full_loader import upsert_full_batch
from core.processing.sql_analytics import JobAnalyticsSQL
from core.llm.llm_analyzer import create_analyzer_from_env
from hh_auth import HHAuthManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def process_single_query(db_session, sq: SearchQuery, client: HHClient, limit: int = 0):
    """Обрабатывает один поисковый запрос: сбор, обогащение, сохранение и LLM-аналитика."""
    logger.info(f"▶️ Начало обработки запроса: '{sq.query}' (ID: {sq.id})")

    # 1. Ingestion (Быстрый сбор списка)
    logger.info(f"   📡 Сбор списка вакансий для '{sq.query}'...")
    search_result = client.fetch_raw_vacancies(query=sq.query, per_page=50, max_pages=20)

    if not search_result.success or not search_result.raw_vacancies:
        logger.warning(f"   ⚠️ Вакансии не найдены или ошибка API: {search_result.error_message}")
        return

    vacancy_ids = [str(v['id']) for v in search_result.raw_vacancies]
    if limit > 0:
        vacancy_ids = vacancy_ids[:limit]
        logger.info(f"   ⚠️ Режим LIMIT={limit}. Обработаем только первые {limit} вакансий.")

    # 2. Enrichment (Детализация)
    logger.info(f"   🔍 Обогащение {len(vacancy_ids)} вакансий деталями...")
    enriched_data = []

    for i, vid in enumerate(vacancy_ids):
        v_details = client.get_vacancy_details(vid)
        e_details = {}
        if v_details and 'employer' in v_details:
            e_details = client.get_employer_details(str(v_details['employer'].get('id')))

        enriched_data.append({'vacancy': v_details, 'employer': e_details})
        time.sleep(1.5)  # Rate limiting для HH API

    if not enriched_data:
        logger.warning("   ⚠️ Нет данных для сохранения после обогащения.")
        return

    # 3. Сохранение в БД с привязкой к SearchQuery
    logger.info(f"   💾 Сохранение {len(enriched_data)} обогащенных вакансий в БД...")
    try:
        stats = upsert_full_batch(db_session, enriched_data, search_query_id=sq.id)
        logger.info(
            f"   ✅ Успешно: Добавлено {stats['inserted']}, Обновлено {stats['updated']}, Ошибок {stats['errors']}")
    except Exception as e:
        logger.error(f"   ❌ Ошибка при сохранении в БД: {e}")
        db_session.rollback()
        return  # Прерываем обработку этого запроса, переходим к следующему

    # 4. 🧠 LLM-Аналитика и отправка на почту (ОТ ВСЕХ доступных онлайн-провайдеров)
    logger.info("   🧠 Генерация аналитических отчетов через доступные LLM...")
    try:
        analytics = JobAnalyticsSQL(db_session)
        context = analytics.get_full_context_for_llm(sq.query)

        analyzer = create_analyzer_from_env()
        custom_prompt = os.getenv("LLM_CUSTOM_PROMPT", "")

        # Определяем, какие онлайн-провайдеры настроены и готовы к работе
        active_providers = []
        if analyzer.gigachat:
            active_providers.append(("gigachat", "GigaChat"))
        if analyzer.openrouter:
            active_providers.append(("openrouter", "OpenRouter"))

        if not active_providers:
            logger.warning("   ⚠️ Ни один онлайн LLM-провайдер не настроен в .env")
        else:
            from core.utils.mailer import send_email_report

            for mode, provider_name in active_providers:
                try:
                    logger.info(f"   🔄 Запрос к {provider_name}...")
                    insight = analyzer.generate_report(context, custom_prompt=custom_prompt, mode=mode)

                    # Вывод в консоль
                    print("\n" + "=" * 70)
                    print(f"🤖 LLM-ОТЧЕТ ({provider_name}) ДЛЯ ЗАПРОСА: '{sq.query}'")
                    print("=" * 70)
                    print(insight)
                    print("=" * 70 + "\n")

                    # 📧 ОТПРАВКА НА ПОЧТУ (с указанием провайдера в теме письма)
                    email_subject_query = f"[{provider_name}] {sq.query}"
                    send_email_report(email_subject_query, insight)

                except Exception as e:
                    logger.warning(f"   ⚠️ Не удалось получить отчет от {provider_name}: {e}")

    except Exception as e:
        logger.warning(f"   ⚠️ Критическая ошибка на этапе LLM-аналитики: {e}")


def main():
    load_dotenv()
    limit = int(os.getenv("LIMIT", "0"))

    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК ОБРАБОТКИ АКТИВНЫХ ПОИСКОВЫХ ЗАПРОСОВ")
    if limit > 0:
        logger.info(f"⚠️ ВКЛЮЧЕН РЕЖИМ ТЕСТИРОВАНИЯ: LIMIT={limit} вакансий на запрос")
    logger.info("=" * 60)

    auth_manager = HHAuthManager()
    try:
        hh_token = auth_manager.get_valid_token()
        logger.info("🔑 Токен HH успешно получен")
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации HH: {e}")
        return

    hh_user_agent = os.getenv("HH_USER_AGENT", "JobAnalytics/1.0 (andrew89s@mail.ru)")
    client = HHClient(user_agent=hh_user_agent)
    client.set_token(hh_token)

    db_session = Session()
    try:
        active_queries = db_session.query(SearchQuery).filter_by(is_active=True).all()

        if not active_queries:
            logger.info("ℹ️ Активных поисковых запросов (is_active=True) не найдено. Завершение.")
            return

        logger.info(f"📋 Найдено активных запросов: {len(active_queries)}")

        for sq in active_queries:
            process_single_query(db_session, sq, client, limit=limit)
            time.sleep(3)  # Пауза между разными запросами

        logger.info("=" * 60)
        logger.info("🎉 ОБРАБОТКА ВСЕХ АКТИВНЫХ ЗАПРОСОВ ЗАВЕРШЕНА!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в оркестраторе: {e}")
        db_session.rollback()
    finally:
        db_session.close()


if __name__ == "__main__":
    main()