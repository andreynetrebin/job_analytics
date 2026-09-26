import logging
from flask import Flask, request, redirect, url_for, jsonify, render_template
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import json
import os
from dotenv import load_dotenv
from database.database import init_db, check_db_exists, Session
from database.models import SearchQuery
from datetime import datetime
import pytz
from api import api_bp
from utils.util import send_email
import requests

from hh_auth import HHAuthManager

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
os.makedirs('logs', exist_ok=True)
log_file_path = 'logs/app.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Регистрация Blueprint
app.register_blueprint(api_bp, url_prefix='/api')
app.secret_key = os.urandom(24)

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Инициализация менеджера авторизации
auth_manager = HHAuthManager()

# Настройки API HH
BASE_URL = 'https://api.hh.ru'

# Модель пользователя для Flask-Login
class User(UserMixin):
    def __init__(self, id):
        self.id = id


@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


def get_api_session() -> requests.Session:
    """
    Создает requests.Session с валидным токеном авторизации
    и правильным User-Agent для API HH.
    """
    session = requests.Session()
    token = auth_manager.get_valid_token()
    
    # ВАЖНО: HH API требует User-Agent в формате:
    # ApplicationName/version (contact@email.com)
    app_email = os.getenv('APP_EMAIL') or os.getenv('ADMIN_EMAIL') or 'noemail@example.com'
    user_agent = f'HH-Job-Analytics/1.0 ({app_email})'
    
    session.headers.update({
        'Authorization': f'Bearer {token}',
        'User-Agent': user_agent,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    
    logger.info(f"Created API session with User-Agent: {user_agent}")
    return session

# ─────────────────────────────────────────────
# Основные страницы
# ─────────────────────────────────────────────
@app.route('/')
def index():
    token_info = auth_manager.get_token_info()
    return render_template('index.html', token_info=token_info)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == os.getenv('ADMIN_PASSWORD'):
            user = User(username)
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        return render_template('login.html', error='Неверный логин или пароль')
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
    token_info = auth_manager.get_token_info()
    return render_template('admin_dashboard.html', queries=queries, token_info=token_info)


# ─────────────────────────────────────────────
# OAuth HH (авторизация)
# ─────────────────────────────────────────────
@app.route('/login_hh')
def login_hh():
    """Перенаправление на страницу авторизации HH."""
    auth_url = auth_manager.get_auth_url()
    logger.info(f"Redirecting to HH authorization URL: {auth_url}")
    return redirect(auth_url)


@app.route('/callback')
def callback():
    """
    Обработчик редиректа от HH OAuth.
    Получает authorization_code, обменивает его на токены и сохраняет их в файл.
    """
    try:
        code = request.args.get('code')
        error = request.args.get('error')

        if error:
            logger.error(f"HH OAuth error: {error}")
            return jsonify({'error': f'OAuth error: {error}'}), 400

        if not code:
            logger.error("No authorization code received")
            return jsonify({'error': 'No authorization code received'}), 400

        logger.info("✅ Received authorization code")

        # Обмениваем code на токены
        token_data = auth_manager.exchange_code(code)

        # Возвращаем HTML-страницу успеха
        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>Авторизация HH успешна</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .success {{
                    background: #d4edda;
                    color: #155724;
                    padding: 20px;
                    border-radius: 8px;
                    border: 1px solid #c3e6cb;
                }}
                .info {{
                    background: #fff;
                    padding: 15px;
                    border-radius: 8px;
                    margin-top: 20px;
                    border: 1px solid #ddd;
                }}
                a {{
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <div class="success">
                <h2>✅ Авторизация успешна!</h2>
                <p>Токены получены и сохранены в <code>hh_tokens.json</code></p>
                <p>Теперь можно работать с API HH. Токены будут автоматически обновляться при истечении.</p>
            </div>
            <div class="info">
                <p><strong>Тип токена:</strong> {token_data.get('token_type', 'bearer')}</p>
                <p><strong>Время жизни access_token:</strong> {token_data.get('expires_in', '?')} секунд</p>
                <p><strong>Refresh token:</strong> {'✅ получен' if token_data.get('refresh_token') else '❌ отсутствует'}</p>
            </div>
            <a href="/">← Вернуться на главную</a>
            <a href="/vacancies">Перейти к вакансиям →</a>
        </body>
        </html>
        """

    except Exception as e:
        logger.error(f"Error in callback: {e}", exc_info=True)
        return jsonify({'error': f'Internal error: {str(e)}'}), 500


# ─────────────────────────────────────────────
# Статус токенов
# ─────────────────────────────────────────────
@app.route('/token_status')
def token_status():
    """Возвращает текущий статус токенов."""
    info = auth_manager.get_token_info()
    return jsonify(info)


@app.route('/logout_hh')
@login_required
def logout_hh():
    """Удаляет сохраненные токены."""
    if os.path.exists('hh_tokens.json'):
        os.remove('hh_tokens.json')
        logger.info("Токены удалены")
        return jsonify({'message': 'Токены успешно удалены'})
    return jsonify({'message': 'Токенов не было'})


# ─────────────────────────────────────────────
# Работа с вакансиями
# ─────────────────────────────────────────────
@app.route('/vacancies', methods=['GET'])
def get_vacancies():
    """Получение вакансий по активным поисковым запросам."""
    db_session = Session()
    try:
        active_queries = db_session.query(SearchQuery).filter_by(is_active=True).all()

        if not active_queries:
            return jsonify({
                'message': 'Нет активных поисковых запросов',
                'total': 0,
                'queries': [],
            })

        # Создаем сессию с валидным токеном
        api_session = get_api_session()
        all_vacancies = []
        results = []

        for query in active_queries:
            params = {
                'text': query.query,
                'per_page': 20,
                'page': 0,
                'date_from': '2025-07-04T00:00:00',
            }
            logger.info(f"Fetching vacancies for query '{query.query}' with params: {params}")

            query_vacancies = []
            try:
                while True:
                    # Используем requests напрямую с валидным токеном
                    resp = api_session.get(f'{BASE_URL}/vacancies', params=params, timeout=15)
                    resp.raise_for_status()
                    response = resp.json()

                    vacancies = response.get('items', [])
                    query_vacancies.extend(vacancies)

                    if response.get('pages', 0) <= params['page'] + 1:
                        break
                    params['page'] += 1

                logger.info(
                    f"Vacancies fetched successfully for query '{query.query}'. "
                    f"Total: {len(query_vacancies)}"
                )

                # Сохранение данных в JSON файл
                os.makedirs('vacancies_data', exist_ok=True)
                date_str = datetime.now().strftime('%Y-%m-%d')
                filename = f'vacancies_data/vacancies_query_{query.id}_{date_str}.json'
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(query_vacancies, f, ensure_ascii=False, indent=4)
                    logger.info(f"Vacancies data saved to {filename}")

                all_vacancies.extend(query_vacancies)
                results.append({
                    'query_id': query.id,
                    'query': query.query,
                    'count': len(query_vacancies),
                    'file': filename,
                })

            except requests.exceptions.HTTPError as http_err:
                logger.error(
                    f"HTTP error for query '{query.query}': "
                    f"{http_err.response.status_code} - {http_err.response.text[:500]}"
                )
                results.append({
                    'query_id': query.id,
                    'query': query.query,
                    'error': f'HTTP {http_err.response.status_code}',
                })
            except Exception as e:
                logger.error(f"Error fetching vacancies for query '{query.query}': {e}", exc_info=True)
                results.append({
                    'query_id': query.id,
                    'query': query.query,
                    'error': str(e),
                })

        return jsonify({
            'total': len(all_vacancies),
            'queries': results,
        })

    except Exception as e:
        logger.error(f"Error in /vacancies: {e}", exc_info=True)
        return jsonify({'error': f'Failed to fetch vacancies: {str(e)}'}), 500
    finally:
        db_session.close()


@app.route('/vacancy/<int:vacancy_id>', methods=['GET'])
def get_vacancy_by_id(vacancy_id):
    """Получение вакансии по ID."""
    try:
        api_session = get_api_session()
        resp = api_session.get(f'{BASE_URL}/vacancies/{vacancy_id}', timeout=15)
        resp.raise_for_status()
        vacancy = resp.json()
        logger.info(f"Vacancy fetched successfully: {vacancy_id}")
        return jsonify(vacancy)
    except Exception as e:
        logger.error(f"Error fetching vacancy {vacancy_id}: {e}", exc_info=True)
        return jsonify({'error': f'Failed to fetch vacancy: {str(e)}'}), 500


@app.route('/employers/<int:employer_id>', methods=['GET'])
def get_employer_by_id(employer_id):
    """Получение компании по ID."""
    try:
        api_session = get_api_session()
        resp = api_session.get(f'{BASE_URL}/employers/{employer_id}', timeout=15)
        resp.raise_for_status()
        employer = resp.json()
        logger.info(f"Employer fetched successfully: {employer_id}")
        return jsonify(employer)
    except Exception as e:
        logger.error(f"Error fetching employer {employer_id}: {e}", exc_info=True)
        return jsonify({'error': f'Failed to fetch employer: {str(e)}'}), 500


# ─────────────────────────────────────────────
# Заявки на поисковые запросы
# ─────────────────────────────────────────────
@app.route('/search_queries', methods=['POST'])
def create_search_query():
    """Создание новой заявки на получение аналитической информации."""
    data = request.json
    db_session = Session()
    try:
        new_query = SearchQuery(
            query=data['query'],
            is_active=False,
            created_at=datetime.now(pytz.timezone('Europe/Moscow')),
            updated_at=datetime.now(pytz.timezone('Europe/Moscow')),
            initiator=data['initiator'],
            email=data['email']
        )
        db_session.add(new_query)
        db_session.commit()
        logger.info(f"New search query created: {new_query.query}")

        subject = "Новая заявка на поисковый запрос"
        body = f"""
        <p>Пользователь {new_query.initiator} создал новую заявку:</p>
        <p><strong>Запрос:</strong> {new_query.query}</p>
        <p><strong>Email инициатора:</strong> {new_query.email}</p>
        """
        try:
            send_email(subject, body, os.getenv('ADMIN_EMAIL'))
            logger.info("Notification email sent to admin.")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

        return jsonify({'message': 'Search query created successfully'}), 201
    finally:
        db_session.close()


@app.route('/search_queries', methods=['GET'])
@login_required
def get_search_queries():
    """Получение всех заявок на получение аналитической информации."""
    db_session = Session()
    try:
        queries = db_session.query(SearchQuery).all()
        return jsonify([
            {'id': q.id, 'query': q.query, 'is_active': q.is_active}
            for q in queries
        ]), 200
    finally:
        db_session.close()


@app.route('/search_queries/<int:query_id>/approve', methods=['POST'])
@login_required
def approve_search_query(query_id):
    """Одобрение заявки на получение аналитической информации."""
    db_session = Session()
    try:
        query = db_session.query(SearchQuery).filter_by(id=query_id).first()
        if query:
            query.is_active = True
            db_session.commit()
            logger.info(f"Search query approved: {query.query}")
            return jsonify({'message': 'Search query approved successfully'}), 200
        return jsonify({'error': 'Search query not found'}), 404
    finally:
        db_session.close()


@app.route('/request_query', methods=['GET', 'POST'])
def request_query():
    """Форма для отправки заявки на поисковый запрос."""
    if request.method == 'POST':
        query_text = request.form['query']
        initiator = request.form['initiator']
        email = request.form['email']

        db_session = Session()
        try:
            new_query = SearchQuery(
                query=query_text,
                is_active=False,
                created_at=datetime.now(pytz.timezone('Europe/Moscow')),
                updated_at=datetime.now(pytz.timezone('Europe/Moscow')),
                initiator=initiator,
                email=email
            )
            db_session.add(new_query)
            db_session.commit()
            logger.info(f"New search query created: {new_query.query}")
            return redirect(url_for('index'))
        finally:
            db_session.close()

    return render_template('request_query.html')


@app.route('/dashboards')
def dashboards():
    return render_template('dashboards.html')


# ─────────────────────────────────────────────
# Тестовый endpoint для проверки работы API
# ─────────────────────────────────────────────

@app.route('/test_vacancies')
def test_vacancies():
    """
    Улучшенный тест: делает запрос к API HH с правильными заголовками
    и выводит детальную диагностику.
    """
    try:
        api_session = get_api_session()

        # Логируем заголовки, которые отправляем
        logger.info(f"Request headers: {dict(api_session.headers)}")

        params = {
            'text': 'Python разработчик',
            'per_page': 5,
            'page': 0,
        }

        resp = api_session.get(
            f'{BASE_URL}/vacancies',
            params=params,
            timeout=15
        )

        # Детальная информация об ответе
        logger.info(f"Response status: {resp.status_code}")
        logger.info(f"Response headers: {dict(resp.headers)}")

        if resp.status_code == 403:
            # Специальная диагностика для 403
            error_text = resp.text[:500]
            logger.error(f"403 Forbidden! Response body: {error_text}")

            return jsonify({
                '❌ error': '403 Forbidden',
                '🔍 diagnosis': 'API HH отклонил запрос',
                '💡 possible_reasons': [
                    'Неправильный User-Agent (должен содержать email)',
                    'Токен невалиден или отозван',
                    'IP адрес заблокирован',
                ],
                '📋 request_headers': {
                    'User-Agent': api_session.headers.get('User-Agent'),
                    'Authorization': f"Bearer {api_session.headers.get('Authorization', '')[:20]}...",
                },
                '📝 response_body': error_text,
                '🔧 solution': 'Проверьте User-Agent и убедитесь, что email указан в .env'
            }), 403

        resp.raise_for_status()
        data = resp.json()

        # Успешный ответ
        result = {
            '✅ status': 'OK',
            '🔍 query': 'Python разработчик',
            '📊 total_found': data.get('found', 0),
            '📄 total_pages': data.get('pages', 0),
            '📥 received_on_page': len(data.get('items', [])),
            '🎯 vacancies': []
        }

        for v in data.get('items', [])[:5]:
            salary = v.get('salary') or {}
            result['🎯 vacancies'].append({
                'id': v.get('id'),
                'title': v.get('name'),
                'employer': v.get('employer', {}).get('name'),
                'city': v.get('area', {}).get('name'),
                'salary_from': salary.get('from'),
                'salary_to': salary.get('to'),
                'currency': salary.get('currency'),
            })

        return jsonify(result)

    except Exception as e:
        logger.error(f"Test vacancies error: {e}", exc_info=True)
        return jsonify({
            '❌ error': str(e),
            '🐛 error_type': type(e).__name__,
        }), 500


@app.route('/debug_headers')
def debug_headers():
    """Показывает, какие заголовки будут отправлены в API HH."""
    try:
        session = get_api_session()
        return jsonify({
            '✅ session_created': True,
            '📋 headers': {
                'User-Agent': session.headers.get('User-Agent'),
                'Authorization': f"{session.headers.get('Authorization', '')[:30]}...",
                'Content-Type': session.headers.get('Content-Type'),
                'Accept': session.headers.get('Accept'),
            },
            '🔑 token_status': auth_manager.get_token_info(),
        })
    except Exception as e:
        return jsonify({'❌ error': str(e)}), 500        

# ─────────────────────────────────────────────
# Диагностика токенов
# ─────────────────────────────────────────────
@app.route('/debug_tokens')
def debug_tokens():
    """Показывает содержимое файла hh_tokens.json (с маскировкой)."""
    import json
    if not os.path.exists('hh_tokens.json'):
        return jsonify({'❌ status': 'Файл hh_tokens.json не существует'})
    
    try:
        with open('hh_tokens.json', 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        
        # Маскируем чувствительные данные
        masked = {}
        for key, value in tokens.items():
            if isinstance(value, str) and len(value) > 10:
                # Показываем только первые 6 и последние 4 символа
                masked[key] = f"{value[:6]}...{value[-4:]} (длина: {len(value)})"
            else:
                masked[key] = value
        
        # Добавляем диагностику
        access_token = tokens.get('access_token', '')
        diagnosis = []
        
        if access_token.startswith('Bearer '):
            diagnosis.append("⚠️ access_token содержит префикс 'Bearer ' — это НЕПРАВИЛЬНО!")
        elif access_token.startswith('USER'):
            diagnosis.append("⚠️ access_token начинается с 'USER' — это НЕ access_token, а что-то другое!")
        elif len(access_token) < 20:
            diagnosis.append(f"⚠️ access_token слишком короткий ({len(access_token)} символов)")
        else:
            diagnosis.append(f"✅ access_token выглядит корректно (длина: {len(access_token)})")
        
        return jsonify({
            '📋 tokens_masked': masked,
            '🔍 diagnosis': diagnosis,
            '💡 solution': 'Удалите файл через /reset_tokens и пройдите авторизацию заново'
        })
    except Exception as e:
        return jsonify({'❌ error': str(e)}), 500


@app.route('/reset_tokens')
@login_required
def reset_tokens():
    """Удаляет файл hh_tokens.json для повторной авторизации."""
    if os.path.exists('hh_tokens.json'):
        os.remove('hh_tokens.json')
        return jsonify({
            '✅ message': 'Файл hh_tokens.json удален. Перейдите на /login_hh для новой авторизации.',
            '🔗 next_step': '/login_hh'
        })
    return jsonify({'ℹ️ message': 'Файл hh_tokens.json не существует'})


@app.route('/manual_reset')
def manual_reset():
    """Упрощенный сброс токенов (без авторизации) — для экстренных случаев."""
    if os.path.exists('hh_tokens.json'):
        os.remove('hh_tokens.json')
        return """
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Токены сброшены</title></head>
        <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
            <h2 style="color: green;">✅ Файл hh_tokens.json удален</h2>
            <p>Теперь пройдите авторизацию заново:</p>
            <a href="/login_hh" style="display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 4px;">Пройти авторизацию →</a>
        </body>
        </html>
        """
    return "Файл не существует"

# ─────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────
if __name__ == '__main__':
    if not check_db_exists():
        init_db()
    app.run(debug=True)
