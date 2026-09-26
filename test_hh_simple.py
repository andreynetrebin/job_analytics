"""
Простейший тестовый скрипт для проверки работы с HH API.
Автоматически получает и обновляет токены.

Использование:
  1. Первый запуск: python test_hh_simple.py --init
  2. Последующие запуски: python test_hh_simple.py
"""

import os
import json
import time
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'https://localhost')

TOKEN_FILE = 'hh_tokens.json'
TOKEN_URL = 'https://api.hh.ru/token'
AUTH_URL = 'https://hh.ru/oauth/authorize'
BASE_URL = 'https://api.hh.ru'

# ─────────────────────────────────────────────
# Работа с токенами
# ─────────────────────────────────────────────
def get_auth_url() -> str:
    """Генерирует ссылку для первичной авторизации."""
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Обменивает authorization_code на токены."""
    payload = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    
    resp = requests.post(TOKEN_URL, data=payload, timeout=15)
    resp.raise_for_status()
    
    token_data = resp.json()
    token_data['expires_at'] = time.time() + token_data.get('expires_in', 7200) - 60
    
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2)
    
    return token_data


def refresh_token(refresh_tok: str) -> dict:
    """Обновляет токены через refresh_token."""
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_tok,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    
    resp = requests.post(TOKEN_URL, data=payload, timeout=15)
    resp.raise_for_status()
    
    token_data = resp.json()
    token_data['expires_at'] = time.time() + token_data.get('expires_in', 7200) - 60
    
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2)
    
    return token_data


def get_valid_token() -> str:
    """Возвращает валидный access_token, при необходимости обновляет его."""
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            "Токены не найдены. Запустите: python test_hh_simple.py --init"
        )
    
    with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
        tokens = json.load(f)
    
    # Проверяем срок действия
    if time.time() < tokens.get('expires_at', 0):
        return tokens['access_token']
    
    # Токен истек, обновляем
    print("⏳ Токен истек, обновляю...")
    new_tokens = refresh_token(tokens['refresh_token'])
    print("✅ Токен обновлен")
    return new_tokens['access_token']


# ─────────────────────────────────────────────
# Тестовый запрос к API
# ─────────────────────────────────────────────
def test_api():
    """Делает тестовый запрос к API HH."""
    token = get_valid_token()
    
    headers = {
        'Authorization': f'Bearer {token}',
        'User-Agent': 'HH-Test-Script/1.0',
    }
    
    params = {
        'text': 'Python разработчик',
        'per_page': 5,
        'page': 0,
    }
    
    print("\n🔍 Делаю запрос к API HH...")
    print(f"   Запрос: {params['text']}")
    print(f"   Страниц: {params['per_page']} вакансий\n")
    
    resp = requests.get(f'{BASE_URL}/vacancies', headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    
    data = resp.json()
    
    print(f"✅ Успех! Найдено вакансий: {data.get('found', 0)}")
    print(f"   Всего страниц: {data.get('pages', 0)}\n")
    
    print("=" * 70)
    print("  ПЕРВЫЕ 5 ВАКАНСИЙ:")
    print("=" * 70)
    
    for i, vacancy in enumerate(data.get('items', []), 1):
        title = vacancy.get('name', 'N/A')
        employer = vacancy.get('employer', {}).get('name', 'N/A')
        area = vacancy.get('area', {}).get('name', 'N/A')
        
        salary = vacancy.get('salary') or {}
        salary_str = "не указана"
        if salary:
            s_from = salary.get('from') or '?'
            s_to = salary.get('to') or '?'
            currency = salary.get('currency', '')
            salary_str = f"{s_from}–{s_to} {currency}"
        
        print(f"\n[{i}] {title}")
        print(f"    Компания: {employer}")
        print(f"    Город: {area}")
        print(f"    Зарплата: {salary_str}")
    
    print("\n" + "=" * 70)
    print("✅ API работает корректно!")
    print("=" * 70)


# ─────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Ошибка: CLIENT_ID и CLIENT_SECRET должны быть указаны в .env")
        sys.exit(1)
    
    if '--init' in sys.argv:
        print("\n" + "=" * 70)
        print("  ПЕРВИЧНАЯ АВТОРИЗАЦИЯ")
        print("=" * 70)
        print("\n1. Откройте эту ссылку в браузере:")
        print(f"\n   {get_auth_url()}\n")
        print("2. Войдите в аккаунт HH и нажмите 'Разрешить'.")
        print("3. Браузер перенаправит на адрес вида:")
        print("   https://localhost/?code=XXXXXXXXXX")
        print("4. Скопируйте значение параметра 'code' из адресной строки.\n")
        
        code = input("Вставьте code сюда: ").strip()
        
        if not code:
            print("❌ Код пуст")
            sys.exit(1)
        
        try:
            exchange_code(code)
            print("\n✅ Токены сохранены в hh_tokens.json")
            print("Теперь можно запускать скрипт без --init\n")
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            sys.exit(1)
    else:
        try:
            test_api()
        except FileNotFoundError as e:
            print(f"\n❌ {e}")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            print(f"\n❌ Ошибка HTTP: {e}")
            if e.response.status_code == 401:
                print("   Токен невалиден. Попробуйте: python test_hh_simple.py --init")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            sys.exit(1)
