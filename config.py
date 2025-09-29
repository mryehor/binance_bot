import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID") or "0")
DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

print("TELEGRAM_TOKEN =", TELEGRAM_TOKEN)
print("TELEGRAM_BOT_TOKEN =", TELEGRAM_BOT_TOKEN)
print("TELEGRAM_CHAT_ID =", TELEGRAM_CHAT_ID)

# Trading / timing
TIMEFRAME = "5m"
CHECK_INTERVAL = 60  # seconds
TOP_N_TICKERS = 10
MIN_PRICE = 0.1
MIN_VOLUME = 1_000_000
MAX_SPREAD_PERCENT = 5.0

# Strategies optimization grids
BBRSI_PARAM_GRID = [
    {"bol_period": p, "bol_dev": d, "rsi_period": r}
    for p in range(20, 41, 5)
    for d in range(1, 4)
    for r in range(12, 19, 2)
]
BREAKOUT_PARAM_GRID = [{"period": p} for p in range(10, 31, 5)]
USE_BBRSI = True
USE_BREAKOUT = True

# Trading / risk
INITIAL_CASH = 500.0
LEVERAGE = 5
RISK_FRACTION = 0.2

# Logging / files
LOG_FILE = "trades_testnet.log"
POSITIONS_LOG_FILE = "positions_log.json"
