# get_refresh_token_local.py
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CLIENT_SECRETS_FILE = 'credentials.json'


def get_refresh_token_local():
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES
        )

        print("Запуск аутентификации через браузер...")
        print("Откроется браузер для авторизации...")

        # Используем port=0 для автоматического выбора свободного порта
        creds = flow.run_local_server(
            port=0,  # Автоматический выбор свободного порта
            open_browser=True,
            success_message="Аутентификация успешна! Вы можете закрыть это окно."
        )

        # Сохраняем токены
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }

        with open('token.json', 'w') as token_file:
            json.dump(token_data, token_file)

        print("✅ Успех! Token сохранен в token.json")
        print(f"📧 Refresh token: {creds.refresh_token}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == '__main__':
    get_refresh_token_local()