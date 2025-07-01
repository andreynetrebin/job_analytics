import logging
from flask import Flask, request, redirect, url_for, session, jsonify
import mysql.connector
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
import os
from dotenv import load_dotenv

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

# Настройки базы данных
db_config = {
    'user': 'your_db_user',
    'password': 'your_db_password',
    'host': 'your_db_host',
    'database': 'your_db_name'
}

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
        'area': '1',  # ID для Москва
        'text': 'Data Engineer'
    }

    logging.info("Fetching vacancies with parameters: %s", params)

    # Получение вакансий из API HH с параметрами
    try:
        vacancies = hh_api.get('vacancies', params=params)
        logging.info("Vacancies fetched successfully.")

        # Логирование результата
        logging.info("Vacancies data: %s", vacancies)

        return jsonify(vacancies)
    except Exception as e:
        logging.error("Error fetching vacancies: %s", str(e))
        return jsonify({"error": "Failed to fetch vacancies"}), 500


if __name__ == '__main__':
    app.run(debug=True)
