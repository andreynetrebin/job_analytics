from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Vacancy, SearchQuery, search_query_vacancies  # Импортируйте ваши модели
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка базы данных
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')

DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'

# Настройка пула соединений
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_timeout=30, pool_recycle=1800)
Session = sessionmaker(bind=engine)


def migrate_data():
    with Session() as session:
        # Получаем все вакансии
        vacancies = session.query(Vacancy).all()

        for vacancy in vacancies:
            # Получаем соответствующий поисковый запрос
            search_query = session.query(SearchQuery).filter_by(id=vacancy.search_query_id).first()
            if search_query:
                # Вставляем данные в промежуточную таблицу
                session.execute(
                    search_query_vacancies.insert().values(
                        search_query_id=search_query.id,
                        vacancy_id=vacancy.id
                    )
                )
                print(f"Inserted vacancy {vacancy.external_id} into search_query_vacancies.")

        session.commit()  # Сохраняем изменения


if __name__ == "__main__":
    migrate_data()
