import os
import sys
import logging
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Session
from core.processing.sql_analytics import JobAnalyticsSQL
from core.llm.llm_analyzer import create_analyzer_from_env

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    load_dotenv()
    query_text = os.getenv("TARGET_QUERY", "Data Engineer")
    custom_prompt = os.getenv("LLM_CUSTOM_PROMPT")

    # Режим можно переключать: "online" (по умолчанию) или "offline"
    mode = os.getenv("LLM_MODE", "online")

    logger.info(f"🚀 Запуск LLM-аналитики (Режим: {mode.upper()}) для: '{query_text}'")

    db_session = Session()
    try:
        # 1. Сбор контекста
        analytics = JobAnalyticsSQL(db_session)
        context = analytics.get_full_context_for_llm(query_text)

        print("\n" + "=" * 60)
        print("📊 SQL-КОНТЕКСТ:")
        print("=" * 60)
        print(context)
        print("=" * 60)

        # 2. Инициализация провайдеров из .env
        analyzer = create_analyzer_from_env()

        # 3. Генерация отчета
        insight = analyzer.generate_report(context, custom_prompt=custom_prompt, mode=mode)

        print("\n" + "=" * 60)
        print(f"🤖 ОТВЕТ LLM [{mode.upper()}]:")
        print("=" * 60)
        print(insight)
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"❌ Ошибка пайплайна: {e}")
    finally:
        db_session.close()


if __name__ == "__main__":
    main()