import json
from unittest.mock import patch
from database.models import SearchQuery

def test_index_route(client):
    """Тест главной страницы."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"HH API" in response.data  # Проверка наличия контента из шаблона


def test_create_search_query(client, db_session):
    """Тест создания нового поискового запроса."""
    payload = {
        "query": "Data Engineer",
        "initiator": "Andrey",
        "email": "test@example.com"
    }

    # ✅ Подменяем импорт Session в flask_app на нашу тестовую db_session
    with patch('flask_app.Session', return_value=db_session):
        response = client.post(
            '/search_queries',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 201

        # Проверяем, что данные попали в тестовую БД
        queries = db_session.query(SearchQuery).all()
        assert len(queries) == 1
        assert queries[0].query == "Data Engineer"
        assert queries[0].is_active is False


def test_get_vacancies_with_mock(client, mock_hh_api):
    """Тест получения вакансий с мокированным API HH."""
    # Сначала создадим активный запрос, чтобы скрипт его нашел
    # (В реальном тесте лучше использовать фикстуру для создания запроса)
    # Для упрощения проверим, что маршрут /test_vacancies работает с моком

    response = client.get('/test_vacancies')
    assert response.status_code == 200

    data = response.get_json()
    assert data['✅ status'] == 'OK'
    assert data['📊 total_found'] == 1
    assert len(data['🎯 vacancies']) == 1
    assert data['🎯 vacancies'][0]['title'] == 'Python Developer'