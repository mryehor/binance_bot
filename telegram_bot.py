import time
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram disabled] " + text)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        resp = requests.post(url, data=data, timeout=5)
        if resp.status_code != 200:
            print(f"Ошибка Telegram: {resp.status_code} {resp.text}")
        else:
            print("✅ Telegram sent:", text)
    except Exception as e:
        print(f"Ошибка отправки Telegram: {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data["ok"]:
            return data["result"]
    except Exception as e:
        print("Ошибка при получении обновлений:", e)
    return []

def listen_channel():
    last_update_id = None
    while True:
        updates = get_updates(last_update_id + 1 if last_update_id else None)
        for update in updates:
            last_update_id = update["update_id"]
            message = update.get("message")
            if not message:
                continue
            chat_id = message["chat"]["id"]
            text = message.get("text", "").lower()
            if str(chat_id) == str(TELEGRAM_CHAT_ID) and "старт" in text:
                send_telegram_message("🚀 Начинаю торговлю!")
        time.sleep(2)  # пауза между запросами

if __name__ == "__main__":
    send_telegram_message("Бот запущен и слушает канал!")
    listen_channel()
