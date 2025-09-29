import pandas as pd

# Кеш свечей для каждого символа
# Формат: {"SYMBOL": pd.DataFrame с колонками ["Open", "High", "Low", "Close", "Volume"]}
klines_cache = {}

# Пользовательские данные (позиции, баланс и т.д.)
# Структура:
# {
#   "positions": {
#       "BTCUSDT": {
#           "side": "BUY" / "SELL",
#           "qty": float,
#           "entry": float,
#           "tp": float,
#           "sl": float,
#           "trail_percent": float,
#           "trailing": bool,
#           "trail_pending": bool
#       },
#       ...
#   }
# }
user_data_cache = {
    "positions": {}
}

# Вспомогательная функция для инициализации свечей (пример)
def load_sample_klines(symbol: str, n=100):
    """Создает тестовые свечи для DRY_RUN"""
    import numpy as np
    close = 100 + np.cumsum(np.random.randn(n))
    high = close + np.random.rand(n) * 2
    low = close - np.random.rand(n) * 2
    open_ = close + np.random.randn(n)
    volume = np.random.randint(100, 1000, size=n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})
    klines_cache[symbol] = df
