import pytest
from database.models import Vacancy, Employer, KeySkill, VacancyStatusHistory, SalaryHistory
from core.processing.vacancy_full_loader import process_full_vacancy

# Фиктивные данные полного ответа API
FULL_VACANCY_JSON = {
    "id": "9999",
    "name": "Senior Data Engineer",
    "archived": False,
    "published_at": "2023-10-27T10:00:00+03:00",
    "employer": {"id": "888", "name": "Tech Corp"},
    "experience": {"id": "exp1", "name": "Senior"},
    "professional_roles": [{"id": "role1", "name": "Engineer"}],
    "employment_form": {"id": "form1", "name": "Full"},
    "working_hours": [{"id": "wh1", "name": "Day"}],
    "salary": {"from": 300000, "currency": "RUB"},
    "key_skills": [{"name": "Python"}, {"name": "SQL"}],
    "work_schedule": [{"id": "sch1", "name": "FullDay"}]
}

FULL_EMPLOYER_JSON = {
    "id": "888",
    "name": "Tech Corp Updated",
    "accredited_it_employer": True,
    "industries": [{"id": "ind1", "name": "IT"}]
}


def test_full_vacancy_upsert(db_session):
    """Тест полной укладки с навыками, зарплатой и работодателем."""
    process_full_vacancy(db_session, FULL_VACANCY_JSON, FULL_EMPLOYER_JSON)

    v = db_session.query(Vacancy).filter_by(external_id="9999").first()
    assert v is not None
    assert v.title == "Senior Data Engineer"

    # Работодатель
    assert v.employer.accredited_it_employer is True

    # Навыки
    skills = db_session.query(KeySkill).filter(KeySkill.name.in_(["Python", "SQL"])).all()
    assert len(skills) == 2

    # Зарплата
    assert v.salary_history[0].salary_from == 300000


def test_full_vacancy_update(db_session):
    """Тест обновления существующей вакансии (смена зарплаты)."""
    # Сначала создаем
    process_full_vacancy(db_session, FULL_VACANCY_JSON, FULL_EMPLOYER_JSON)

    # Обновляем (меняем зарплату)
    updated_json = FULL_VACANCY_JSON.copy()
    updated_json['salary'] = {"from": 500000, "currency": "RUB"}

    process_full_vacancy(db_session, updated_json, FULL_EMPLOYER_JSON)

    v = db_session.query(Vacancy).filter_by(external_id="9999").first()
    # Проверяем историю зарплат (должно быть 2 записи: старая неактивна, новая активна)
    salaries = db_session.query(SalaryHistory).filter_by(vacancy_id=v.id).all()
    assert len(salaries) == 2
    assert any(s.is_active and s.salary_from == 500000 for s in salaries)