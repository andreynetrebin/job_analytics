# check_token_simple.py
import json
from google.oauth2.credentials import Credentials

def check_token_simple():
    """Проверяет токен без вызова Gmail API"""
    try:
        with open('token.json', 'r') as f:
            token_data = json.load(f)
        
        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes', ['https://www.googleapis.com/auth/gmail.send'])
        )
        
        print("🔍 Проверка токена:")
        print(f"✅ Token valid: {creds.valid}")
        print(f"✅ Token expired: {creds.expired}")
        print(f"✅ Has refresh token: {bool(creds.refresh_token)}")
        print(f"✅ Correct scope: {'https://www.googleapis.com/auth/gmail.send' in creds.scopes}")
        print(f"✅ Scopes: {creds.scopes}")
        
        return True
        
    except Exception as e:
        print(f"❌ Token check failed: {e}")
        return False

if __name__ == '__main__':
    check_token_simple()
