import asyncio
import pandas as pd
import time
from typing import List
from binance import AsyncClient, BinanceSocketManager
from config import API_KEY, API_SECRET, TIMEFRAME, DRY_RUN
from data_store import klines_cache
from utils import bol_h, bol_l, rsi
from pos_manager import get_open_position, open_position, close_position
from telegram_bot import send_telegram_message
from logger import log_position
# ---------- fetch_historical_klines ----------
async def fetch_historical_klines(symbol: str, interval="5m", limit=500):
    if DRY_RUN:
        df = pd.DataFrame([{"Open": 0, "High": 0, "Low": 0, "Close": 0, "Volume": 0}] * limit)
        df.index = pd.date_range(end=pd.Timestamp.now(), periods=limit, freq=interval)
        return df

    client = await AsyncClient.create(API_KEY, API_SECRET)
    try:
        raw = await client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(raw, columns=[
            "Open time", "Open", "High", "Low", "Close", "Volume",
            "Close time", "Quote asset volume", "Number of trades",
            "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"
        ])
        df["Open time"] = pd.to_datetime(df["Open time"], unit="ms")
        df["Close time"] = pd.to_datetime(df["Close time"], unit="ms")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        df.set_index("Close time", inplace=True)
        return df
    except Exception as e:
        print(f"❌ Ошибка загрузки {symbol}: {e}")
        return pd.DataFrame()
    finally:
        await client.close_connection()

# ---------- WebSocket handler ----------
async def handle_kline(msg):
    try:
        k = msg["k"]
        symbol = msg["s"]
        row = {
            "Open": float(k["o"]),
            "High": float(k["h"]),
            "Low": float(k["l"]),
            "Close": float(k["c"]),
            "Volume": float(k["v"]),
        }
        idx = pd.to_datetime(k["t"], unit="ms")

        # Обновляем кэш свечей
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

        # Проверка открытой позиции
        pos = get_open_position(symbol)
        price_last = row["Close"]
        signal = None

        # --- сигналы по индикаторам ---
        if len(df) > 2:
            lower = bol_l(df["Close"])[-1]
            upper = bol_h(df["Close"])[-1]
            rsi_val = rsi(df["Close"])[-1]
            if df["Close"].iloc[-2] > lower and df["Close"].iloc[-1] < lower and rsi_val < 30:
                signal = "BUY"
            elif df["Close"].iloc[-2] < upper and df["Close"].iloc[-1] > upper and rsi_val > 70:
                signal = "SELL"

        # --- сигналы по пробою ---
        period = 20
        if len(df) > period + 2:
            highest = df["High"].iloc[-period-1:-1].max()
            lowest = df["Low"].iloc[-period-1:-1].min()
            if price_last > highest:
                signal = "BUY"
            elif price_last < lowest:
                signal = "SELL"

        # --- если есть открытая позиция ---
        if pos:
            side = pos["side"]
            entry = pos["entry"]

            # проверка TP / SL и обратного сигнала через logger
            if side == "BUY" and (signal == "SELL" or price_last <= pos["sl"] or price_last >= pos["tp"]):
                reason = "Обратный сигнал/TP/SL достигнут"
                close_position(symbol, price_last, reason=reason)
                log_position("CLOSE", symbol, side, price_last, pos["qty"], 
                             pnl=(price_last - entry) * pos["qty"], 
                             tp=pos["tp"], sl=pos["sl"], 
                             exit_reason=reason)
            elif side == "SELL" and (signal == "BUY" or price_last >= pos["sl"] or price_last <= pos["tp"]):
                reason = "Обратный сигнал/TP/SL достигнут"
                close_position(symbol, price_last, reason=reason)
                log_position("CLOSE", symbol, side, price_last, pos["qty"], 
                             pnl=(entry - price_last) * pos["qty"], 
                             tp=pos["tp"], sl=pos["sl"], 
                             exit_reason=reason)
            else:
                print(f"⏳ Ожидаем: {symbol} {side}, entry={entry}, last={price_last}")

        # --- если позиции нет и появился сигнал ---
        elif signal:
            pos_data = open_position(symbol, signal)
            if pos_data:
                log_position("OPEN", symbol, signal, pos_data["entry"], pos_data["qty"], 
                             tp=pos_data["tp"], sl=pos_data["sl"], reason=f"Сигнал {signal}")

    except Exception as e:
        print("Ошибка в обработчике kline:", e)

# ---------- start websockets ----------
async def start_websockets(symbols: List[str], interval: str = TIMEFRAME):
    if DRY_RUN:
        print("[DRY_RUN] WebSockets не запущены")
        return

    client = await AsyncClient.create(API_KEY, API_SECRET)
    bm = BinanceSocketManager(client)
    sockets = [bm.kline_socket(symbol=s, interval=interval) for s in symbols]

    async def listen(sock):
        async with sock as stream:
            while True:
                msg = await stream.recv()
                await handle_kline(msg)

    tasks = [asyncio.create_task(listen(sock)) for sock in sockets]
    print("✅ WebSockets запущены для:", symbols)
    await asyncio.gather(*tasks)

# ---------- get_liquid_tickers ----------
_liquid_tickers_cache = {"timestamp": 0, "tickers": []}

async def get_liquid_tickers(top_n=10, min_price=0.1, min_volume=1_000_000, max_spread_percent=5.0):
    global _liquid_tickers_cache
    if DRY_RUN:
        if not _liquid_tickers_cache["tickers"]:
            _liquid_tickers_cache["tickers"] = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        return _liquid_tickers_cache["tickers"]

    client = await AsyncClient.create(API_KEY, API_SECRET)
    now = time.time()
    if now - _liquid_tickers_cache["timestamp"] < 3600:
        await client.close_connection()
        return _liquid_tickers_cache["tickers"]

    try:
        tickers = await client.futures_ticker()
        filtered = []
        for t in tickers:
            symbol = t.get("symbol")
            if not symbol or "USDT" not in symbol:
                continue
            try:
                price = float(t.get("lastPrice", 0))
                volume = float(t.get("quoteVolume", 0))
                high = float(t.get("highPrice", 0))
                low = float(t.get("lowPrice", 0))
                spread_percent = ((high - low) / price) * 100 if price else 100
                if price >= min_price and volume >= min_volume and spread_percent <= max_spread_percent:
                    filtered.append({"symbol": symbol, "volume": volume})
            except Exception:
                continue

        filtered.sort(key=lambda x: x["volume"], reverse=True)
        top_symbols = [x["symbol"] for x in filtered[:top_n]]
        _liquid_tickers_cache = {"timestamp": now, "tickers": top_symbols}
        return top_symbols
    finally:
        await client.close_connection()
