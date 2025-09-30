from data_store import klines_cache, user_data_cache
from config import LEVERAGE, INITIAL_CASH, RISK_FRACTION, DRY_RUN
from utils import _quantize_to_step
from logger import log_position

def get_open_positions():
    return user_data_cache.get("positions", {})

def get_open_position(symbol: str):
    return user_data_cache.get("positions", {}).get(symbol)

def calculate_qty(price: float, equity: float = None, risk_fraction: float = RISK_FRACTION) -> float:
    if equity is None:
        equity = INITIAL_CASH
    qty = max(1e-8, (equity * risk_fraction * LEVERAGE) / price)
    return qty

# Открыть сделку (только в DRY RUN)
def open_position(symbol: str, side: str, equity: float = None, risk_fraction: float = RISK_FRACTION):
    df = klines_cache.get(symbol)
    if df is None or df.empty:
        print(f"[open_position] нет свечей для {symbol}")
        return None

    price = float(df["Close"].iloc[-1])
    if equity is None:
        equity = INITIAL_CASH

    # считаем размер позиции
    qty = calculate_qty(price, equity, risk_fraction)
    qty = _quantize_to_step(qty, step=0.001)

    # тейк-профит и стоп-лосс
    tp = price * (1.01 if side.upper() == "BUY" else 0.99)
    sl = price * (0.98 if side.upper() == "BUY" else 1.02)

    # трейлинг стоп (0.5%)
    trail_percent = 0.5

    pos_dict = {
        "side": side.upper(),
        "qty": qty,
        "entry": price,
        "tp": tp,
        "sl": sl,
        "trail_percent": trail_percent,
        "status": "OPEN"
    }

    # сохраняем сделку в кеш
    user_data_cache.setdefault("positions", {})[symbol] = pos_dict
    print(f"[DRY RUN] OPEN {symbol} {side} @ {price} TP={tp:.2f} SL={sl:.2f} Trail={trail_percent}%")

    return pos_dict


# Проверка сделки (DRY RUN)
def check_position(symbol: str, price: float):
    pos = user_data_cache.get("positions", {}).get(symbol)
    if not pos or pos["status"] != "OPEN":
        return

    side = pos["side"]
    sl = pos["sl"]
    tp = pos["tp"]
    trail = pos["trail_percent"]

    reason = None

    # --- трейлинг стоп ---
    if side == "BUY":
        new_sl = price * (1 - trail / 100)
        if new_sl > sl:  # подтягиваем стоп
            pos["sl"] = new_sl
            print(f"[TRAIL] {symbol} stop moved to {new_sl:.2f}")
    else:  # SELL
        new_sl = price * (1 + trail / 100)
        if new_sl < sl:
            pos["sl"] = new_sl
            print(f"[TRAIL] {symbol} stop moved to {new_sl:.2f}")

    # --- TP / SL ---
    if side == "BUY":
        if tp is not None and price >= tp:
            reason = "TP"
        elif sl is not None and price <= sl:
            reason = "SL"
    else:  # SELL
        if tp is not None and price <= tp:
            reason = "TP"
        elif sl is not None and price >= sl:
            reason = "SL"

    if reason:
        pos["status"] = "CLOSED"
        print(f"[DRY RUN] CLOSE {symbol} {side} @ {price} by {reason}")


def close_position(symbol: str, exit_price: float, reason="DRY_RUN", exit_reason=None):
    pos = get_open_position(symbol)
    if not pos:
        return False

    qty = pos["qty"]
    side = pos["side"]
    entry = pos["entry"]

    # Расчёт PnL
    if side == "BUY":  # Лонг
        pnl = (exit_price - entry) * qty
    elif side in ("SELL", "SHORT"):  # Шорт
        pnl = (entry - exit_price) * qty
    else:
        pnl = 0

    # Обновляем exit_reason и зануляем TP/SL
    pos["exit_reason"] = exit_reason or reason
    pos["tp"] = None
    pos["sl"] = None

    # Логируем закрытие
    log_position(
        action="CLOSE",
        symbol=symbol,
        side=side,
        price=exit_price,
        qty=qty,
        pnl=pnl,
        reason=reason,
        exit_reason=pos["exit_reason"]
    )

    # Удаляем из кеша
    user_data_cache["positions"].pop(symbol, None)
    return True

