import pytest
import responses
from core.ingest.hh_client import HHClient

@responses.activate
def test_fetch_raw_vacancies_success():
    """Тест успешного сбора сырых данных с пагинацией."""
    # Мок первой страницы
    responses.add(
        responses.GET,
        "https://api.hh.ru/vacancies?text=Python&per_page=2&page=0",
        json={
            "items": [{"id": "1", "name": "Python Dev 1"}, {"id": "2", "name": "Python Dev 2"}],
            "found": 3,
            "pages": 2
        },
        status=200
    )
    # Мок второй страницы
    responses.add(
        responses.GET,
        "https://api.hh.ru/vacancies?text=Python&per_page=2&page=1",
        json={
            "items": [{"id": "3", "name": "Python Dev 3"}],
            "found": 3,
            "pages": 2
        },
        status=200
    )

    client = HHClient()
    result = client.fetch_raw_vacancies(query="Python", per_page=2, max_pages=5)

    assert result.success is True
    assert result.query == "Python"
    assert result.total_found == 3
    assert result.total_fetched == 3
    assert len(result.raw_vacancies) == 3
    assert result.raw_vacancies[0]["name"] == "Python Dev 1"

@responses.activate
def test_fetch_raw_vacancies_403_forbidden():
    """Тест корректной обработки 403 ошибки без падения."""
    responses.add(
        responses.GET,
        "https://api.hh.ru/vacancies?text=Java&per_page=20&page=0",
        json={"errors": [{"type": "forbidden"}]},
        status=403
    )

    client = HHClient()
    result = client.fetch_raw_vacancies(query="Java", per_page=20)

    assert result.success is False
    assert "403 Forbidden" in result.error_message
    assert result.total_fetched == 0