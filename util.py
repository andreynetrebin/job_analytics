# util.py

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

def send_email(subject, body, recipient_email):
    sender_email = os.getenv('EMAIL_HOST_USER')
    sender_password = os.getenv('EMAIL_HOST_PASSWORD')

    # Создание сообщения
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    # Добавление HTML-содержимого
    msg.attach(MIMEText(body, 'html'))

    # Отправка сообщения
    try:
        logging.info("Connecting to SMTP server...")
        with smtplib.SMTP_SSL(os.getenv('EMAIL_HOST'), int(os.getenv('EMAIL_PORT'))) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            logging.info("Email sent successfully.")
    except smtplib.SMTPAuthenticationError:
        logging.error("SMTP Authentication Error: Check your email and password.")
    except smtplib.SMTPConnectError:
        logging.error("Failed to connect to the SMTP server. Check your host and port.")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
