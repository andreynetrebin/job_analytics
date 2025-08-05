from flask import Blueprint, jsonify
from sqlalchemy import func, distinct
from database.models import Vacancy, KeySkill, KeySkillHistory, WorkFormat, ExperienceLevel, ProfessionalRole, \
    SalaryHistory, SearchQuery, vacancy_work_formats, search_query_vacancies, Industry, employer_industries, VacancyStatusHistory
from database.database import Session  # Импортируем Session из database.py
import numpy as np

api_bp = Blueprint('api', __name__)


@api_bp.route('/vacancies/top-skills/<int:search_query_id>', methods=['GET'])
def get_top_skills(search_query_id):
    session = Session()

    top_skills = session.query(
        KeySkill.name.label('skill_name'),
        func.count(distinct(KeySkillHistory.vacancy_id)).label('cnt')
    ) \
        .join(KeySkillHistory, KeySkillHistory.key_skill_id == KeySkill.id) \
        .join(search_query_vacancies, search_query_vacancies.c.vacancy_id == KeySkillHistory.vacancy_id) \
        .join(Vacancy, Vacancy.id == KeySkillHistory.vacancy_id).filter(
        search_query_vacancies.c.search_query_id == search_query_id,
        KeySkillHistory.is_active == 1,
        Vacancy.status == "Активный"  # Добавляем условие для статуса вакансии
    ) \
        .group_by(KeySkill.name) \
        .order_by(func.count(distinct(KeySkillHistory.vacancy_id)).desc()) \
        .limit(10) \
        .all()

    session.close()
    return jsonify([{'skill': skill_name, 'count': cnt} for skill_name, cnt in top_skills])


@api_bp.route('/vacancies/by-work-format/<int:search_query_id>', methods=['GET'])
def get_vacancies_by_work_format(search_query_id):
    session = Session()

    results = session.query(
        WorkFormat.name.label('work_format_name'),
        func.count(Vacancy.id).label('count')
    ) \
        .select_from(WorkFormat) \
        .join(vacancy_work_formats, vacancy_work_formats.c.work_format_id == WorkFormat.id) \
        .join(Vacancy, Vacancy.id == vacancy_work_formats.c.vacancy_id) \
        .join(search_query_vacancies, search_query_vacancies.c.vacancy_id == Vacancy.id) \
        .join(SearchQuery, SearchQuery.id == search_query_vacancies.c.search_query_id) \
        .filter(SearchQuery.id == search_query_id) \
        .group_by(WorkFormat.id) \
        .all()

    session.close()
    return jsonify([{'work_format': work_format_name, 'count': count} for work_format_name, count in results])


@api_bp.route('/vacancies/by-experience/<int:search_query_id>', methods=['GET'])
def get_vacancies_by_experience(search_query_id):
    session = Session()
    results = session.query(
        ExperienceLevel.name,
        func.count(Vacancy.id).label('count')
    ) \
        .join(Vacancy) \
        .join(Vacancy.search_queries) \
        .filter(
        SearchQuery.id == search_query_id,
        Vacancy.status == "Активный"  # Добавляем условие для статуса вакансии
    ).group_by(ExperienceLevel.id).all()
    session.close()
    return jsonify([{'experience_level': experience_level, 'count': count} for experience_level, count in results])


@api_bp.route('/vacancies/by-professional-role/<int:search_query_id>', methods=['GET'])
def get_vacancies_by_professional_role(search_query_id):
    session = Session()
    results = session.query(
        ProfessionalRole.name,
        func.count(Vacancy.id).label('count')
    ) \
        .join(Vacancy) \
        .join(Vacancy.search_queries) \
        .filter(
        SearchQuery.id == search_query_id,
        Vacancy.status == "Активный"  # Добавляем условие для статуса вакансии
    ).group_by(ProfessionalRole.id).order_by(func.count(Vacancy.id).desc()).limit(10).all()

    session.close()
    return jsonify([{'professional_role': professional_role, 'count': count} for professional_role, count in results])


@api_bp.route('/vacancies/industries/<int:search_query_id>', methods=['GET'])
def get_industries(search_query_id):
    session = Session()
    results = session.query(
        Industry.name,  # Используем поле name из модели Industry
        func.count(Vacancy.id).label('count')
    ) \
        .select_from(Vacancy).join(Vacancy.search_queries) \
        .join(employer_industries, employer_industries.c.employer_id == Vacancy.employer_id) \
        .join(Industry, Industry.id == employer_industries.c.industry_id) \
        .filter(
        SearchQuery.id == search_query_id,
        Vacancy.status == "Активный"  # Добавляем условие для статуса вакансии
    ) \
        .group_by(Industry.id) \
        .order_by(func.count(Vacancy.id).desc()).limit(10).all()
    session.close()
    return jsonify([{'industry': industry, 'count': count} for industry, count in results])


@api_bp.route('/vacancies/salaries/<int:search_query_id>', methods=['GET'])
def get_average_salaries(search_query_id):
    session = Session()

    avg_salaries = session.query(
        SalaryHistory.currency,
        ExperienceLevel.name.label('experience_level'),
        func.round(func.avg(SalaryHistory.salary_from)).label('avg_salary'),
    ).select_from(Vacancy).join(Vacancy.search_queries).join(SalaryHistory).join(ExperienceLevel).filter(
        SearchQuery.id == search_query_id,
        SalaryHistory.is_active == True,  # Учитываем только активные записи
        Vacancy.status == "Активный"  # Добавляем условие для статуса вакансии
    ).group_by(
        SalaryHistory.currency,
        ExperienceLevel.name
    ).order_by(
        SalaryHistory.currency,
        ExperienceLevel.name
    ).all()

    session.close()
    return jsonify([{'currency': currency, 'avg_salary': avg_salary, 'experience_level': experience_level} for
                    currency, avg_salary, experience_level in avg_salaries])


@api_bp.route('/vacancies/salary-experience-correlation/<int:search_query_id>', methods=['GET'])
def get_salary_experience_correlation(search_query_id):
    session = Session()

    salary_experience_data = session.query(
        SalaryHistory.salary_from,
        ExperienceLevel.name.label('experience_level')
    ) \
        .select_from(SalaryHistory) \
        .join(Vacancy, SalaryHistory.vacancy_id == Vacancy.id) \
        .join(ExperienceLevel, Vacancy.experience_id == ExperienceLevel.id) \
        .join(Vacancy.search_queries) \
        .filter(
        SearchQuery.id == search_query_id,
        SalaryHistory.is_active == True,  # Учитываем только активные записи
        SalaryHistory.salary_from != None  # Исключаем записи с None значениями зарплаты
    ) \
        .all()

    session.close()

    # Подсчет корреляции
    if salary_experience_data:
        salaries = [float(data.salary_from) for data in salary_experience_data if data.salary_from is not None]
        experience_levels = [data.experience_level for data in salary_experience_data]

        # Преобразование уровней опыта в числовые значения для корреляции
        experience_mapping = {level: idx for idx, level in enumerate(set(experience_levels))}
        experience_numeric = [experience_mapping[level] for level in experience_levels]

        # Проверка, что у нас достаточно данных для вычисления корреляции
        if len(salaries) > 1 and len(experience_numeric) > 1:
            correlation = np.corrcoef(np.array(salaries), np.array(experience_numeric))[0, 1]
        else:
            correlation = None
    else:
        correlation = None

    return jsonify({'correlation': correlation})


@api_bp.route('/vacancies/status_trends/<int:search_query_id>', methods=['GET'])
def get_vacancies_status_trends(search_query_id):
    session = Session()

    results = session.query(
        VacancyStatusHistory.cur_status,
        func.count(VacancyStatusHistory.id).label('count'),
        func.date(VacancyStatusHistory.created_at_cur_status).label('date')
    ).join(Vacancy, Vacancy.id == VacancyStatusHistory.vacancy_id) \
        .join(search_query_vacancies, search_query_vacancies.c.vacancy_id == Vacancy.id) \
        .filter(search_query_vacancies.c.search_query_id == search_query_id) \
        .group_by(VacancyStatusHistory.cur_status, func.date(VacancyStatusHistory.created_at_cur_status)) \
        .order_by(func.date(VacancyStatusHistory.created_at_cur_status)) \
        .all()

    session.close()

    return jsonify([{'status': status, 'count': count, 'date': date} for status, count, date in results])
