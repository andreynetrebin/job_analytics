import os
import sys
from dotenv import load_dotenv

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import engine
from database.models import Base

def main():
    load_dotenv()
    print("🔄 Проверка и создание таблиц в базе данных...")
    try:
        # Создаем все таблицы, определенные в database/models.py
        # Если таблицы уже существуют, эта команда ничего не сломает
        Base.metadata.create_all(bind=engine)
        print("✅ База данных успешно инициализирована! Все таблицы созданы.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")

if __name__ == "__main__":
    main()