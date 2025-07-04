import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from dotenv import load_dotenv
from sqlalchemy import inspect

# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем переменные окружения
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')

# Формируем строку подключения
DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'

# Создаем движок и сессию
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def init_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def check_db_exists():
    """Проверка существования базы данных."""
    inspector = inspect(engine)
    return 'vacancies' in inspector.get_table_names()  # Проверяем, существует ли таблица 'vacancies'
