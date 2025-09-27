import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN:
        # токен не указан — молча логируем в консоль
        print("[Telegram disabled] " + text)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        resp = requests.post(url, data=data, timeout=5)
        if resp.status_code != 200:
            print(f"Ошибка Telegram: {resp.status_code} {resp.text}")
        else:
            # ответ содержит JSON с информацией о сообщении
            print("✅ Telegram sent")
    except Exception as e:
        print(f"Ошибка отправки Telegram: {e}")
