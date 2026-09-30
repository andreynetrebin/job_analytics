import pytest
import responses
from job_analytics import process_vacancy, fetch_vacancies
from database.models import SearchQuery, Vacancy


def test_process_vacancy_creates_record(db_session, mock_hh_api):
    """Тест, что process_vacancy корректно создает запись в БД из JSON-ответа."""
    mock_query = SearchQuery(id=99, query="Test Query", email="test@test.com", initiator="TestUser", is_active=True)
    db_session.add(mock_query)
    db_session.commit()

    vacancy_data = {
        "id": "12345678",
        "name": "Python Developer",
        "employer": {"id": "1", "name": "Test Company"},
        "archived": False
    }

    # Вызываем тестируемую функцию
    process_vacancy(vacancy_data, db_session, mock_query)

    # Проверяем результат в БД
    vacancy = db_session.query(Vacancy).filter_by(external_id="12345678").first()
    assert vacancy is not None
    assert vacancy.title == "Python Developer"
    assert vacancy.status == "Активный"


def test_fetch_vacancies_handles_403_gracefully(db_session, mock_hh_api):
    """Тест, что скрипт не падает, если HH возвращает 403 Forbidden."""
    # Перенастраиваем мок на возврат 403 ошибки
    mock_hh_api.reset()
    mock_hh_api.add(
        responses.GET,
        "https://api.hh.ru/vacancies",
        json={"errors": [{"type": "forbidden"}]},
        status=403
    )

    # ✅ ПОЛНОСТЬЮ ЗАМЕНИТЕ ЭТУ СТРОКУ:
    mock_query = SearchQuery(id=99, query="Test Query", email="test@test.com", initiator="TestUser", is_active=True)

    db_session.add(mock_query)
    db_session.commit()

    # Функция должна выполниться без выброса необработанных исключений
    try:
        fetch_vacancies(db_session, mock_query)
    except Exception as e:
        import pytest
        pytest.fail(f"fetch_vacancies raised an exception unexpectedly: {e}")