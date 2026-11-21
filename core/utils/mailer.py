import os
import smtplib
import logging
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_email_report(query: str, report_text: str) -> bool:
    """
    Отправляет текстовый LLM-отчет на почту администратора,
    используя настройки из .env (EMAIL_HOST, EMAIL_PORT и т.д.).
    """
    admin_email = os.getenv("ADMIN_EMAIL")
    smtp_server = os.getenv("EMAIL_HOST")
    smtp_port = int(os.getenv("EMAIL_PORT", 465))
    smtp_user = os.getenv("EMAIL_HOST_USER")
    smtp_password = os.getenv("EMAIL_HOST_PASSWORD")

    if not all([admin_email, smtp_server, smtp_user, smtp_password]):
        logger.warning("⚠️ Настройки EMAIL в .env не полные. Отправка письма пропущена.")
        logger.warning("Проверьте: ADMIN_EMAIL, EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD")
        return False

    msg = EmailMessage()
    msg['Subject'] = f"📊 LLM-Отчет по рынку труда: {query}"
    msg['From'] = smtp_user
    msg['To'] = admin_email
    msg.set_content(report_text)

    try:
        # Mail.ru и другие провайдеры для 465 порта требуют SMTP_SSL
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()

        logger.info(f"✅ Отчет успешно отправлен на {admin_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "❌ Ошибка аутентификации SMTP. Проверьте EMAIL_HOST_PASSWORD (для Mail.ru это должен быть 'пароль для внешних приложений').")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки email: {e}")
        return False