import pytest
from datetime import datetime
from database.models import (
    Vacancy, Employer, KeySkill, SalaryHistory, VacancyStatusHistory,
    SearchQuery, Industry, WorkSchedule, WorkFormat,
    vacancy_work_schedules, vacancy_work_formats, employer_industries
)
from core.processing.vacancy_db_loader import upsert_vacancies_to_db, parse_hh_date


# --- Тесты парсинга дат ---

def test_parse_hh_date_valid():
    assert parse_hh_date("2023-10-27T10:00:00+0300") is not None
    assert parse_hh_date("2023-10-27T10:00:00Z") is not None


def test_parse_hh_date_invalid():
    assert parse_hh_date(None) is None
    assert parse_hh_date("not_a_date") is None


# --- Тесты загрузки в БД ---

def test_upsert_new_vacancy_basic(db_session):
    """Тест создания новой вакансии с базовыми полями."""
    raw_data = [{
        "id": "10001",
        "name": "Junior Data Engineer",
        "employer": {"id": "500", "name": "Tech Corp", "area": {"name": "Moscow"}},
        "area": {"name": "Moscow"},
        "experience": {"id": "noExperience", "name": "Нет опыта"},
        "published_at": "2023-10-27T10:00:00+03:00",
        "archived": False,
        "salary": {"from": 1000, "currency": "RUR"}
    }]

    stats = upsert_vacancies_to_db(db_session, raw_data)
    assert stats['inserted'] == 1

    v = db_session.query(Vacancy).filter_by(external_id="10001").first()
    assert v is not None
    assert v.title == "Junior Data Engineer"
    assert v.status == "Активный"
    assert v.employer.name == "Tech Corp"

    # Проверка истории зарплат
    sal = db_session.query(SalaryHistory).filter_by(vacancy_id=v.id, is_active=True).first()
    assert sal is not None
    assert sal.salary_from == 1000

    # Проверка истории статусов
    status_h = db_session.query(VacancyStatusHistory).filter_by(vacancy_id=v.id).first()
    assert status_h is not None
    assert status_h.cur_status == "Активный"


def test_upsert_existing_vacancy(db_session):
    """Тест обновления существующей вакансии (смена зарплаты и статуса)."""
    # 1. Создаем вакансию с НАЧАЛЬНОЙ зарплатой
    upsert_vacancies_to_db(db_session, [{
        "id": "10002",
        "name": "Old Title",
        "employer": {"id": "501", "name": "Old Employer"},
        "archived": False,
        "salary": {"from": 1000, "to": 2000, "currency": "RUR"}  # <-- ДОБАВЛЕНО
    }])

    # 2. Обновляем вакансию (меняем зарплату и статус)
    raw_update = [{
        "id": "10002",
        "name": "New Senior Title",
        "employer": {"id": "501", "name": "Old Employer"},
        "archived": True,
        "salary": {"from": 5000, "to": 8000, "currency": "RUB"}
    }]
    stats = upsert_vacancies_to_db(db_session, raw_update)

    assert stats['inserted'] == 0
    assert stats['updated'] == 1

    v = db_session.query(Vacancy).filter_by(external_id="10002").first()
    assert v.title == "New Senior Title"
    assert v.status == "Архивный"

    # Новая активная зарплата
    active_sal = db_session.query(SalaryHistory).filter_by(vacancy_id=v.id, is_active=True).first()
    assert active_sal is not None
    assert active_sal.salary_from == 5000

    # Старая зарплата должна быть деактивирована
    old_sal = db_session.query(SalaryHistory).filter_by(vacancy_id=v.id, is_active=False).first()
    assert old_sal is not None
    assert old_sal.salary_from == 1000


def test_upsert_with_skills_and_m2m(db_session):
    """Тест связей M2M (Навыки, Графики) и связей Employer-Industry."""
    raw_data = [{
        "id": "10003", "name": "Skill Test",
        "employer": {
            "id": "502", "name": "Industries Corp",
            "industries": [{"id": "1", "name": "IT"}, {"id": "2", "name": "Banking"}]
        },
        "key_skills": [{"name": "Python"}, {"name": "SQL"}],
        "work_schedule": [{"id": "fullDay", "name": "Полный день"}],
        "work_format": [{"id": "remote", "name": "Удаленная работа"}],
        "archived": False
    }]

    upsert_vacancies_to_db(db_session, raw_data)

    v = db_session.query(Vacancy).filter_by(external_id="10003").first()

    # Проверка навыков
    assert len(v.key_skill_history) == 2
    skill_names = {ksh.key_skill.name for ksh in v.key_skill_history}
    assert "Python" in skill_names

    # Проверка графиков
    schedules = db_session.query(vacancy_work_schedules).filter_by(vacancy_id=v.id).all()
    assert len(schedules) == 1

    # Проверка отраслей работодателя
    emp = v.employer
    industries = db_session.query(employer_industries).filter_by(employer_id=emp.id).all()
    assert len(industries) == 2


def test_link_to_search_query(db_session):
    """Тест привязки вакансии к поисковому запросу."""
    # Создаем запрос
    sq = SearchQuery(query="Test Query", initiator="Me", email="me@test.com", is_active=True)
    db_session.add(sq)
    db_session.flush()

    raw_data = [{"id": "10004", "name": "Query Link Test", "employer": {"id": "503", "name": "E"}}]

    upsert_vacancies_to_db(db_session, raw_data, search_query_id=sq.id)

    v = db_session.query(Vacancy).filter_by(external_id="10004").first()
    assert len(v.search_queries) == 1
    assert v.search_queries[0].query == "Test Query"