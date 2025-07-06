import requests
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


def load_temp_vacancies_from_json(json_file_path):
    """Загрузить данные о вакансиях из JSON в таблицу temporary_vacancies."""
    with open(json_file_path, 'r', encoding='utf-8') as file:
        vacancies_data = json.load(file)

    session = Session()

    # Очистка таблицы перед загрузкой новых данных
    session.query(TemporaryVacancy).delete()
    session.commit()

    for vacancy in vacancies_data:
        # Определение статуса на основе значения "archived"
        status = "Архивный" if vacancy.get('archived', False) else "Активный"

        # Проверка существования записи перед вставкой
        existing_vacancy = session.query(TemporaryVacancy).filter_by(external_id=vacancy['id']).first()
        if existing_vacancy:
            logging.info(f"Vacancy {vacancy['id']} already exists in temporary_vacancies. Skipping.")
            continue

        temp_vacancy = TemporaryVacancy(
            external_id=vacancy['id'],
            title=vacancy['name'],
            employer=vacancy['employer']['name'],
            status=status,  # Устанавливаем статус на основе значения "archived"
            professional_role=vacancy['professional_roles'][0]['name'] if vacancy['professional_roles'] else None
        )
        session.add(temp_vacancy)

    session.commit()
    logging.info(f"Загружено {len(vacancies_data)} вакансий во временную таблицу.")
    session.close()


def fetch_vacancies():
    """Сбор данных о вакансиях и сохранение в temporary_vacancies."""
    session = Session()
    # Получаем активные поисковые запросы из базы данных
    active_queries = session.query(SearchQuery).filter_by(is_active=True).all()
    logging.info("Fetching vacancies with active search queries.")
    for query in active_queries:
        all_vacancies = []  # Список для хранения всех вакансий
        params = {
            'text': query.query,  # Используем текст из активного поискового запроса
            'per_page': 20,  # Количество вакансий на странице
            'page': 0,  # Начальная страница
            'date_from': '2025-07-06T00:00:00'
        }

        logging.info("Fetching vacancies with parameters: %s", params)
        try:
            while True:
                # Получение вакансий из API HH с параметрами
                response = hh_api.get('vacancies', params=params)
                vacancies = response.get('items', [])
                all_vacancies.extend(vacancies)  # Добавляем полученные вакансии в общий список
                # Проверка на наличие следующей страницы
                if response.get('pages', 0) <= params['page'] + 1:
                    break  # Если больше нет страниц, выходим из цикла
                params['page'] += 1  # Переход к следующей странице

            # Логирование результата
            logging.info("Vacancies fetched successfully for query '%s'. Total vacancies: %d", query.query,
                         len(vacancies))

            # Сохранение данных в JSON файл для каждого поискового запроса
            date_str = datetime.now().strftime('%Y-%m-%d')  # Формат даты
            filename = f'vacancies_data/vacancies_query_{query.id}_{date_str}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(vacancies, f, ensure_ascii=False, indent=4)
                logging.info("Vacancies data saved to %s", filename)

            # Очистка таблицы перед загрузкой новых данных
            session.query(TemporaryVacancy).delete()
            session.commit()

            for vacancy in vacancies:
                temp_vacancy = TemporaryVacancy(
                    external_id=vacancy['id'],
                    title=vacancy['name'],
                    employer=vacancy['employer']['name'],
                    status='Активный' if not vacancy['archived'] else 'Архивный',
                    professional_role=vacancy['professional_roles'][0]['name'] if vacancy[
                        'professional_roles'] else None
                )
                session.add(temp_vacancy)
            session.commit()
            logging.info(f"Loaded {len(vacancies)} vacancies into temporary_vacancies.")
            session.close()
        except Exception as e:
            logging.error("Error fetching vacancies for query '%s': %s", query.query, str(e))
            session.close()


def check_for_new_vacancies():
    """Проведение сверки и сбор детальной информации о новых вакансиях."""
    session = Session()
    successful_loads = 0
    failed_loads = 0
    error_messages = []

    try:
        # Получаем все external_id из temporary_vacancies
        temp_vacancies = session.query(TemporaryVacancy).all()
        temp_ids = {vacancy.external_id for vacancy in temp_vacancies}

        # Получаем все external_id из vacancies
        existing_vacancies = session.query(Vacancy).all()
        existing_ids = {vacancy.external_id for vacancy in existing_vacancies}

        # Находим новые вакансии
        new_vacancy_ids = temp_ids - existing_ids
        logging.info(f"Found {len(new_vacancy_ids)} new vacancies.")

        for vacancy_id in new_vacancy_ids:
            # Получаем детальную информацию о новой вакансии
            response = requests.get(f'{FLASK_SERVER_URL}/vacancy/{vacancy_id}')
            if response.status_code == 200:
                vacancy_data = response.json()

                try:
                    # Преобразование дат
                    created_date = parse_datetime(vacancy_data['initial_created_at'])
                    published_date = parse_datetime(vacancy_data['published_at'])
                    # Получение данных о работодателе через API
                    employer_id = vacancy_data['employer']['id']
                    employer_response = requests.get(f'{FLASK_SERVER_URL}/employers/{employer_id}')

                    if employer_response.status_code == 200:
                        employer_info = employer_response.json()
                        employer_name = employer_info['name']
                        employer_area = employer_info['area']['name']
                        employer_accredited = employer_info['accredited_it_employer']
                        employer_open_vacancies = employer_info['open_vacancies']
                    else:
                        logging.error(
                            f"Failed to fetch employer data for ID {employer_id}: {employer_response.status_code}")
                        continue  # Прекращаем выполнение, если не удалось получить данные о работодателе
                    # Проверка и добавление работодателя в базу данных
                    employer = session.query(Employer).filter_by(id_external=employer_id).first()
                    if not employer:
                        employer = Employer(
                            id_external=employer_id,
                            name=employer_name,
                            area=employer_area,
                            accredited_it_employer=employer_accredited,
                            open_vacancies=employer_open_vacancies
                        )
                        session.add(employer)
                        session.commit()  # Сохраняем изменения, чтобы получить id

                    # Проверка и добавление уровня опыта
                    experience_id = vacancy_data['experience']['id']
                    experience_name = vacancy_data['experience']['name']
                    experience_external_id = experience_id
                    experience = session.query(ExperienceLevel).filter_by(id_external=experience_external_id).first()
                    if not experience:
                        experience = ExperienceLevel(id_external=experience_external_id, name=experience_name)
                        session.add(experience)
                        session.commit()  # Сохраняем изменения, чтобы получить id

                    # Проверка и добавление профессиональной роли
                    professional_role_id = vacancy_data['professional_roles'][0]['id']
                    professional_role_name = vacancy_data['professional_roles'][0]['name']
                    professional_role_external_id = professional_role_id
                    professional_role = session.query(ProfessionalRole).filter_by(
                        id_external=professional_role_external_id).first()
                    if not professional_role:
                        professional_role = ProfessionalRole(id_external=professional_role_external_id,
                                                             name=professional_role_name)
                        session.add(professional_role)
                        session.commit()  # Сохраняем изменения, чтобы получить id

                    # Проверка и добавление формата работы
                    employment_form_id = vacancy_data['employment_form']['id']
                    employment_form_name = vacancy_data['employment_form']['name']
                    employment_form = session.query(EmploymentForm).filter_by(id_external=employment_form_id).first()
                    if not employment_form:
                        employment_form = EmploymentForm(id_external=employment_form_id, name=employment_form_name)
                        session.add(employment_form)
                        session.commit()  # Сохраняем изменения, чтобы получить id

                    # Проверка и добавление рабочих часов
                    working_hours_id = vacancy_data['working_hours'][0]['id']
                    working_hours_name = vacancy_data['working_hours'][0]['name']
                    working_hours = session.query(WorkingHours).filter_by(id_external=working_hours_id).first()
                    if not working_hours:
                        working_hours = WorkingHours(id_external=working_hours_id, name=working_hours_name)
                        session.add(working_hours)
                        session.commit()  # Сохраняем изменения, чтобы получить id

                    # Проверка и добавление графиков работы
                    work_schedule_data = vacancy_data.get('work_schedule_by_days', [])
                    work_schedule_ids = []  # Список для хранения id графиков работы
                    if work_schedule_data:
                        for ws in work_schedule_data:
                            work_schedule_id = ws['id']
                            work_schedule_name = ws['name']
                            work_schedule = session.query(WorkSchedule).filter_by(id_external=work_schedule_id).first()
                            if not work_schedule:
                                work_schedule = WorkSchedule(id_external=work_schedule_id, name=work_schedule_name)
                                session.add(work_schedule)
                                session.commit()  # Сохраняем изменения, чтобы получить id
                            work_schedule_ids.append(work_schedule.id)  # Добавляем id графика работы в список
                    else:
                        logging.warning(f"No work schedule found for vacancy {vacancy_data['id']}.")

                    # Проверка и добавление форматов работы
                    work_format_data = vacancy_data.get('work_format', [])
                    work_format_ids = []  # Список для хранения id форматов работы
                    if work_format_data:
                        for wf in work_format_data:
                            work_format_id = wf['id']
                            work_format_name = wf['name']
                            work_format_external_id = work_format_id
                            work_format = session.query(WorkFormat).filter_by(
                                id_external=work_format_external_id).first()
                            if not work_format:
                                work_format = WorkFormat(id_external=work_format_external_id, name=work_format_name)
                                session.add(work_format)
                                session.commit()  # Сохраняем изменения, чтобы получить id
                            work_format_ids.append(work_format.id)  # Добавляем id формата работы в список
                    else:
                        logging.warning(f"No work format found for vacancy {vacancy_data['id']}.")

                    # Проверка и добавление ключевых навыков
                    key_skills_ids = []
                    for skill_data in vacancy_data['key_skills']:
                        skill_name = skill_data['name']
                        key_skill = session.query(KeySkill).filter_by(name=skill_name).first()
                        if not key_skill:
                            key_skill = KeySkill(name=skill_name)
                            session.add(key_skill)
                            session.commit()  # Сохраняем изменения, чтобы получить id
                        key_skills_ids.append(key_skill.id)

                        # Проверка и добавление отраслей работодателя
                    industry_ids = []
                    for industry_data in employer_info['industries']:
                        industry_id = industry_data['id']
                        industry_name = industry_data['name']
                        industry = session.query(Industry).filter_by(id_external=industry_id).first()
                        if not industry:
                            industry = Industry(id_external=industry_id, name=industry_name)
                            session.add(industry)
                            session.commit()  # Сохраняем изменения, чтобы получить id
                        industry_ids.append(industry.id)

                    # Сохранение отраслей работодателя в промежуточную таблицу
                    for industry_id in industry_ids:
                        # Проверяем, существует ли запись в промежуточной таблице
                        existing_entry = session.query(employer_industries).filter_by(employer_id=employer.id,
                                                                                      industry_id=industry_id).first()
                        if not existing_entry:
                            # Если записи нет, добавляем её
                            session.execute(
                                employer_industries.insert().values(employer_id=employer.id, industry_id=industry_id))

                    # Создание объекта вакансии
                    vacancy = Vacancy(
                        external_id=vacancy_data['id'],
                        title=vacancy_data['name'],
                        employer_id=employer.id,  # Используем id работодателя
                        area=vacancy_data['area']['name'],
                        experience_id=experience.id,
                        professional_role_id=professional_role.id,
                        employment_form_id=employment_form.id,
                        working_hours_id=working_hours.id,
                        status='Активный' if not vacancy_data['archived'] else 'Архивный',
                        created_date=created_date,
                        published_date=published_date
                    )
                    session.add(vacancy)
                    session.commit()  # Сохраняем изменения, чтобы получить id вакансии

                    # Создание записи о зарплате
                    if vacancy_data.get('salary'):
                        salary_data = vacancy_data['salary_range']
                        salary = Salary(
                            salary_from=salary_data.get('from'),
                            salary_to=salary_data.get('to'),
                            currency=salary_data.get('currency'),
                            mode_id=salary_data["mode"]["id"],
                            mode_name=salary_data["mode"]["name"],
                            vacancy_id=vacancy.id  # Устанавливаем связь с вакансией
                        )
                        session.add(salary)

                    # Сохранение форматов работы и ключевых навыков в промежуточные таблицы
                    for work_format_id in work_format_ids:
                        session.execute(
                            vacancy_work_formats.insert().values(vacancy_id=vacancy.id, work_format_id=work_format_id))

                    for key_skill_id in key_skills_ids:
                        session.execute(
                            vacancy_key_skills.insert().values(vacancy_id=vacancy.id, key_skill_id=key_skill_id))

                    # Сохранение графиков работы в промежуточную таблицу
                    for work_schedule_id in work_schedule_ids:
                        session.execute(
                            vacancy_work_schedules.insert().values(vacancy_id=vacancy.id,
                                                                   work_schedule_id=work_schedule_id))

                    # Сохранение изменений в базе данных
                    session.commit()
                    successful_loads += 1
                    logging.info(f"Vacancy {vacancy_data['id']} loaded successfully.")

                except Exception as e:
                    logging.error(f"Error loading vacancy {vacancy_data['id']}: {str(e)}")
                    error_messages.append(str(e))
                    failed_loads += 1
                    session.rollback()

                # Пауза между запросами
                time.sleep(2)

            else:
                logging.error(f"Failed to fetch vacancy details for ID {vacancy_id}: {response.status_code}")
                failed_loads += 1
                error_messages.append(f"Failed to fetch vacancy details for ID {vacancy_id}: {response.status_code}")

        # Очищаем таблицу temporary_vacancies после успешной обработки
        session.query(TemporaryVacancy).delete()
        session.commit()
        logging.info("Cleared temporary_vacancies table after processing.")

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


if __name__ == "__main__":
    fetch_vacancies()  # Сбор данных о вакансиях
    # load_temp_vacancies_from_json('vacancies_data/vacancies_2025_7_4_.json')  # Укажите путь к вашему JSON файлу
    check_for_new_vacancies()  # Сверка и сбор детальной информации о новых вакансиях
