import asyncio
import time
import traceback
from binance_client import get_liquid_tickers, fetch_historical_klines, start_websockets
from data_store import klines_cache
from config import (
    TIMEFRAME, CHECK_INTERVAL, TOP_N_TICKERS, MIN_PRICE, MIN_VOLUME,
    MAX_SPREAD_PERCENT, DRY_RUN, USE_BBRSI, USE_BREAKOUT,
    BBRSI_PARAM_GRID, BREAKOUT_PARAM_GRID, INITIAL_CASH
)
from strategies import BBRSI_EMA_Strategy, Breakout_Strategy
from pos_manager import (
    get_open_position, open_position, close_position
)
from telegram_bot import send_telegram_message
from backtesting.lib import FractionalBacktest
from utils import bol_h, bol_l, rsi
from pnl_utils import simulate_realtime_pnl



# ========== OPTIMIZATION ==========
def optimize_params_ws(symbol, strategy_class, param_grid):
    df = klines_cache.get(symbol)
    if df is None or len(df) < 150:
        return None

    best_eq = -float("inf")
    best_params = {}

    for params in param_grid:
        class TempStrategy(strategy_class):
            pass
        for k, v in params.items():
            setattr(TempStrategy, k, v)
        try:
            bt = FractionalBacktest(df, TempStrategy, cash=INITIAL_CASH, margin=1, commission=0.005, finalize_trades=True)
            stats = bt.run()
            eq_final = stats.get("Equity Final [$]", None)
            if eq_final is not None and eq_final > best_eq:
                best_eq = eq_final
                best_params = params
        except Exception:
            continue
    return best_params

def optimize_and_select_top_ws(symbols):
    results = []
    for symbol in symbols:
        total_equity = 0.0
        df = klines_cache.get(symbol)
        if df is None or df.empty:
            print(f"[WARN] Нет данных по {symbol}")
            continue

        # BBRSI
        if USE_BBRSI:
            try:
                params = optimize_params_ws(symbol, BBRSI_EMA_Strategy, BBRSI_PARAM_GRID)
                if params:
                    BBRSI_EMA_Strategy.bol_period = params["bol_period"]
                    BBRSI_EMA_Strategy.bol_dev = params["bol_dev"]
                    BBRSI_EMA_Strategy.rsi_period = params["rsi_period"]
                bt = FractionalBacktest(df, BBRSI_EMA_Strategy, cash=INITIAL_CASH, margin=1, commission=0.005, finalize_trades=True)
                stats = bt.run()
                equity = stats.get("Equity Final [$]", 0.0)
                total_equity += equity
                print(f"[INFO] {symbol} BBRSI equity: {equity}")
            except Exception as e:
                print(f"[ERROR] BBRSI бэктест {symbol} упал:", e)

        # BREAKOUT
        if USE_BREAKOUT:
            try:
                params_b = optimize_params_ws(symbol, Breakout_Strategy, BREAKOUT_PARAM_GRID)
                if params_b:
                    Breakout_Strategy.period = params_b["period"]
                bt2 = FractionalBacktest(df, Breakout_Strategy, cash=INITIAL_CASH, margin=1, commission=0.005, finalize_trades=True)
                stats2 = bt2.run()
                equity2 = stats2.get("Equity Final [$]", 0.0)
                total_equity += equity2
                print(f"[INFO] {symbol} BREAKOUT equity: {equity2}")
            except Exception as e:
                print(f"[ERROR] BREAKOUT бэктест {symbol} упал:", e)

        results.append((symbol, total_equity))

    # сортируем по equity и выбираем топ-5
    if not results:
        print("[WARN] Нет результатов оптимизации, берём первые 5 символов")
        return symbols[:5]

    results.sort(key=lambda x: x[1], reverse=True)
    top5 = results[:5]
    print("[INFO] Top5 монет:", top5)
    return top5


    results.sort(key=lambda x: x[1], reverse=True)
    return results[:5]

# ========== DRY_RUN HELPERS ==========
def check_and_close_position(symbol):
    pos = get_open_position(symbol)
    if not pos:
        return False

    df = klines_cache.get(symbol)
    if df is None or df.empty:
        return False

    last_price = float(df["Close"].iloc[-1])
    side = pos["side"]
    tp = pos["tp"]
    sl = pos["sl"]
    trail_percent = pos.get("trail_percent", None)
    reason = None

    # трейлинг
    if trail_percent:
        if side == "BUY":
            new_sl = last_price * (1 - trail_percent / 100)
            if new_sl > sl:
                pos["sl"] = new_sl
                reason = "Trailing"
        elif side == "SELL":
            new_sl = last_price * (1 + trail_percent / 100)
            if new_sl < sl:
                pos["sl"] = new_sl
                reason = "Trailing"

    # проверка TP/SL
    if side == "BUY":
        if last_price >= tp:
            reason = "TP"
        elif last_price <= sl:
            reason = "SL"
    elif side == "SELL":
        if last_price <= tp:
            reason = "TP"
        elif last_price >= sl:
            reason = "SL"

    if reason in ("TP", "SL"):
        close_position(symbol, last_price, reason=f"DRY_RUN {reason}", exit_reason=reason)
        send_telegram_message(f"✅ Позиция закрыта для {symbol}, причина: {reason}")
        return True
    return False

def check_entry_signal(symbol):
    df = klines_cache.get(symbol)
    if df is None or len(df) < 20:
        return None

    price_last = float(df["Close"].iloc[-1])

    # BBRSI
    lower = bol_l(df["Close"])[-1]
    upper = bol_h(df["Close"])[-1]
    rsi_val = rsi(df["Close"])[-1]

    if df["Close"].iloc[-2] > lower and df["Close"].iloc[-1] < lower and rsi_val < 30:
        return "BUY"
    elif df["Close"].iloc[-2] < upper and df["Close"].iloc[-1] > upper and rsi_val > 70:
        return "SELL"

    # Breakout
    period = Breakout_Strategy.period
    if len(df) > period + 2:
        highest = df["High"].iloc[-period-1:-1].max()
        lowest = df["Low"].iloc[-period-1:-1].min()
        if price_last > highest:
            return "BUY"
        elif price_last < lowest:
            return "SELL"
    return None

# ========== TRADE LOOP ==========
async def trade_symbol_loop(symbol):
    while True:
        try:
            df = klines_cache.get(symbol)
            if df is None or len(df) < 20:
                print(f"{symbol}: данные отсутствуют или мало свечей")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Проверяем, есть ли уже открытая позиция
            pos = get_open_position(symbol)
            if pos:
                # Можно добавить трейлинг или проверку TP/SL
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Проверяем сигналы
            price_last = df["Close"].iloc[-1]
            signal = None

            # ===== BBRSI сигнал =====
            lower = bol_l(df["Close"])[-1]
            upper = bol_h(df["Close"])[-1]
            rsi_val = rsi(df["Close"])[-1]

            if df["Close"].iloc[-2] > lower and df["Close"].iloc[-1] < lower and rsi_val < 30:
                signal = "BUY (BBRSI)"
            elif df["Close"].iloc[-2] < upper and df["Close"].iloc[-1] > upper and rsi_val > 70:
                signal = "SELL (BBRSI)"

            # ===== Breakout сигнал =====
            period = Breakout_Strategy.period
            if len(df) > period + 2:
                highest = df["High"].iloc[-period-1:-1].max()
                lowest = df["Low"].iloc[-period-1:-1].min()
                if price_last > highest:
                    signal = "BUY (Breakout)"
                elif price_last < lowest:
                    signal = "SELL (Breakout)"

            if signal:
                msg = f"⚡ Сигнал для {symbol}: {signal} | Цена: {price_last}"
                print(msg)
                send_telegram_message(msg)

                # Открываем позицию
                if not DRY_RUN:
                    side = "BUY" if "BUY" in signal else "SELL"
                    try:
                        open_position(symbol, side)  # рыночный ордер
                        send_telegram_message(f"✅ Позиция открыта: {side} для {symbol} @ {price_last}")
                        print(f"{symbol}: Позиция открыта ({side})")
                    except Exception as e:
                        print(f"❌ Ошибка открытия позиции для {symbol}: {e}")
                else:
                    print(f"{symbol}: DRY_RUN=True, позиция не открыта")

        except Exception as e:
            print(f"❌ Ошибка в торговом цикле {symbol}: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
# ========== MAIN ASYNC ==========
async def main_async():
    symbols = await get_liquid_tickers(
        top_n=TOP_N_TICKERS,
        min_price=MIN_PRICE,
        min_volume=MIN_VOLUME,
        max_spread_percent=MAX_SPREAD_PERCENT
    )
    if not symbols:
        print("Не получили ликвидные тикеры, ставим BTCUSDT в список")
        symbols = ["BTCUSDT"]
    print("Selected symbols:", symbols)

    # загрузка исторических свечей
    print("Загружаем исторические свечи...")
    for s in symbols:
        df = await fetch_historical_klines(s, interval=TIMEFRAME, limit=500)
        if not df.empty:
            klines_cache[s] = df
            print(f"✅ {s} loaded {len(df)} candles")
        else:
            print(f"❌ {s} failed to load history")

    # start websocket
    await start_websockets(symbols, interval=TIMEFRAME)
    print("Websockets started")

    # optimization & selection
    print("Оптимизация и выбор топ-5...")
    top5 = optimize_and_select_top_ws(symbols)
    top_symbols = [s for s, _ in top5] if top5 else symbols[:5]
    print("Top symbols:", top_symbols)

    # запуск торговых тасков
    tasks = [trade_symbol_loop(sym) for sym in top_symbols]
    await asyncio.gather(*tasks)

# ========== ENTRY POINT ==========
if __name__ == "__main__":
    RESTART_DELAY = 10  # секунд
    while True:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            print("Остановлено вручную")
            break
        except Exception as e:
            print("Критическая ошибка! Перезапуск через", RESTART_DELAY, "секунд")
            traceback.print_exc()
            time.sleep(RESTART_DELAY)

