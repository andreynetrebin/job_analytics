import os
import sys
from dotenv import load_dotenv

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import Session
from database.models import SearchQuery


def main():
    load_dotenv()
    db_session = Session()

    # Данные для 2 тестовых активных запросов
    test_queries = [
        {
            "query": "Data Engineer",
            "initiator": "System Test",
            "email": "test@example.com",
            "is_active": True
        },
        {
            "query": "Python Backend Developer",
            "initiator": "System Test",
            "email": "test@example.com",
            "is_active": True
        }
    ]

    print("🔄 Проверка и создание тестовых поисковых запросов...")
    for tq in test_queries:
        # Проверяем, нет ли уже такого запроса в БД
        existing = db_session.query(SearchQuery).filter_by(query=tq["query"]).first()

        if not existing:
            new_query = SearchQuery(**tq)
            db_session.add(new_query)
            print(f"✅ Добавлен новый запрос: '{tq['query']}'")
        else:
            # Если запрос есть, но был деактивирован, включаем его обратно
            if not existing.is_active:
                existing.is_active = True
                print(f"🔄 Активирован существующий запрос: '{tq['query']}'")
            else:
                print(f"ℹ️ Запрос '{tq['query']}' уже активен.")

    db_session.commit()
    print("🎉 Тестовые запросы успешно созданы/обновлены в БД!")
    db_session.close()


if __name__ == "__main__":
    main()