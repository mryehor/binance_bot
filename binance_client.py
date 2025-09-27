import time
import pandas as pd
from binance.client import Client
from binance import ThreadedWebsocketManager
from config import API_KEY, API_SECRET, TIMEFRAME
from utils import clean_klines
from data_store import klines_cache
from typing import List

_client = Client(API_KEY, API_SECRET, testnet=False, requests_params={"timeout": 30})
_twm = None

def safe_request(func, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Ошибка запроса: {e}, попытка {i+1}/{retries}")
            time.sleep(delay)
    raise

def fetch_historical_klines(symbol: str, interval: str = TIMEFRAME, limit: int = 500) -> pd.DataFrame:
    try:
        data = safe_request(_client.futures_klines, symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(data, columns=[
            "Open time", "Open", "High", "Low", "Close", "Volume", "Close time",
            "Quote asset volume", "Number of trades", "Taker buy base",
            "Taker buy quote", "Ignore"
        ])
        df = clean_klines(df)
        df.index = pd.to_datetime(df["Open time"], unit="ms", errors="coerce")
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as e:
        print(f"Ошибка загрузки исторических свечей для {symbol}: {e}")
        return pd.DataFrame()

# ========== websocket handler ==========
def _handle_kline(msg):
    try:
        symbol = msg["s"]
        k = msg["k"]
        row = {
            "Open": float(k["o"]),
            "High": float(k["h"]),
            "Low": float(k["l"]),
            "Close": float(k["c"]),
            "Volume": float(k["v"]),
        }
        idx = pd.to_datetime(k["t"], unit="ms")
        df = klines_cache.get(symbol)
        if df is None or df.empty:
            df = pd.DataFrame([row], index=[idx])
        else:
            if idx in df.index:
                df.loc[idx] = row
            else:
                df = pd.concat([df, pd.DataFrame([row], index=[idx])])
                df = df.tail(500)
        klines_cache[symbol] = df
    except Exception as e:
        print("Ошибка в обработчике kline:", e)

def start_websockets(symbols: List[str], interval: str = TIMEFRAME):
    global _twm
    if _twm:
        return _twm
    _twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
    _twm.start()
    for s in symbols:
        try:
            _twm.start_kline_socket(callback=_handle_kline, symbol=s, interval=interval)
        except Exception as e:
            print("Ошибка старта ws для", s, e)
    return _twm

def stop_websockets():
    global _twm
    if _twm:
        try:
            _twm.stop()
        except Exception:
            pass
        _twm = None

# ========== liquid tickers ==========
_liquid_tickers_cache = {"timestamp": 0, "tickers": []}

def get_liquid_tickers(top_n=10, min_price=0.1, min_volume=1_000_000, max_spread_percent=5.0) -> List[str]:
    global _liquid_tickers_cache
    now = time.time()
    if now - _liquid_tickers_cache["timestamp"] < 3600:
        return _liquid_tickers_cache["tickers"]
    filtered = []
    try:
        tickers = safe_request(_client.futures_ticker)
        for t in tickers:
            symbol = t.get("symbol")
            if not symbol or "USDT" not in symbol:
                continue
            try:
                price = float(t.get("lastPrice", 0))
                volume = float(t.get("quoteVolume", 0))
                high = float(t.get("highPrice", 0))
                low = float(t.get("lowPrice", 0))
                if price <= 0:
                    continue
                spread_percent = ((high - low) / price) * 100 if price else 100
                if price >= min_price and volume >= min_volume and spread_percent <= max_spread_percent:
                    filtered.append({"symbol": symbol, "volume": volume})
            except Exception:
                continue
        filtered.sort(key=lambda x: x["volume"], reverse=True)
        top_symbols = [x["symbol"] for x in filtered[:top_n]]
        _liquid_tickers_cache = {"timestamp": now, "tickers": top_symbols}
        return top_symbols
    except Exception as e:
        print("Ошибка при фильтрации ликвидных монет:", e)
        return []
