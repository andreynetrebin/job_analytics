import json
import os
import logging
import time
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from dotenv import load_dotenv
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
from models import Vacancy, ExperienceLevel, WorkFormat, KeySkill, Salary, ProfessionalRole, \
    EmploymentForm, WorkingHours, WorkSchedule, vacancy_work_formats, vacancy_key_skills, vacancy_work_schedules, \
    Employer, Industry, employer_industries, SearchQuery, VacancyStatusHistory, KeySkillHistory, SalaryHistory

# Настройка логирования
log_file_path = 'job_analytics.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file_path), logging.StreamHandler()])

# Загрузка переменных окружения
load_dotenv()

# Настройка базы данных
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')

DATABASE_URL = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# Настройки API HH
base_url = 'https://api.hh.ru'  # Базовый URL для API HH
hh_api = RestApiTool(base_url)


def parse_datetime(date_str):
    """Преобразуем строку даты в формат, который понимает MySQL."""
    dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z')
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def fetch_vacancies(session, query):
    """Сбор данных о вакансиях и сохранение в базу данных."""
    params = {
        'text': query.query,
        'per_page': 20,
        'page': 0,
        'date_from': '2025-07-10T07:00:00',
        'date_to': '2025-07-14T23:00:00'
    }
    logging.info("Fetching vacancies with parameters: %s", params)
    all_vacancies = []
    try:
        while True:
            response = hh_api.get('vacancies', params=params)
            vacancies = response.get('items', [])
            all_vacancies.extend(vacancies)
            if response.get('pages', 0) <= params['page'] + 1:
                break
            params['page'] += 1

        logging.info("Vacancies fetched successfully for query '%s'. Total vacancies: %d", query.query,
                     len(all_vacancies))

        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f'vacancies_data/vacancies_query_{query.id}_{date_str}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_vacancies, f, ensure_ascii=False, indent=4)
            logging.info("Vacancies data saved to %s", filename)

        for vacancy in all_vacancies:
            process_vacancy(vacancy, session, query)

    except Exception as e:
        logging.error("Error fetching vacancies for query '%s': %s", query.query, str(e))
        session.rollback()  # Rollback in case of error


def process_vacancy(vacancy_data, session, query):
    """Обработка и сохранение вакансии в базу данных."""
    external_id = vacancy_data['id']
    existing_vacancy = session.query(Vacancy).filter_by(external_id=external_id).first()

    if existing_vacancy:
        # Если вакансия уже существует, проверяем, была ли она архивирована
        if existing_vacancy.status == 'Архивный' and not vacancy_data.get('archived', False):
            # Вакансия возобновляется
            existing_vacancy.status = 'Активный'
            existing_vacancy.updated_at = datetime.now()

            # Добавляем запись в историю статусов
            created_at_prev_status = existing_vacancy.updated_at
            created_at_cur_status = datetime.now()
            duration = (created_at_cur_status - created_at_prev_status).days

            status_history = VacancyStatusHistory(
                vacancy_id=existing_vacancy.id,
                prev_status='Архивный',
                cur_status='Активный',
                created_at_prev_status=created_at_prev_status,
                created_at_cur_status=created_at_cur_status,
                duration=duration,
                type_changed='Возобновление'
            )
            session.add(status_history)
            logging.info(f"Updated status of existing vacancy {external_id} to 'Active'.")

            # Обновляем ключевые навыки, если они изменились
            new_key_skills = get_key_skills(session, external_id)
            current_key_skills = {skill.id for skill in existing_vacancy.key_skills}  # Предполагается, что у вас есть связь с ключевыми навыками
            if current_key_skills != new_key_skills:
                for skill_id in new_key_skills - current_key_skills:
                    session.add(KeySkillHistory(vacancy_id=existing_vacancy.id, skill_id=skill_id, changed_at=datetime.now()))

            # Обновляем информацию о зарплате, если она изменилась
            salary_data = vacancy_data.get('salary')
            if salary_data and (existing_vacancy.salary_from != salary_data.get('from') or existing_vacancy.salary_to != salary_data.get('to')):
                session.add(SalaryHistory(vacancy_id=existing_vacancy.id, salary_from=salary_data.get('from'), salary_to=salary_data.get('to'), changed_at=datetime.now()))

        # Если вакансия активна, просто обновляем информацию
        else:
            update_vacancy(existing_vacancy, vacancy_data, session)

    else:
        # Если вакансия новая, создаем её
        create_vacancy(vacancy_data, session, query)


def update_vacancy(existing_vacancy, vacancy_data, session):
    """Обновление информации о существующей вакансии."""
    # Обновляем поля вакансии
    existing_vacancy.title = vacancy_data['name']
    existing_vacancy.updated_at = datetime.now()
    session.commit()
    logging.info(f"Updated existing vacancy {existing_vacancy.external_id}.")


def create_vacancy(vacancy_data, session, query):
    """Создание объекта вакансии."""
    try:
        # Получаем детальную информацию о вакансии для получения ключевых навыков и дат
        vacancy_details = hh_api.get(f'vacancies/{vacancy_data["id"]}')

        # Получаем информацию о работодателе из детальной информации о вакансии
        employer_info = vacancy_details['employer']
        employer_id = employer_info['id']
        employer_details = hh_api.get(f'employers/{employer_id}')

        # Извлекаем информацию о работодателе
        employer_name = employer_info['name']
        open_vacancies = employer_info.get('open_vacancies', 0)  # Значение по умолчанию 0
        accredited_it_employer = employer_info.get('accredited_it_employer', False)

        total_rating = employer_info.get('employer_rating', {}).get('total_rating')  # Значение по умолчанию 0.0
        reviews_count = employer_info.get('employer_rating', {}).get('reviews_count')  # Значение по умолчанию 0

        # Извлекаем area и industries из employer_details
        area_name = employer_details.get('area', {}).get('name')  # Получаем area из деталей работодателя
        industries = employer_details.get('industries', [])

        # Проверяем, существует ли работодатель в базе данных
        employer = session.query(Employer).filter_by(id_external=employer_id).first()
        if not employer:
            # Если работодатель не существует, создаем его
            employer = Employer(
                id_external=employer_id,
                name=employer_name,
                area=area_name,
                accredited_it_employer=accredited_it_employer,
                open_vacancies=open_vacancies,
                total_rating=total_rating,
                reviews_count=reviews_count
            )
            session.add(employer)
            session.commit()  # Сохраняем изменения, чтобы получить id работодателя

        # Получаем уровень опыта, профессиональную роль, форму занятости и рабочие часы из JSON
        experience = get_or_create_experience(session, vacancy_details['experience'])
        professional_role = get_or_create_professional_role(session, vacancy_details['professional_roles'][0])
        employment_form = get_or_create_employment_form(session, vacancy_details['employment_form'])
        working_hours = get_or_create_working_hours(session, vacancy_details['working_hours'][0])

        # Получаем графики работы и форматы работы из JSON
        work_schedule_ids = get_or_create_work_schedules(session, vacancy_details.get('work_schedule_by_days', []))
        work_format_ids = get_or_create_work_formats(session, vacancy_details.get('work_format', []))

        # Извлекаем ключевые навыки
        key_skills_ids = get_or_create_key_skills(session, vacancy_details['key_skills'])

        # Извлекаем даты создания и публикации
        created_date = parse_datetime(vacancy_details['initial_created_at']) if 'created_at' in vacancy_details else None
        published_date = parse_datetime(vacancy_details['published_at']) if 'published_at' in vacancy_details else None

        vacancy = Vacancy(
            external_id=vacancy_data['id'],
            title=vacancy_data['name'],
            employer_id=employer.id,
            area=area_name,
            experience_id=experience.id,
            professional_role_id=professional_role.id,
            employment_form_id=employment_form.id,
            working_hours_id=working_hours.id,
            status='Активный' if not vacancy_data.get('archived', False) else 'Архивный',
            created_date=created_date,
            published_date=published_date,
            search_query_id=query.id
        )
        session.add(vacancy)
        session.commit()  # Сохраняем изменения, чтобы получить id вакансии

        # Получаем отрасли работодателя через отдельный запрос к API
        industry_ids = get_or_create_industries(session, industries, employer)

        # Сохраняем связи
        save_relations(session, vacancy.id, work_format_ids, key_skills_ids, work_schedule_ids, industry_ids)

        logging.info(f"Vacancy {vacancy_data['id']} loaded successfully.")

    except Exception as e:
        logging.error(f"Error loading vacancy {vacancy_data['id']}: {str(e)}")


def get_or_create_key_skills(session, key_skills_data):
    """Проверка и добавление ключевых навыков."""
    key_skills_ids = []
    for skill_data in key_skills_data:
        key_skill = session.query(KeySkill).filter_by(name=skill_data['name']).first()
        if not key_skill:
            key_skill = KeySkill(name=skill_data['name'])
            session.add(key_skill)
            session.commit()  # Сохраняем изменения, чтобы получить id
        key_skills_ids.append(key_skill.id)
    return key_skills_ids


def get_key_skills(session, vacancy_id):
    """Получение ключевых навыков через API."""
    try:
        vacancy_details = hh_api.get(f'vacancies/{vacancy_id}')
        key_skills_ids = get_or_create_key_skills(session, vacancy_details['key_skills'])
        return key_skills_ids
    except Exception as e:
        logging.error(f"Failed to fetch key skills for vacancy ID {vacancy_id}: {str(e)}")
        return []


def get_or_create_industries(session, industries_data, employer):
    """Проверка и добавление отраслей работодателя."""
    industry_ids = []
    for industry_data in industries_data:
        industry = session.query(Industry).filter_by(id_external=industry_data['id']).first()
        if not industry:
            industry = Industry(id_external=industry_data['id'], name=industry_data['name'])
            session.add(industry)
            session.commit()  # Сохраняем изменения, чтобы получить id
        industry_ids.append(industry.id)

        # Сохранение отраслей работодателя в промежуточную таблицу
        existing_entry = session.query(employer_industries).filter_by(employer_id=employer.id,
                                                                      industry_id=industry.id).first()
        if not existing_entry:
            session.execute(employer_industries.insert().values(employer_id=employer.id, industry_id=industry.id))

    return industry_ids


def save_relations(session, vacancy_id, work_format_ids, key_skills_ids, work_schedule_ids, industry_ids):
    """Сохранение форматов работы, ключевых навыков и графиков работы в промежуточные таблицы."""
    for work_format_id in work_format_ids:
        session.execute(
            vacancy_work_formats.insert().values(vacancy_id=vacancy_id, work_format_id=work_format_id))

    for key_skill_id in key_skills_ids:
        session.execute(
            vacancy_key_skills.insert().values(vacancy_id=vacancy_id, key_skill_id=key_skill_id))

    for work_schedule_id in work_schedule_ids:
        session.execute(
            vacancy_work_schedules.insert().values(vacancy_id=vacancy_id, work_schedule_id=work_schedule_id))


def main():
    with Session() as session:
        active_queries = session.query(SearchQuery).filter_by(is_active=True).all()
        logging.info("Fetching vacancies with active search queries.")
        for query in active_queries:
            fetch_vacancies(session, query)  # Сбор данных о вакансиях


if __name__ == "__main__":
    main()
