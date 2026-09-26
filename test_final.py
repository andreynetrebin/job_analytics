# test_final.py
import logging
from utils.util import send_email

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_final():
    """Финальный тест отправки email"""
    subject = "Отчет о вакансиях - тест"
    body = """
    <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                .header { color: #2c3e50; }
                .info { background-color: #f8f9fa; padding: 10px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1 class="header">📊 Отчет о результатах сбора вакансий</h1>
            <div class="info">
                <p><strong>Всего было получено:</strong> 1512</p>
                <p><strong>Добавлено новых вакансий:</strong> 41</p>
                <p><strong>Пропущено по причине наличия:</strong> 0</p>
                <p><strong>С ошибками:</strong> 0</p>
            </div>
            <p>Это тестовое письмо для проверки работы Gmail API.</p>
        </body>
    </html>
    """
    
    # Замените на ваш email для тестирования
    recipient = "andrew89s@mail.ru"
    
    print("🧪 Запуск финального теста отправки email...")
    success = send_email(subject, body, recipient)
    
    if success:
        print("✅ Тест пройден! Email успешно отправлен.")
    else:
        print("❌ Тест не пройден. Проверьте логи для деталей.")

if __name__ == '__main__':
    test_final()
