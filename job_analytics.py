import json
import os
import logging
import time
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from dotenv import load_dotenv
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
from models import TemporaryVacancy, Vacancy, ExperienceLevel, WorkFormat, KeySkill, Salary, ProfessionalRole, \
    EmploymentForm, WorkingHours, WorkSchedule, vacancy_work_formats, vacancy_key_skills, vacancy_work_schedules, \
    Employer, Industry, employer_industries, SearchQuery

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

FLASK_SERVER_URL = os.getenv('SERVER_HOST')

# Настройки API HH
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
redirect_uri = os.getenv('REDIRECT_URI')  # Получаем Redirect URI из .env
base_url = 'https://api.hh.ru'  # Базовый URL для API HH
hh_api = RestApiTool(base_url)


def parse_datetime(date_str):
    """Преобразуем строку даты в формат, который понимает MySQL."""
    dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z')
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def fetch_vacancies(session, query):
    """Сбор данных о вакансиях и сохранение в temporary_vacancies."""
    params = {
        'text': query.query,
        'per_page': 20,
        'page': 0,
        'date_from': '2025-07-06T20:00:00',
        'date_to': '2025-07-08T00:00:00'
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

        session.query(TemporaryVacancy).delete()
        session.commit()

        for vacancy in all_vacancies:
            temp_vacancy = TemporaryVacancy(
                external_id=vacancy['id'],
                title=vacancy['name'],
                employer=vacancy['employer']['name'],
                status='Активный' if not vacancy['archived'] else 'Архивный',
                professional_role=vacancy['professional_roles'][0]['name'] if vacancy['professional_roles'] else None
            )
            session.add(temp_vacancy)
        session.commit()
        logging.info(f"Loaded {len(all_vacancies)} vacancies into temporary_vacancies.")
    except Exception as e:
        logging.error("Error fetching vacancies for query '%s': %s", query.query, str(e))
        session.rollback()  # Rollback in case of error


def check_for_new_vacancies(session, query):
    """Проведение сверки и сбор детальной информации о новых вакансиях."""
    logging.info(f"Checking for new vacancies for query ID: {query.id}")
    successful_loads = 0
    failed_loads = 0
    error_messages = []

    try:
        temp_ids = get_temp_vacancy_ids(session)
        existing_ids = get_existing_vacancy_ids(session)

        new_vacancy_ids = temp_ids - existing_ids
        logging.info(f"Found {len(new_vacancy_ids)} new vacancies.")

        for vacancy_id in new_vacancy_ids:
            result = process_new_vacancy(vacancy_id, session, query)
            if result['success']:
                successful_loads += 1
            else:
                failed_loads += 1
                error_messages.append(result['error'])

            # Пауза между запросами
            time.sleep(2)

        clear_temporary_vacancies(session)

    except Exception as e:
        logging.error(f"Error checking for new vacancies: {str(e)}")
        session.rollback()
    finally:
        session.close()

    # Вывод отчета
    logging.info(f"Successfully loaded vacancies: {successful_loads}")
    logging.info(f"Failed to load vacancies: {failed_loads}")
    if error_messages:
        logging.info("Error messages:")
        for message in error_messages:
            logging.info(message)


def get_temp_vacancy_ids(session):
    """Получение всех external_id из temporary_vacancies."""
    temp_vacancies = session.query(TemporaryVacancy).all()
    return {vacancy.external_id for vacancy in temp_vacancies}


def get_existing_vacancy_ids(session):
    """Получение всех external_id из vacancies."""
    existing_vacancies = session.query(Vacancy).all()
    return {vacancy.external_id for vacancy in existing_vacancies}


def process_new_vacancy(vacancy_id, session, query):
    """Обработка новой вакансии."""
    try:
        vacancy_data = hh_api.get(f'vacancies/{vacancy_id}')
    except Exception as e:
        logging.error(f"Failed to fetch vacancy details for ID {vacancy_id}: {str(e)}")
        return {'success': False,
                'error': f"Failed to fetch vacancy details for ID {vacancy_id}: {str(e)}"}

    try:
        employer_info = fetch_employer_info(vacancy_data['employer']['id'])
        print(f"employer_data - {vacancy_data['employer']}")
        if 'employer_rating' in vacancy_data['employer']:
            employer_rating_total_rating = vacancy_data['employer']['employer_rating']['total_rating']
            employer_rating_reviews_count = vacancy_data['employer']['employer_rating']['reviews_count']
        else:
            employer_rating_total_rating = 0.0
            employer_rating_reviews_count = 0
        employer = get_or_create_employer(session, employer_info, employer_rating_total_rating,
                                          employer_rating_reviews_count)

        experience = get_or_create_experience(session, vacancy_data['experience'])
        professional_role = get_or_create_professional_role(session, vacancy_data['professional_roles'][0])
        employment_form = get_or_create_employment_form(session, vacancy_data['employment_form'])
        working_hours = get_or_create_working_hours(session, vacancy_data['working_hours'][0])
        work_schedule_ids = get_or_create_work_schedules(session, vacancy_data.get('work_schedule_by_days', []))
        work_format_ids = get_or_create_work_formats(session, vacancy_data.get('work_format', []))
        key_skills_ids = get_or_create_key_skills(session, vacancy_data['key_skills'])
        industry_ids = get_or_create_industries(session, employer_info['industries'], employer)

        vacancy = create_vacancy(session, vacancy_data, employer, experience, professional_role, employment_form,
                                 working_hours, query)
        create_salary(session, vacancy_data.get('salary_range'), vacancy.id)
        save_relations(session, vacancy.id, work_format_ids, key_skills_ids, work_schedule_ids, industry_ids)

        logging.info(f"Vacancy {vacancy_data['id']} loaded successfully.")
        return {'success': True}

    except Exception as e:
        logging.error(f"Error loading vacancy {vacancy_data['id']}: {str(e)}")
        return {'success': False, 'error': str(e)}


def fetch_employer_info(employer_id):
    """Получение данных о работодателе через API."""
    try:
        employer_response = hh_api.get(f'employers/{employer_id}')
    except Exception as e:
        logging.error(f"Failed to fetch employer data for ID {employer_id}: {str(e)}")
        raise Exception(f"Failed to fetch employer data for ID {employer_id}: {str(e)}")
    return employer_response


def get_or_create_employer(session, employer_info, employer_rating_total_rating, employer_rating_reviews_count):
    """Проверка и добавление работодателя в базу данных."""
    employer = session.query(Employer).filter_by(id_external=employer_info['id']).first()
    if not employer:
        employer = Employer(
            id_external=employer_info['id'],
            name=employer_info['name'],
            area=employer_info['area']['name'],
            accredited_it_employer=employer_info['accredited_it_employer'],
            open_vacancies=employer_info['open_vacancies'],
            total_rating=float(employer_rating_total_rating),
            reviews_count=employer_rating_reviews_count,
        )
        session.add(employer)
        session.commit()  # Сохраняем изменения, чтобы получить id
    return employer


def get_or_create_experience(session, experience_data):
    """Проверка и добавление уровня опыта."""
    experience = session.query(ExperienceLevel).filter_by(id_external=experience_data['id']).first()
    if not experience:
        experience = ExperienceLevel(id_external=experience_data['id'], name=experience_data['name'])
        session.add(experience)
        session.commit()  # Сохраняем изменения, чтобы получить id
    return experience


def get_or_create_professional_role(session, role_data):
    """Проверка и добавление профессиональной роли."""
    professional_role = session.query(ProfessionalRole).filter_by(id_external=role_data['id']).first()
    if not professional_role:
        professional_role = ProfessionalRole(id_external=role_data['id'], name=role_data['name'])
        session.add(professional_role)
        session.commit()  # Сохраняем изменения, чтобы получить id
    return professional_role


def get_or_create_employment_form(session, form_data):
    """Проверка и добавление формата работы."""
    employment_form = session.query(EmploymentForm).filter_by(id_external=form_data['id']).first()
    if not employment_form:
        employment_form = EmploymentForm(id_external=form_data['id'], name=form_data['name'])
        session.add(employment_form)
        session.commit()  # Сохраняем изменения, чтобы получить id
    return employment_form


def get_or_create_working_hours(session, hours_data):
    """Проверка и добавление рабочих часов."""
    working_hours = session.query(WorkingHours).filter_by(id_external=hours_data['id']).first()
    if not working_hours:
        working_hours = WorkingHours(id_external=hours_data['id'], name=hours_data['name'])
        session.add(working_hours)
        session.commit()  # Сохраняем изменения, чтобы получить id
    return working_hours


def get_or_create_work_schedules(session, work_schedule_data):
    """Проверка и добавление графиков работы."""
    work_schedule_ids = []
    for ws in work_schedule_data:
        work_schedule = session.query(WorkSchedule).filter_by(id_external=ws['id']).first()
        if not work_schedule:
            work_schedule = WorkSchedule(id_external=ws['id'], name=ws['name'])
            session.add(work_schedule)
            session.commit()  # Сохраняем изменения, чтобы получить id
        work_schedule_ids.append(work_schedule.id)
    return work_schedule_ids


def get_or_create_work_formats(session, work_format_data):
    """Проверка и добавление форматов работы."""
    work_format_ids = []
    for wf in work_format_data:
        work_format = session.query(WorkFormat).filter_by(id_external=wf['id']).first()
        if not work_format:
            work_format = WorkFormat(id_external=wf['id'], name=wf['name'])
            session.add(work_format)
            session.commit()  # Сохраняем изменения, чтобы получить id
        work_format_ids.append(work_format.id)
    return work_format_ids


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


def create_vacancy(session, vacancy_data, employer, experience, professional_role, employment_form, working_hours,
                   query):
    """Создание объекта вакансии."""
    created_date = parse_datetime(vacancy_data['initial_created_at'])
    published_date = parse_datetime(vacancy_data['published_at'])
    vacancy = Vacancy(
        external_id=vacancy_data['id'],
        title=vacancy_data['name'],
        employer_id=employer.id,
        area=vacancy_data['area']['name'],
        experience_id=experience.id,
        professional_role_id=professional_role.id,
        employment_form_id=employment_form.id,
        working_hours_id=working_hours.id,
        status='Активный' if not vacancy_data['archived'] else 'Архивный',
        created_date=created_date,
        published_date=published_date,
        search_query_id=query.id
    )
    session.add(vacancy)
    session.commit()  # Сохраняем изменения, чтобы получить id вакансии
    return vacancy


def create_salary(session, salary_data, vacancy_id):
    """Создание записи о зарплате."""
    if salary_data and 'from' in salary_data and 'to' in salary_data and 'currency' in salary_data and 'mode' in salary_data:
        salary = Salary(
            salary_from=salary_data.get('from'),
            salary_to=salary_data.get('to'),
            currency=salary_data.get('currency'),
            mode_id=salary_data["mode"].get("id"),  # Используем get для безопасного доступа
            mode_name=salary_data["mode"].get("name"),  # Используем get для безопасного доступа
            vacancy_id=vacancy_id
        )
        session.add(salary)
    else:
        logging.warning(f"Salary data is incomplete for vacancy ID {vacancy_id}: {salary_data}")


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


def clear_temporary_vacancies(session):
    """Очищаем таблицу temporary_vacancies после успешной обработки."""
    session.query(TemporaryVacancy).delete()
    session.commit()
    logging.info("Cleared temporary_vacancies table after processing.")


def main():
    with Session() as session:
        active_queries = session.query(SearchQuery).filter_by(is_active=True).all()
        logging.info("Fetching vacancies with active search queries.")
        for query in active_queries:
            fetch_vacancies(session, query)  # Сбор данных о вакансиях
            check_for_new_vacancies(session, query)  # Сверка и сбор детальной информации о новых вакансиях


if __name__ == "__main__":
    main()
