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
                'credentials.json', SCOPES)
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
