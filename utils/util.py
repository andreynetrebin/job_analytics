# util.py
import os
import json
import logging
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from dotenv import load_dotenv
from database.models import Vacancy

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def load_credentials():
    """Загружает credentials для отправки писем"""
    try:
        if not os.path.exists('token.json'):
            logging.error("token.json not found")
            return None

        with open('token.json', 'r') as token_file:
            token_data = json.load(token_file)

        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes', SCOPES)
        )

        # Обновляем токен если истек
        if creds.expired and creds.refresh_token:
            logging.info("Refreshing access token...")
            try:
                creds.refresh(Request())

                # Сохраняем обновленный токен
                new_token_data = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }

                with open('token.json', 'w') as token_file:
                    json.dump(new_token_data, token_file)

                logging.info("Access token refreshed successfully")

            except RefreshError as e:
                logging.error(f"Failed to refresh token: {e}")
                return None

        return creds

    except Exception as e:
        logging.error(f"Error loading credentials: {e}")
        return None


def send_email(subject, body, recipient_email):
    """Отправка email через Gmail API."""

    creds = load_credentials()
    if not creds:
        logging.error("Failed to load credentials")
        return False

    try:
        service = build('gmail', 'v1', credentials=creds)

        # Создаем сообщение
        message = MIMEMultipart()
        message['to'] = recipient_email
        message['from'] = os.getenv('EMAIL_HOST_USER')
        message['subject'] = subject

        # Добавляем тело письма
        msg_body = MIMEText(body, 'html')
        message.attach(msg_body)

        # Кодируем и отправляем
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        logging.info(f"Email sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        return False


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
