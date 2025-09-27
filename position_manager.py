from data_store import klines_cache, user_data_cache
from utils import _quantize_to_step
from config import LEVERAGE, INITIAL_CASH, RISK_FRACTION, DRY_RUN
from logger import log_position

def get_open_positions():
    return user_data_cache.get("positions", {})

def get_open_position(symbol: str):
    return user_data_cache.get("positions", {}).get(symbol)

def calculate_qty(price: float, equity: float = None, risk_fraction: float = RISK_FRACTION) -> float:
    if equity is None:
        equity = INITIAL_CASH
    # базовый расчет количества контрактов (простая формула)
    qty = max(1e-8, (equity * risk_fraction * LEVERAGE) / price)
    return qty

def simulate_realtime_pnl(symbol: str):
    pos = get_open_position(symbol)
    if not pos:
        return None
    df = klines_cache.get(symbol)
    if df is None or df.empty:
        return None
    prices = df["Close"].to_numpy()
    entry = pos["entry"]
    qty = pos["qty"]
    side = pos["side"]
    tp = pos.get("tp", entry * (1.01 if side == "BUY" else 0.99))
    sl = pos.get("sl", entry * (0.98 if side == "BUY" else 1.02))
    trail_percent = pos.get("trail_percent", 0.5) / 100.0
    trail_activation = 0.002
    trailing_active = False

    if side == "BUY":
        max_price = entry
        for price in prices:
            max_price = max(max_price, price)
            if not trailing_active and price >= entry * (1 + trail_activation):
                trailing_active = True
            if price >= tp:
                return (tp - entry) * qty
            if price <= sl:
                return (sl - entry) * qty
            if trailing_active and price < max_price * (1 - trail_percent):
                pnl = (price - entry) * qty
                if pnl > 0:
                    return pnl
        return (prices[-1] - entry) * qty
    else:  # SELL
        min_price = entry
        for price in prices:
            min_price = min(min_price, price)
            if not trailing_active and price <= entry * (1 - trail_activation):
                trailing_active = True
            if price <= tp:
                return (entry - tp) * qty
            if price >= sl:
                return (entry - sl) * qty
            if trailing_active and price > min_price * (1 + trail_percent):
                pnl = (entry - price) * qty
                if pnl > 0:
                    return pnl
        return (entry - prices[-1]) * qty

def open_position(symbol: str, side: str, equity: float = None, risk_fraction: float = RISK_FRACTION):
    df = klines_cache.get(symbol)
    if df is None or df.empty:
        print(f"[open_position] нет свечей для {symbol}")
        return None
    price = float(df["Close"].iloc[-1])
    if equity is None:
        equity = INITIAL_CASH
    qty = calculate_qty(price, equity, risk_fraction)
    qty = _quantize_to_step(qty, step=0.001)
    tp_price = _quantize_to_step(price * (1.01 if side.upper() == "BUY" else 0.99), step=0.0001)
    sl_price = _quantize_to_step(price * (0.98 if side.upper() == "BUY" else 1.02), step=0.0001)
    trail_callback_rate = 0.5

    # Записываем в кеш (DRY_RUN)
    user_data_cache["positions"][symbol] = {
        "side": side.upper(),
        "qty": qty,
        "entry": price,
        "tp": tp_price,
        "sl": sl_price,
        "trail_percent": trail_callback_rate,
        "trailing": True,
        "trail_pending": True
    }
    log_position("OPEN", symbol, side, price, qty, reason="DRY_RUN")
    print(f"[DRY RUN] OPEN {symbol} {side} price={price:.4f} qty={qty:.4f} TP={tp_price} SL={sl_price}")
    return True

def close_position(symbol: str, exit_price: float, reason="DRY_RUN", exit_reason=None):
    pos = get_open_position(symbol)
    if not pos:
        return False
    qty = pos["qty"]
    side = pos["side"]
    # PnL для симуляции
    pnl = (exit_price - pos["entry"]) * qty if side == "BUY" else (pos["entry"] - exit_price) * qty
    log_position("CLOSE", symbol, side, exit_price, qty, pnl, reason=reason, exit_reason=exit_reason)
    user_data_cache["positions"].pop(symbol, None)
    return True
