import os
import re
import sys
import pytest
import responses
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_app import app as flask_app
from database.models import Base
from database.database import Session as AppSession  # Импортируем оригинальный Session


@pytest.fixture(scope="session")
def app():
    flask_app.config.update({
        "TESTING": True,
        "ADMIN_PASSWORD": "test_password",
        "APP_EMAIL": "test@example.com"
    })
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Создает изолированную in-memory SQLite БД для каждого теста."""
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)

    # Создаем фабрику сессий, привязанную к тестовому движку
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def mock_hh_api():
    """Мокирует ВСЕ запросы к API HH, включая получение токена."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        # 1. МОК ПОЛУЧЕНИЯ ТОКЕНА
        rsps.add(
            responses.POST,
            "https://api.hh.ru/token",
            json={"access_token": "test_mock_token_123", "token_type": "bearer", "expires_in": 1209600},
            status=200
        )
        # 2. МОК СПИСКА ВАКАНСИЙ
        rsps.add(
            responses.GET,
            "https://api.hh.ru/vacancies",
            json={
                "items": [{
                    "id": "12345678", "name": "Python Developer",
                    "area": {"name": "Москва"}, "employer": {"id": "1", "name": "Test Co"},
                    "published_at": "2026-09-25T10:00:00+03:00", "archived": False,
                    "salary_range": {"from": 100000, "to": 150000, "currency": "RUB"}
                }],
                "found": 1, "pages": 1
            },
            status=200
        )
        # 3. МОК ДЕТАЛЕЙ ВАКАНСИИ (для ID 12345678)
        rsps.add(
            responses.GET,
            "https://api.hh.ru/vacancies/12345678",
            json={
                "id": "12345678", "name": "Python Developer",
                "experience": {"id": "1", "name": "Опыт"},
                "professional_roles": [{"id": "1", "name": "Роль"}],
                "employment_form": {"id": "1", "name": "Форма"},
                "working_hours": [{"id": "1", "name": "Часы"}],
                "key_skills": [{"name": "Python"}],
                "published_at": "2026-09-25T10:00:00+03:00",
                "initial_created_at": "2026-09-25T09:00:00+03:00",
                "archived": False
            },
            status=200
        )
        # 4. МОК ДЕТАЛЕЙ ВАКАНСИИ (для ID 999999, используется в test_process_vacancy_revive)
        rsps.add(
            responses.GET,
            "https://api.hh.ru/vacancies/999999",
            json={
                "id": "999999", "name": "Test Vacancy",
                "experience": {"id": "1", "name": "Опыт"},
                "professional_roles": [{"id": "1", "name": "Роль"}],
                "employment_form": {"id": "1", "name": "Форма"},
                "working_hours": [{"id": "1", "name": "Часы"}],
                "key_skills": [{"name": "Python"}],
                "published_at": "2026-09-25T10:00:00+03:00",
                "initial_created_at": "2026-09-25T09:00:00+03:00",
                "archived": False
            },
            status=200
        )
        # 5. МОК РАБОТОДАТЕЛЯ
        rsps.add(
            responses.GET,
            "https://api.hh.ru/employers/1",
            json={
                "name": "Test Co", "open_vacancies": 5, "accredited_it_employer": True,
                "area": {"name": "Москва"}, "industries": [{"id": "1", "name": "IT"}]
            },
            status=200
        )
        yield rsps

