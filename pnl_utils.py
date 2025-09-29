from data_store import klines_cache, user_data_cache

def simulate_realtime_pnl(symbol: str):
    pos = user_data_cache.get("positions", {}).get(symbol)
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
