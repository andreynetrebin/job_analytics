import logging
from flask import Flask, request, redirect, url_for, session, jsonify
import json
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
import os
from dotenv import load_dotenv
from database import init_db, check_db_exists  # Импортируем функцию проверки

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
log_file_path = 'app.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler(log_file_path),
    logging.StreamHandler()  # Для вывода в консоль
])

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Секретный ключ для сессий

# Настройки API HH
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
redirect_uri = os.getenv('REDIRECT_URI')  # Получаем Redirect URI из .env
base_url = 'https://api.hh.ru'  # Базовый URL для API HH
hh_api = RestApiTool(base_url)


@app.route('/')
def index():
    return 'Welcome to the HH API App! <a href="/login">Login with HH</a>'


@app.route('/login')
def login():
    # Перенаправление на страницу авторизации HH
    auth_url = f"https://hh.ru/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"
    logging.info("Redirecting to HH authorization URL.")
    return redirect(auth_url)


@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        if code:
            logging.info("Received authorization code.")
            # Подготовка данных для запроса
            data = {
                'client_id': os.getenv('CLIENT_ID'),
                'client_secret': os.getenv('CLIENT_SECRET'),
                'code': code,
                'redirect_uri': os.getenv('REDIRECT_URI'),
                'grant_type': 'authorization_code'
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            # Отправка POST запроса на новый URL
            token_response = hh_api.post_form('token', data=data, headers=headers)
            logging.info("Token response: %s", token_response)

            access_token = token_response.get('access_token')
            refresh_token = token_response.get('refresh_token')
            hh_api.set_token(access_token)  # Установка токена для дальнейших запросов

            return redirect(url_for('get_vacancies'))
        logging.error("Authorization failed: No code received.")
        return 'Authorization failed', 400
    except Exception as e:
        logging.error("Error in callback: %s", str(e))
        return 'Internal Server Error', 500


@app.route('/vacancies', methods=['GET'])
def get_vacancies():
    # Параметры для фильтрации вакансий
    params = {
        'text': 'Data Engineer',
        'per_page': 20,  # Количество вакансий на странице
        'page': 0,  # Начальная страница
        'date_from': '2025-07-04T00:00:00'
    }
    all_vacancies = []  # Список для хранения всех вакансий
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
        logging.info("Vacancies fetched successfully. Total vacancies: %d", len(all_vacancies))
        # Сохранение данных в JSON файл
        with open('vacancies_data/vacancies.json', 'w', encoding='utf-8') as f:
            json.dump(all_vacancies, f, ensure_ascii=False, indent=4)
            logging.info("Vacancies data saved to vacancies.json")
        return jsonify(all_vacancies)
    except Exception as e:
        logging.error("Error fetching vacancies: %s", str(e))
        return jsonify({"error": "Failed to fetch vacancies"}), 500


@app.route('/vacancy/<int:vacancy_id>', methods=['GET'])
def get_vacancy_by_id(vacancy_id):
    """Получение вакансии по ID"""
    try:
        vacancy = hh_api.get(f'vacancies/{vacancy_id}')
        logging.info("Vacancy fetched successfully: %s", vacancy_id)
        return jsonify(vacancy), 200, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        logging.error("Error fetching vacancy by ID: %s", str(e))
        return jsonify({"error": "Failed to fetch vacancy"}), 500


@app.route('/employers/<int:employer_id>', methods=['GET'])
def get_employer_by_id(employer_id):
    """Получение компании по ID"""
    try:
        employer = hh_api.get(f'employers/{employer_id}')
        logging.info("Employer fetched successfully: %s", employer_id)
        return jsonify(employer), 200, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        logging.error("Error fetching employer by ID: %s", str(e))
        return jsonify({"error": "Failed to fetch employer"}), 500


if __name__ == '__main__':
    if not check_db_exists():  # Проверяем, существует ли база данных
        init_db()  # Инициализация базы данных только если она не существует
    app.run(debug=True)
