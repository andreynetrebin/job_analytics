# verify_token.py
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def verify_token():
    """Проверяет валидность токена"""
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
        
        print(f"🔍 Token valid: {creds.valid}")
        print(f"🔍 Token expired: {creds.expired}")
        print(f"🔍 Has refresh token: {bool(creds.refresh_token)}")
        
        if not creds.valid and creds.expired:
            print("🔄 Token expired, attempting refresh...")
            creds.refresh(Request())
            print("✅ Token refreshed successfully!")
            
            # Сохраняем обновленный токен
            with open('token.json', 'w') as f:
                json.dump({
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }, f)
            print("💾 Updated token saved")
        
        # Проверяем доступ к Gmail API
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        print(f"✅ Gmail API access verified for: {profile['emailAddress']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Token verification failed: {e}")
        return False

if __name__ == '__main__':
    verify_token()