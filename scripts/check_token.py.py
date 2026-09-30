# check_token.py
import json
import os

def check_token():
    if not os.path.exists('token.json'):
        print("❌ token.json не найден")
        return
    
    with open('token.json', 'r') as f:
        token_data = json.load(f)
    
    print("📋 Содержимое token.json:")
    print(f"✅ Есть token: {'Да' if token_data.get('token') else 'Нет'}")
    print(f"✅ Есть refresh_token: {'Да' if token_data.get('refresh_token') else 'Нет'}")
    print(f"✅ Scopes: {token_data.get('scopes', [])}")
    print(f"✅ Client ID: {'Есть' if token_data.get('client_id') else 'Нет'}")
    print(f"✅ Client Secret: {'Есть' if token_data.get('client_secret') else 'Нет'}")

if __name__ == '__main__':
    check_token()