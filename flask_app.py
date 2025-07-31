import logging
from flask import Flask, request, redirect, url_for, session, jsonify, render_template
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import json
from api_tool import RestApiTool  # Импортируйте вашу библиотеку api-tool
import os
from dotenv import load_dotenv
from database import init_db, check_db_exists, Session  # Импортируем функцию проверки
from models import SearchQuery  # Импортируем модель SearchQuery
from datetime import datetime
import pytz
from api import api_bp  # Импортируем Blueprint

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
log_file_path = 'app.log'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler(log_file_path),
    logging.StreamHandler()  # Для вывода в консоль
])

app = Flask(__name__)
# Регистрация Blueprint
app.register_blueprint(api_bp, url_prefix='/api')  # Все маршруты API будут начинаться с /api

app.secret_key = os.urandom(24)  # Секретный ключ для сессий

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Настройки API HH
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
redirect_uri = os.getenv('REDIRECT_URI')  # Получаем Redirect URI из .env
base_url = 'https://api.hh.ru'  # Базовый URL для API HH
hh_api = RestApiTool(base_url)


# Модель пользователя для Flask-Login
class User(UserMixin):
    def __init__(self, id):
        self.id = id


# Загрузка пользователя
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Здесь должна быть проверка пользователя (например, из базы данных)
        if username == 'admin' and password == os.getenv('ADMIN_PASSWORD'):
            user = User(username)
            login_user(user)
            return redirect(url_for('admin_dashboard'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    session = Session()
    queries = session.query(SearchQuery).all()
    return render_template('admin_dashboard.html', queries=queries)


@app.route('/search_queries', methods=['POST'])
def create_search_query():
    """Создание новой заявки на получение аналитической информации"""
    data = request.json
    new_query = SearchQuery(
        query=data['query'],
        is_active=False,  # По умолчанию неактивна
        created_at=datetime.now(pytz.timezone('Europe/Moscow')),
        updated_at=datetime.now(pytz.timezone('Europe/Moscow')),
        initiator=data['initiator'],
        email=data['email']
    )
    session = Session()
    session.add(new_query)
    session.commit()
    logging.info("New search query created: %s", new_query.query)
    return jsonify({"message": "Search query created successfully"}), 201


@app.route('/search_queries', methods=['GET'])
@login_required
def get_search_queries():
    """Получение всех заявок на получение аналитической информации"""
    session = Session()
    queries = session.query(SearchQuery).all()
    return jsonify([{"id": q.id, "query": q.query, "is_active": q.is_active} for q in queries]), 200


@app.route('/search_queries/<int:query_id>/approve', methods=['POST'])
@login_required
def approve_search_query(query_id):
    """Одобрение заявки на получение аналитической информации"""
    session = Session()
    query = session.query(SearchQuery).filter_by(id=query_id).first()
    if query:
        query.is_active = True
        session.commit()
        logging.info("Search query approved: %s", query.query)
        return jsonify({"message": "Search query approved successfully"}), 200
    return jsonify({"error": "Search query not found"}), 404


@app.route('/request_query', methods=['GET', 'POST'])
def request_query():
    """Форма для отправки заявки на поисковый запрос"""
    if request.method == 'POST':
        query_text = request.form['query']
        initiator = request.form['initiator']
        email = request.form['email']

        new_query = SearchQuery(
            query=query_text,
            is_active=False,  # По умолчанию неактивна
            created_at=datetime.now(pytz.timezone('Europe/Moscow')),
            updated_at=datetime.now(pytz.timezone('Europe/Moscow')),
            initiator=initiator,
            email=email
        )

        session = Session()
        session.add(new_query)
        session.commit()
        logging.info("New search query created: %s", new_query.query)
        return redirect(url_for('index'))  # Перенаправление на главную страницу после отправки
    return render_template('request_query.html')


@app.route('/login_hh')
def login_hh():
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
    session = Session()
    # Получаем активные поисковые запросы из базы данных
    active_queries = session.query(SearchQuery).filter_by(is_active=True).all()

    all_vacancies = []  # Список для хранения всех вакансий
    logging.info("Fetching vacancies with active search queries.")

    for query in active_queries:
        params = {
            'text': query.query,  # Используем текст из активного поискового запроса
            'per_page': 20,  # Количество вакансий на странице
            'page': 0,  # Начальная страница
            'date_from': '2025-07-04T00:00:00'
        }

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
            logging.info("Vacancies fetched successfully for query '%s'. Total vacancies: %d", query.query,
                         len(vacancies))

            # Сохранение данных в JSON файл для каждого поискового запроса
            date_str = datetime.now().strftime('%Y-%m-%d')  # Формат даты
            filename = f'vacancies_data/vacancies_query_{query.id}_{date_str}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(vacancies, f, ensure_ascii=False, indent=4)
                logging.info("Vacancies data saved to %s", filename)

        except Exception as e:
            logging.error("Error fetching vacancies for query '%s': %s", query.query, str(e))
            return jsonify({"error": "Failed to fetch vacancies"}), 500

    return jsonify(all_vacancies)

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
