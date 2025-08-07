import json
import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import pytz
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
from utils.util import send_email, create_email_body
from database.models import Vacancy, ExperienceLevel, WorkFormat, KeySkill, ProfessionalRole, \
    EmploymentForm, WorkingHours, WorkSchedule, vacancy_work_formats, vacancy_work_schedules, \
    Employer, Industry, employer_industries, SearchQuery, VacancyStatusHistory, KeySkillHistory, SalaryHistory, \
    search_query_vacancies
from database.database import Session  # Импортируем Session из database.py

# Настройка логирования
log_file_path = 'logs/job_analytics.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file_path), logging.StreamHandler()])

# Получаем текущий рабочий каталог
current_dir = os.path.dirname(os.path.abspath(__file__))
# Устанавливаем рабочий каталог на текущий каталог
os.chdir(current_dir)

# Загрузка переменных окружения
load_dotenv()

# Настройки API HH
base_url = 'https://api.hh.ru'  # Базовый URL для API HH
hh_api = RestApiTool(base_url)

moscow_tz = pytz.timezone('Europe/Moscow')


def parse_datetime(date_str):
    """Преобразуем строку даты в формат, который понимает MySQL."""
    dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S%z')
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def fetch_vacancies_from_file(session, query):
    """Загрузка данных о вакансиях из файла и сохранение в базу данных с обработкой повторных попыток."""
    filename = f'vacancies_data/vacancies_query_{query.id}_2025-07-28.json'

    if not os.path.exists(filename):
        logging.error(f"Файл {filename} не найден.")
        return

    with open(filename, 'r', encoding='utf-8') as f:
        all_vacancies = json.load(f)
        logging.info(f"Vacancies loaded from {filename}. Total vacancies: {len(all_vacancies)}")

    error_ids = []
    missing_status_ids = []  # Список для вакансий с отсутствующим статусом
    new_vacancies_count = 0
    skipped_vacancies_count = 0
    error_count = 0
    new_vacancies = []  # Список для хранения новых вакансий

    try:
        # Получаем все вакансии из базы данных для текущего поискового запроса
        existing_vacancy_ids = session.query(search_query_vacancies.c.vacancy_id).filter_by(
            search_query_id=query.id).all()
        existing_vacancy_ids = {vacancy_id for (vacancy_id,) in existing_vacancy_ids}  # Извлекаем только ID

        # Список внешних ID полученных вакансий
        fetched_vacancy_ids = {vacancy['id'] for vacancy in all_vacancies}

        # Проверяем, какие вакансии отсутствуют среди полученных
        missing_vacancy_ids = existing_vacancy_ids - fetched_vacancy_ids

        # Находим новые вакансии
        new_vacancy_ids = fetched_vacancy_ids - existing_vacancy_ids

        # Обработка новых вакансий
        for new_id in new_vacancy_ids:
            # Находим вакансию в all_vacancies по ID
            vacancy = next((v for v in all_vacancies if v['id'] == new_id), None)
            if vacancy:
                try:
                    process_vacancy(vacancy, session, query)
                    new_vacancies_count += 1
                    new_vacancies.append(vacancy)  # Добавляем вакансию в список новых
                except Exception as e:
                    logging.error(f"Error processing vacancy {vacancy['id']}: {str(e)}")
                    error_ids.append(vacancy['id'])
                    error_count += 1
            else:
                logging.warning(f"Vacancy with ID {new_id} not found in all_vacancies.")

        # Обработка отсутствующих вакансий
        for missing_id in missing_vacancy_ids:
            logging.info(f"Vacancy with external ID {missing_id} is missing from the fetched data. Checking status.")
            missing_vacancy = session.query(Vacancy).filter_by(external_id=missing_id).first()
            if missing_vacancy:
                # Запрашиваем актуальный статус вакансии
                vacancy_details = hh_api.get(f'vacancies/{missing_id}')
                time.sleep(2)

                # Обработка ответа с кодом 404
                if vacancy_details.get('status_code') == 404:
                    logging.error(f"Vacancy {missing_id} returned 404. Adding to missing status list.")
                    missing_status_ids.append(missing_id)  # Добавляем в отдельный список
                    continue  # Пропускаем дальнейшую обработку для этой вакансии

                if vacancy_details.get('archived', False):
                    # Если статус архивный, обновляем статус в базе
                    update_vacancy_status_to_archived(missing_vacancy, session)
                else:
                    logging.info(f"Vacancy {missing_id} is still active.")
                    skipped_vacancies_count += 1

    except Exception as e:
        logging.error(f"Error fetching vacancies for query '{query.query}': {str(e)}")
        session.rollback()  # Rollback in case of error

    # Отчет о результатах
    total_vacancies = len(all_vacancies)
    logging.info("Отчет о результатах сбора вакансий:")
    logging.info(f"Всего было получено: {total_vacancies}")
    logging.info(f"Добавлено новых вакансий: {new_vacancies_count}")
    logging.info(f"Пропущено по причине наличия: {skipped_vacancies_count}")
    logging.info(f"С ошибками: {error_count}")
    if error_ids:
        logging.info(f"ID вакансий с ошибками: {error_ids}")

        # Повторная попытка сохранения вакансий с ошибками
        retry_vacancies(session, query.id, error_ids)

    # Отчет о вакансиях с отсутствующим статусом
    if missing_status_ids:
        logging.info(f"ID вакансий по которым при проверке не получен актуальный статус: {missing_status_ids}")

    # Отправка уведомления по электронной почте, если есть новые вакансии
    if new_vacancies:
        email_body = create_email_body(new_vacancies, session, query)  # Передаем сессию и запрос
        send_email("Новые вакансии по запросу: " + query.query, email_body,
                   query.email)  # Используем email из SearchQuery


def fetch_vacancies(session, query):
    """Сбор данных о вакансиях и сохранение в базу данных с обработкой повторных попыток."""
    params = {
        'text': query.query,
        'per_page': 20,
        'page': 0,
    }
    logging.info(f"Fetching vacancies with parameters: {params}")
    all_vacancies = []
    error_ids = []
    missing_status_ids = []  # Список для вакансий с отсутствующим статусом
    new_vacancies_count = 0
    skipped_vacancies_count = 0
    error_count = 0
    new_vacancies = []  # Список для хранения новых вакансий

    max_retries = 5  # Максимальное количество попыток
    for attempt in range(max_retries):
        try:
            while True:
                response = hh_api.get('vacancies', params=params)
                vacancies = response.get('items', [])
                all_vacancies.extend(vacancies)
                if response.get('pages', 0) <= params['page'] + 1:
                    break
                params['page'] += 1
                time.sleep(10)

            logging.info(
                f"Vacancies fetched successfully for query '{query.query}'. Total vacancies: {len(all_vacancies)}")

            date_str = datetime.now().strftime('%Y-%m-%d')
            filename = f'vacancies_data/vacancies_query_{query.id}_{date_str}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(all_vacancies, f, ensure_ascii=False, indent=4)
                logging.info(f"Vacancies data saved to {filename}")
            time.sleep(5)

            # Получаем все вакансии из базы данных для текущего поискового запроса
            existing_vacancy_ids = session.query(Vacancy.external_id).join(
                search_query_vacancies
            ).filter(
                search_query_vacancies.c.search_query_id == query.id
            ).all()

            # Извлекаем только external_id
            existing_vacancy_ids = {external_id for (external_id,) in existing_vacancy_ids}

            # Список внешних ID полученных вакансий
            fetched_vacancy_ids = {vacancy['id'] for vacancy in all_vacancies}

            # Проверяем, какие вакансии отсутствуют среди полученных
            missing_vacancy_ids = existing_vacancy_ids - fetched_vacancy_ids

            # Находим новые вакансии
            new_vacancy_ids = fetched_vacancy_ids - existing_vacancy_ids

            # Обработка новых вакансий
            for new_id in new_vacancy_ids:
                # Находим вакансию в all_vacancies по ID
                vacancy = next((v for v in all_vacancies if v['id'] == new_id), None)
                if vacancy:
                    try:
                        process_vacancy(vacancy, session, query)
                        new_vacancies_count += 1
                        new_vacancies.append(vacancy)  # Добавляем вакансию в список новых
                    except Exception as e:
                        logging.error(f"Error processing vacancy {vacancy['id']}: {str(e)}")
                        error_ids.append(vacancy['id'])
                        error_count += 1
                else:
                    logging.warning(f"Vacancy with ID {new_id} not found in all_vacancies.")
                time.sleep(2)

            # Обработка отсутствующих вакансий
            for missing_id in missing_vacancy_ids:
                logging.info(
                    f"Vacancy with external ID {missing_id} is missing from the fetched data. Checking status.")
                missing_vacancy = session.query(Vacancy).filter_by(external_id=missing_id).first()
                if missing_vacancy:
                    # Запрашиваем актуальный статус вакансии
                    vacancy_details = hh_api.get(f'vacancies/{missing_id}')
                    time.sleep(2)

                    # Обработка ответа с кодом 404
                    if vacancy_details.get('status_code') == 404:
                        logging.error(f"Vacancy {missing_id} returned 404. Adding to missing status list.")
                        missing_status_ids.append(missing_id)  # Добавляем в отдельный список
                        continue  # Пропускаем дальнейшую обработку для этой вакансии

                    if vacancy_details.get('archived', False):
                        # Получаем последнюю запись в истории статусов для данной вакансии с наибольшим id
                        last_status_history = session.query(VacancyStatusHistory).filter_by(
                            vacancy_id=missing_vacancy.id).order_by(VacancyStatusHistory.id.desc()).first()
                        if last_status_history is None or last_status_history.type_changed != "Отправлена в архив":
                            # Если статус архивный, обновляем статус в базе
                            update_vacancy_status_to_archived(missing_vacancy, session)
                        else:
                            logging.info(f"Vacancy {missing_id} is already archive.")
                    else:
                        logging.info(f"Vacancy {missing_id} is still active.")
                        skipped_vacancies_count += 1
            break  # Выход из цикла, если все прошло успешно

        except Exception as e:
            logging.error(f"Error fetching vacancies for query '{query.query}': {str(e)}")
            session.rollback()  # Rollback in case of error
            if attempt < max_retries - 1:
                logging.info("Retrying...")
                time.sleep(5)  # Ожидание перед повторной попыткой

    # Отчет о результатах
    total_vacancies = len(all_vacancies)
    logging.info("Отчет о результатах сбора вакансий:")
    logging.info(f"Всего было получено: {total_vacancies}")
    logging.info(f"Добавлено новых вакансий: {new_vacancies_count}")
    logging.info(f"Пропущено по причине наличия: {skipped_vacancies_count}")
    logging.info(f"С ошибками: {error_count}")
    if error_ids:
        logging.info(f"ID вакансий с ошибками: {error_ids}")

        # Повторная попытка сохранения вакансий с ошибками
        retry_vacancies(session, query.id, error_ids)

    # Отчет о вакансиях с отсутствующим статусом
    if missing_status_ids:
        logging.info(f"ID вакансий по которым при проверке не получен актуальный статус: {missing_status_ids}")

    # Отправка уведомления по электронной почте, если есть новые вакансии
    if new_vacancies:
        email_body = create_email_body(new_vacancies, session, query)  # Передаем сессию и запрос
        send_email("Новые вакансии по запросу: " + query.query, email_body,
                   query.email)  # Используем email из SearchQuery

    # Формирование отчета для админского ящика
    admin_email_body = (
        f"Отчет о собранных вакансиях по запросу: {query.query}\n"
        f"Всего вакансий: {total_vacancies}\n"
        f"Новых вакансий: {new_vacancies_count}\n"
        f"Пропущено по причине наличия: {skipped_vacancies_count}\n"
        f"С ошибками: {error_count}\n"
    )
    if error_ids:
        admin_email_body += f"ID вакансий с ошибками: {', '.join(map(str, error_ids))}\n"
    if missing_status_ids:
        admin_email_body += f"ID вакансий с отсутствующим статусом: {', '.join(map(str, missing_status_ids))}\n"
    # Отправка отчета на админский ящик
    admin_email = os.getenv('ADMIN_EMAIL')  # Замените на реальный адрес админа
    send_email("Отчет о собранных вакансиях", admin_email_body, admin_email)


def retry_vacancies(session, query_id, error_ids):
    """Повторная попытка сохранения вакансий по списку error_ids."""
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f'vacancies_data/vacancies_query_{query_id}_{date_str}.json'

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            all_vacancies = json.load(f)

        for vacancy_id in error_ids:
            # Находим вакансию по ID
            vacancy_data = next((vacancy for vacancy in all_vacancies if vacancy['id'] == vacancy_id), None)
            if vacancy_data:
                try:
                    process_vacancy(vacancy_data, session, session.query(SearchQuery).filter_by(id=query_id).first())
                    logging.info(f"Vacancy {vacancy_id} processed successfully on retry.")
                except Exception as e:
                    logging.error(f"Error processing vacancy {vacancy_id} on retry: {str(e)}")
    except FileNotFoundError:
        logging.error(f"File {filename} not found. Cannot retry vacancies.")
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file {filename}.")


def update_vacancy_status_to_archived(vacancy, session):
    """Обновление статуса вакансии на 'Архивный'."""
    # Создаем запись в VacancyStatusHistory
    if vacancy.updated_at.tzinfo is None:
        vacancy.updated_at = moscow_tz.localize(vacancy.updated_at)

    vacancy_status_history = VacancyStatusHistory(
        vacancy_id=vacancy.id,
        prev_status="Активный",
        cur_status="Архивный",
        created_at_prev_status=vacancy.updated_at,
        created_at_cur_status=datetime.now(moscow_tz),
        duration=(datetime.now(moscow_tz) - vacancy.updated_at).days,
        type_changed="Отправлена в архив"
    )
    session.add(vacancy_status_history)

    # Обновляем статус вакансии
    vacancy.status = "Архивный"
    vacancy.updated_at = datetime.now(moscow_tz)

    session.commit()
    logging.info(f"Vacancy {vacancy.external_id} status updated to 'Архивный'.")


def process_vacancy(vacancy_data, session, query):
    """Обработка и сохранение вакансии в базу данных."""
    external_id = vacancy_data['id']

    existing_vacancy = session.query(Vacancy).filter_by(external_id=external_id).first()
    if existing_vacancy:
        existing_search_query_ids = {sq.id for sq in existing_vacancy.search_queries}
        if query.id not in existing_search_query_ids:
            # Если вакансия существует, но под другим search_query_id, добавляем связь
            session.execute(
                search_query_vacancies.insert().values(search_query_id=query.id, vacancy_id=existing_vacancy.id))
            logging.info(f"Vacancy {external_id} already exists. Added relation to search query {query.id}.")
        else:
            logging.info(f"Vacancy {external_id} is already linked to search query {query.id}. Skipping.")
        return  # Вакансия уже существует, пропускаем
    try:
        # Создаем новую вакансию
        create_vacancy(vacancy_data, session, query)
    except Exception as e:
        logging.error(f"Error processing vacancy {external_id}: {str(e)}")


def revive_vacancy(existing_vacancy, vacancy_data, session):
    """Возобновление архивной вакансии."""
    # Обновляем статус вакансии
    existing_vacancy.status = "Активный"
    if existing_vacancy.updated_at.tzinfo is None:
        existing_vacancy.updated_at = moscow_tz.localize(existing_vacancy.updated_at)

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
    time.sleep(1)
    # Получаем детальную информацию о вакансии для получения ключевых навыков
    vacancy_details = hh_api.get(f'vacancies/{vacancy_data["id"]}')

    # Обновляем историю зарплаты
    update_salary_history(existing_vacancy, vacancy_details, session)

    # Обновляем ключевые навыки
    update_key_skills(existing_vacancy, vacancy_details, session)

    existing_vacancy.updated_at = datetime.now(moscow_tz)
    existing_vacancy.published_date = parse_datetime(
        vacancy_data['published_at']) if 'published_at' in vacancy_data else existing_vacancy.published_date

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

    # Получаем текущие активные ключевые навыки
    current_key_skills = {ks.key_skill_id for ks in existing_vacancy.key_skill_history if ks.is_active}
    # Получаем новые ключевые навыки из деталей вакансии
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
    new_skill_ids = {session.query(KeySkill).filter_by(name=skill_name).first().id for skill_name in
                     new_key_skills.keys() if session.query(KeySkill).filter_by(name=skill_name).first()}

    for existing_skill_id in current_key_skills:
        if existing_skill_id not in new_skill_ids:
            # Деактивируем старую запись
            skill_history = session.query(KeySkillHistory).filter_by(vacancy_id=existing_vacancy.id,
                                                                     key_skill_id=existing_skill_id,
                                                                     is_active=True).first()
            if skill_history:
                skill_history.is_active = False
                skill_history.updated_at = datetime.now(moscow_tz)
                logging.info(
                    f"Key skill with ID {existing_skill_id} deactivated for vacancy {existing_vacancy.external_id}.")

    # Проверяем, есть ли среди новых навыков те, которые были деактивированы
    for skill_name in new_key_skills.keys():
        key_skill = session.query(KeySkill).filter_by(name=skill_name).first()
        if key_skill:
            # Проверяем, есть ли история для этого навыка
            skill_history = session.query(KeySkillHistory).filter_by(vacancy_id=existing_vacancy.id,
                                                                     key_skill_id=key_skill.id,
                                                                     is_active=False).first()
            if skill_history:
                # Если навык был деактивирован, активируем его
                skill_history.is_active = True
                skill_history.updated_at = datetime.now(moscow_tz)
                logging.info(f"Key skill '{skill_name}' reactivated for vacancy {existing_vacancy.external_id}.")

    session.commit()


def create_vacancy(vacancy_data, session, query):
    """Создание объекта вакансии."""
    try:
        # Получаем детальную информацию о вакансии для получения ключевых навыков и дат
        time.sleep(1)
        vacancy_details = hh_api.get(f'vacancies/{vacancy_data["id"]}')

        # Получаем информацию о работодателе из детальной информации о вакансии
        employer_info = vacancy_data['employer']
        employer_id = employer_info['id']
        time.sleep(1)
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
            published_date=published_date
        )
        session.add(vacancy)
        session.commit()  # Сохраняем изменения, чтобы получить id вакансии

        # Создаем запись в таблице search_query_vacancies
        session.execute(search_query_vacancies.insert().values(search_query_id=query.id, vacancy_id=vacancy.id))

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
            # fetch_vacancies_from_file(session, query)  # Сбор данных о вакансиях
            fetch_vacancies(session, query)  # Сбор данных о вакансиях


if __name__ == "__main__":
    main()
