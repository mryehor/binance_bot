import os

# Binance / API
API_KEY = os.getenv("API_KEY") or "YOUR_REAL_KEY"
API_SECRET = os.getenv("API_SECRET") or "YOUR_REAL_SECRET"
DRY_RUN = True  # True = не отправляем реальные ордера
LEVERAGE = 5
RISK_FRACTION = 0.2
INITIAL_CASH = 500.0

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

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID") or "-1002926519188")

# Logging / files
LOG_FILE = "trades_testnet.log"
POSITIONS_LOG_FILE = "positions_log.json"
