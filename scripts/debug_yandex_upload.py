import os
import sys
import urllib3
from dotenv import load_dotenv

# ✅ ОТКЛЮЧАЕМ ПРЕДУПРЕЖДЕНИЯ О НЕБЕЗОПАСНОМ SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Добавляем корень проекта в пути импорта
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.storage.raw_storage import YandexDiskStorage
import requests

# ✅ Временно патчим requests, чтобы он игнорировал проверку сертификатов
original_request = requests.Session.request
def patched_request(self, *args, **kwargs):
    kwargs['verify'] = False
    return original_request(self, *args, **kwargs)
requests.Session.request = patched_request

def main():
    # ... остальной код без изменений ...
    load_dotenv()

    # 1. Возьмите токен из .env или вставьте его сюда напрямую для теста
    token = os.getenv("YANDEX_DISK_TOKEN", "ВСТАВЬТЕ_СЮДА_ВАШ_ТОКЕН_ИЗ_ПОЛИГОНА")

    if token == "ВСТАВЬТЕ_СЮДА_ВАШ_ТОКЕН_ИЗ_ПОЛИГОНА":
        print("⚠️ Пожалуйста, укажите реальный токен в переменной token или в файле .env")
        return

    # 2. Инициализируем хранилище
    storage = YandexDiskStorage(token=token, remote_dir="/data/job_analytics")

    # 3. Подготовим тестовые данные
    test_vacancies = [
        {
            "id": "99999999",
            "name": "Senior Data Engineer (Real Test)",
            "area": {"name": "Москва"},
            "salary": {"from": 300000, "currency": "RUB"}
        }
    ]

    print("🔄 Начинаю загрузку на Яндекс.Диск...")
    try:
        remote_path = storage.save(query="Data_Engineer_Test", vacancies=test_vacancies)
        print(f"✅ УСПЕХ! Файл сохранен по пути: {remote_path}")
        print(f"🔗 Проверьте его в веб-интерфейсе: https://disk.yandex.ru/client/disk{remote_path}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")


if __name__ == "__main__":
    main()