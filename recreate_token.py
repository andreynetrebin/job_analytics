# recreate_token_send_only.py
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Только scope для отправки писем
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def recreate_token_send_only():
    try:
        # Удаляем старый токен если существует
        if os.path.exists('token.json'):
            os.remove('token.json')
            print("🗑️ Старый token.json удален")

        print("🔄 Запуск аутентификации с правами только для отправки...")
        print("📋 Запрашиваемые права:")
        print("   - Отправка писем (gmail.send)")

        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES
        )

        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            success_message="✅ Аутентификация успешна! Вы можете закрыть это окно."
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

        print("✅ Успех! Новый token сохранен в token.json")
        print(f"📧 Refresh token: {creds.refresh_token}")
        print(f"🔑 Scopes: {creds.scopes}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    recreate_token_send_only()