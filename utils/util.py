# util.py

import os
import logging
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv
from database.models import Vacancy

# Загружаем переменные окружения из файла .env
load_dotenv()

# Если измените эти области, удалите файл token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def send_email(subject, body, recipient_email):
    """Отправка email через Gmail API."""

    # Получаем учетные данные
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # Если нет (действительных) учетных данных, запрашиваем их у пользователя.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',
                SCOPES)
            creds = flow.run_local_server(port=0)
        # Сохраняем учетные данные для следующего запуска
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Создание сообщения
    msg = MIMEMultipart()
    msg['From'] = os.getenv('EMAIL_HOST_USER')
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    # Отправка сообщения
    try:
        logging.info("Connecting to Gmail API...")
        service = build('gmail', 'v1', credentials=creds)
        message = {'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        service.users().messages().send(userId='me', body=message).execute()
        logging.info("Email sent successfully to %s", recipient_email)  # Логирование адреса получателя
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")


def create_email_body(new_vacancies, session, query):
    html = f"""
    <html>
    <head>
        <style>
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                border: 1px solid #dddddd;
                text-align: left;
                padding: 8px;
            }}
            th {{
                background-color: #f2f2f2;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
        </style>
    </head>
    <body>
        <h2>Новые вакансии по запросу: "{query.query}"</h2>
        <table>
            <tr>
                <th>Название</th>
                <th>Профессиональная роль</th>
                <th>Город</th>
                <th>Зарплата</th>
                <th>Опыт</th>
                <th>Формат работы</th>
                <th>Работодатель</th>
                <th>IT-аккредитация</th>
                <th>Рейтинг</th>
                <th>Кол-во оценок</th>
            </tr>
    """
    new_vacancies = sorted(new_vacancies, key=lambda x: (
        session.query(Vacancy).filter_by(external_id=x['id']).first().employer.open_vacancies if session.query(
            Vacancy).filter_by(external_id=x['id']).first() and session.query(Vacancy).filter_by(
            external_id=x['id']).first().employer else 0
    ), reverse=True)

    for vacancy_data in new_vacancies:
        # Получаем вакансию из базы данных по external_id
        vacancy = session.query(Vacancy).filter_by(external_id=vacancy_data['id']).first()

        if vacancy:
            title = f'<a href="https://hh.ru/vacancy/{vacancy_data["id"]}">{vacancy.title}</a>'
            employer = f'<a href="https://hh.ru/employer/{vacancy.employer.id_external}">{vacancy.employer.name}</a>' if vacancy.employer else 'Неизвестен'
            area = vacancy.area if vacancy.area else 'Не указан'
            experience = vacancy.experience.name if vacancy.experience else 'Не указан'
            work_format = ', '.join([wf.name for wf in vacancy.work_formats]) if vacancy.work_formats else 'Не указан'
            professional_role = vacancy.professional_role.name if vacancy.professional_role else 'Не указана'
            it_accredited = 'Да' if vacancy.employer.accredited_it_employer else 'Нет'
            total_rating = vacancy.employer.total_rating if vacancy.employer else 'Не указан'
            reviews_count = vacancy.employer.reviews_count if vacancy.employer else 'Не указано'

            # Получаем информацию о зарплате
            salary_history = vacancy.salary_history  # Получаем связанные записи SalaryHistory
            if salary_history:
                active_salary = next((sh for sh in salary_history if sh.is_active), None)
                if active_salary:
                    salary = f"{active_salary.salary_from} - {active_salary.salary_to} {active_salary.currency}"
                else:
                    salary = 'Не указана'
            else:
                salary = 'Не указана'

            html += f"""
                <tr>
                    <td>{title}</td>
                    <td>{professional_role}</td>
                    <td>{area}</td>
                    <td>{salary}</td>
                    <td>{experience}</td>
                    <td>{work_format}</td>
                    <td>{employer}</td>
                    <td>{it_accredited}</td>
                    <td>{total_rating}</td>
                    <td>{reviews_count}</td>
                </tr>
            """

    html += """
        </table>
        <h2>Топ-10 ключевых навыков</h2>
        <table>
            <tr>
                <th>Ключевой навык</th>
                <th>Количество вакансий</th>
            </tr>
    """

    # Анализ ключевых навыков
    skill_counts = {}
    for vacancy_data in new_vacancies:
        vacancy = session.query(Vacancy).filter_by(external_id=vacancy_data['id']).first()
        if vacancy:
            for skill in vacancy.key_skill_history:
                skill_name = skill.key_skill.name
                if skill_name in skill_counts:
                    skill_counts[skill_name] += 1
                else:
                    skill_counts[skill_name] = 1

    # Сортировка навыков по количеству вакансий и выбор топ-10
    top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    for skill, count in top_skills:
        html += f"""
            <tr>
                <td>{skill}</td>
                <td>{count}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """
    return html
