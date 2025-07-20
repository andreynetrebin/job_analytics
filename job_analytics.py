import json
import os
import logging
import time
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from dotenv import load_dotenv
import pytz
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
from models import Vacancy, ExperienceLevel, WorkFormat, KeySkill, ProfessionalRole, \
    EmploymentForm, WorkingHours, WorkSchedule, vacancy_work_formats, vacancy_work_schedules, \
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

moscow_tz = pytz.timezone('Europe/Moscow')


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
        'date_from': '2025-07-15T14:00:00',
        'date_to': '2025-07-15T20:00:00'
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
            time.sleep(2)
            process_vacancy(vacancy, session, query)

    except Exception as e:
        logging.error("Error fetching vacancies for query '%s': %s", query.query, str(e))
        session.rollback()  # Rollback in case of error


def process_vacancy(vacancy_data, session, query):
    """Обработка и сохранение вакансии в базу данных."""
    external_id = vacancy_data['id']
    search_query_id = query.id

    # Проверяем существование вакансии по external_id и search_query_id
    existing_vacancy = session.query(Vacancy).filter_by(external_id=external_id,
                                                        search_query_id=search_query_id).first()

    if existing_vacancy:
        logging.info(f"Vacancy with external ID {external_id} already exists. Checking status.")

        # Проверяем статус вакансии
        if existing_vacancy.status == "Архивный":
            logging.info(f"Vacancy {external_id} is archived. Reviving it.")
            revive_vacancy(existing_vacancy, vacancy_data, session)
        else:
            logging.info(f"Vacancy {external_id} is already active. Skipping.")
        return  # Вакансия уже существует и активна, пропускаем

    try:
        # Создаем новую вакансию
        create_vacancy(vacancy_data, session, query)
    except Exception as e:
        logging.error(f"Error processing vacancy {external_id}: {str(e)}")


def revive_vacancy(existing_vacancy, vacancy_data, session):
    """Возобновление архивной вакансии."""
    # Обновляем статус вакансии
    existing_vacancy.status = "Активный"
    existing_vacancy.updated_at = datetime.now(moscow_tz)
    existing_vacancy.published_date = parse_datetime(
        vacancy_data['published_at']) if 'published_at' in vacancy_data else existing_vacancy.published_date

    # Обновляем запись в VacancyStatusHistory
    vacancy_status_history = VacancyStatusHistory(
        vacancy_id=existing_vacancy.id,
        prev_status="Архивный",
        cur_status="Активный",
        created_at_prev_status=existing_vacancy.updated_at,
        created_at_cur_status=datetime.now(moscow_tz),
        duration=(datetime.now(moscow_tz) - existing_vacancy.updated_at).days,
        type_changed="Возобновление"
    )
    session.add(vacancy_status_history)

    # Обновляем историю зарплаты
    update_salary_history(existing_vacancy, vacancy_data, session)

    # Получаем детальную информацию о вакансии для получения ключевых навыков
    vacancy_details = hh_api.get(f'vacancies/{vacancy_data["id"]}')

    # Обновляем ключевые навыки
    update_key_skills(existing_vacancy, vacancy_details, session)

    # Сохраняем изменения
    session.commit()
    logging.info(f"Vacancy {existing_vacancy.external_id} revived successfully.")


def update_salary_history(existing_vacancy, vacancy_data, session):
    """Обновление истории зарплаты для вакансии."""
    salary_range_data = vacancy_data.get('salary_range')
    salary_from = salary_range_data.get('from') if salary_range_data else None
    salary_to = salary_range_data.get('to') if salary_range_data else None
    currency = salary_range_data.get('currency', 'RUB') if salary_range_data else 'RUB'
    mode = salary_range_data.get('mode', {})
    mode_id = mode.get('id')
    mode_name = mode.get('name')

    # Получаем текущую активную запись зарплаты
    current_salary_history = session.query(SalaryHistory).filter_by(vacancy_id=existing_vacancy.id,
                                                                    is_active=True).first()

    if current_salary_history:
        # Проверяем изменения в зарплате
        if (current_salary_history.salary_from != salary_from or
                current_salary_history.salary_to != salary_to or
                current_salary_history.currency != currency or
                current_salary_history.mode_id != mode_id or
                current_salary_history.mode_name != mode_name):
            # Деактивируем текущую запись
            current_salary_history.is_active = False
            current_salary_history.updated_at = datetime.now(moscow_tz)

            # Создаем новую запись
            new_salary_history = SalaryHistory(
                vacancy_id=existing_vacancy.id,
                salary_from=salary_from,
                salary_to=salary_to,
                currency=currency,
                mode_id=mode_id,
                mode_name=mode_name
            )
            session.add(new_salary_history)
            logging.info(f"Salary history updated for vacancy {existing_vacancy.external_id}.")
    else:
        # Если записи нет, создаем новую
        new_salary_history = SalaryHistory(
            vacancy_id=existing_vacancy.id,
            salary_from=salary_from,
            salary_to=salary_to,
            currency=currency,
            mode_id=mode_id,
            mode_name=mode_name
        )
        session.add(new_salary_history)
        logging.info(f"New salary history created for vacancy {existing_vacancy.external_id}.")


def update_key_skills(existing_vacancy, vacancy_details, session):
    """Обновление ключевых навыков для вакансии."""
    current_key_skills = {ks.key_skill_id for ks in existing_vacancy.key_skill_history if ks.is_active}
    new_key_skills = {skill['name']: skill for skill in vacancy_details.get('key_skills', [])}

    # Проверяем новые навыки
    for skill_name, skill_data in new_key_skills.items():
        key_skill = session.query(KeySkill).filter_by(name=skill_name).first()
        if key_skill:
            if key_skill.id not in current_key_skills:
                # Если навык новый, добавляем его в историю
                key_skill_history = KeySkillHistory(
                    vacancy_id=existing_vacancy.id,
                    key_skill_id=key_skill.id
                )
                session.add(key_skill_history)
                logging.info(f"New key skill '{skill_name}' added for vacancy {existing_vacancy.external_id}.")
        else:
            # Если навык не найден, создаем его
            key_skill = KeySkill(name=skill_name)
            session.add(key_skill)
            session.commit()  # Сохраняем, чтобы получить id
            key_skill_history = KeySkillHistory(
                vacancy_id=existing_vacancy.id,
                key_skill_id=key_skill.id
            )
            session.add(key_skill_history)
            logging.info(f"Key skill '{skill_name}' created and added for vacancy {existing_vacancy.external_id}.")

    # Проверяем ушедшие навыки
    for existing_skill_id in current_key_skills:
        if existing_skill_id not in new_key_skills.values():
            # Деактивируем старую запись
            skill_history = session.query(KeySkillHistory).filter_by(vacancy_id=existing_vacancy.id,
                                                                     key_skill_id=existing_skill_id,
                                                                     is_active=True).first()
            if skill_history:
                skill_history.is_active = False
                skill_history.updated_at = datetime.now(moscow_tz)
                logging.info(
                    f"Key skill with ID {existing_skill_id} deactivated for vacancy {existing_vacancy.external_id}.")

    session.commit()


def create_vacancy(vacancy_data, session, query):
    """Создание объекта вакансии."""
    try:
        # Получаем детальную информацию о вакансии для получения ключевых навыков и дат
        vacancy_details = hh_api.get(f'vacancies/{vacancy_data["id"]}')

        # Получаем информацию о работодателе из детальной информации о вакансии
        employer_info = vacancy_data['employer']
        employer_id = employer_info['id']
        employer_details = hh_api.get(f'employers/{employer_id}')

        # Извлекаем информацию о работодателе
        employer_name = employer_info['name']
        open_vacancies = employer_details.get('open_vacancies', 0)  # Значение по умолчанию 0
        accredited_it_employer = employer_details.get('accredited_it_employer', False)

        try:
            employer_rating = employer_info['employer_rating']
            total_rating = float(employer_rating.get('total_rating', 0.0))  # Преобразуем в float
            reviews_count = int(employer_rating.get('reviews_count', 0))  # Преобразуем в int
        except:
            total_rating = 0.0  # Значение по умолчанию
            reviews_count = 0  # Значение по умолчанию

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

        # Извлекаем даты создания и публикации
        created_date = parse_datetime(
            vacancy_details['initial_created_at']) if 'created_at' in vacancy_details else None
        published_date = parse_datetime(vacancy_details['published_at']) if 'published_at' in vacancy_details else None

        # Извлекаем данные о зарплате только из salary_range
        salary_range_data = vacancy_details.get('salary_range')
        salary_from = None
        salary_to = None
        currency = 'RUB'  # Значение по умолчанию для валюты
        mode_id = None
        mode_name = None
        if salary_range_data:
            salary_from = salary_range_data.get('from')
            salary_to = salary_range_data.get('to')
            currency = salary_range_data.get('currency', currency)  # Обновляем валюту, если указана
            mode = salary_range_data.get('mode')
            if mode:
                mode_id = mode.get('id')
                mode_name = mode.get('name')

        # Создаем запись о вакансии
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

        # Теперь, когда у нас есть vacancy.id, мы можем получить ключевые навыки
        get_or_create_key_skills(session, vacancy_details['key_skills'], vacancy.id)

        # Создаем запись о зарплате, если она указана
        if salary_from is not None or salary_to is not None:
            salary_history = SalaryHistory(
                salary_from=salary_from,
                salary_to=salary_to,
                currency=currency,
                mode_id=mode_id,
                mode_name=mode_name,
                vacancy_id=vacancy.id
            )
            session.add(salary_history)

        # Создаем запись о статусе вакансии
        vacancy_status_history = VacancyStatusHistory(
            vacancy_id=vacancy.id,
            prev_status="Отсутствует",
            cur_status="Активный",
            created_at_prev_status=vacancy.created_at,
            created_at_cur_status=vacancy.created_at,
            duration=0,
            type_changed="Первичная загрузка"
        )
        session.add(vacancy_status_history)

        # Получаем отрасли работодателя через отдельный запрос к API
        get_or_create_industries(session, industries, employer)

        # Сохраняем связи
        save_relations(session, vacancy.id, work_format_ids, work_schedule_ids)

        logging.info(f"Vacancy {vacancy_data['id']} loaded successfully.")

    except Exception as e:
        logging.error(f"Error loading vacancy {vacancy_data['id']}: {str(e)}")


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


def get_or_create_key_skills(session, key_skills_data, vacancy_id):
    """Проверка и добавление ключевых навыков в таблицу key_skill_history."""
    key_skills_ids = []
    for skill_data in key_skills_data:
        # Проверяем, существует ли ключевой навык
        key_skill = session.query(KeySkill).filter_by(name=skill_data['name']).first()
        if not key_skill:
            # Если не существует, создаем новый ключевой навык
            key_skill = KeySkill(name=skill_data['name'])
            session.add(key_skill)
            session.commit()  # Сохраняем изменения, чтобы получить id

        # Создаем запись в key_skill_history
        key_skill_history = KeySkillHistory(
            vacancy_id=vacancy_id,
            key_skill_id=key_skill.id,
        )
        session.add(key_skill_history)
        key_skills_ids.append(key_skill.id)

    session.commit()  # Сохраняем все изменения в конце
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


def save_relations(session, vacancy_id, work_format_ids, work_schedule_ids):
    """Сохранение форматов работы и графиков работы в промежуточные таблицы."""

    # Сохранение форматов работы
    for work_format_id in work_format_ids:
        session.execute(
            vacancy_work_formats.insert().values(vacancy_id=vacancy_id, work_format_id=work_format_id)
        )

    # Сохранение графиков работы
    for work_schedule_id in work_schedule_ids:
        session.execute(
            vacancy_work_schedules.insert().values(vacancy_id=vacancy_id, work_schedule_id=work_schedule_id)
        )

    # Сохраняем все изменения в сессии
    session.commit()


def main():
    with Session() as session:
        active_queries = session.query(SearchQuery).filter_by(is_active=True).all()
        logging.info("Fetching vacancies with active search queries.")
        for query in active_queries:
            fetch_vacancies(session, query)  # Сбор данных о вакансиях


if __name__ == "__main__":
    main()
