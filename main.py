import asyncio
import time
import traceback
from binance_client import get_liquid_tickers, fetch_historical_klines, start_websockets
from data_store import klines_cache
from config import TIMEFRAME, CHECK_INTERVAL, TOP_N_TICKERS, MIN_PRICE, MIN_VOLUME, MAX_SPREAD_PERCENT, DRY_RUN, USE_BBRSI, USE_BREAKOUT
from strategies import BBRSI_EMA_Strategy, Breakout_Strategy
from position_manager import get_open_position, open_position, simulate_realtime_pnl, get_open_positions, close_position
from backtesting.lib import FractionalBacktest
from logger import log_position
from config import BBRSI_PARAM_GRID, BREAKOUT_PARAM_GRID, INITIAL_CASH

# маленькая защита: если нужно — установи вручную SYMBOLS в конфигах,
# но обычно получаем их динамически
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
            continue
        if USE_BBRSI:
            params = optimize_params_ws(symbol, BBRSI_EMA_Strategy, BBRSI_PARAM_GRID)
            if params:
                BBRSI_EMA_Strategy.bol_period = params["bol_period"]
                BBRSI_EMA_Strategy.bol_dev = params["bol_dev"]
                BBRSI_EMA_Strategy.rsi_period = params["rsi_period"]
            try:
                bt = FractionalBacktest(df, BBRSI_EMA_Strategy, cash=INITIAL_CASH, margin=1, commission=0.005, finalize_trades=True)
                stats = bt.run()
                total_equity += stats.get("Equity Final [$]", 0.0)
            except Exception:
                pass
        if USE_BREAKOUT:
            params_b = optimize_params_ws(symbol, Breakout_Strategy, BREAKOUT_PARAM_GRID)
            if params_b:
                Breakout_Strategy.period = params_b["period"]
            try:
                bt2 = FractionalBacktest(df, Breakout_Strategy, cash=INITIAL_CASH, margin=1, commission=0.005, finalize_trades=True)
                stats2 = bt2.run()
                total_equity += stats2.get("Equity Final [$]", 0.0)
            except Exception:
                pass
        results.append((symbol, total_equity))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:5]

async def trade_symbol_loop(symbol):
    while True:
        try:
            pos = get_open_position(symbol)
            df = klines_cache.get(symbol)
            if df is None or df.empty:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # DRY_RUN: проверка TP/SL/Trailing
            if DRY_RUN and pos:
                last_price = float(df["Close"].iloc[-1])
                pnl = simulate_realtime_pnl(symbol)
                entry = pos["entry"]
                side = pos["side"]
                qty = pos["qty"]
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
                    elif last_price <= pos["sl"]:
                        reason = "SL"
                elif side == "SELL":
                    if last_price <= tp:
                        reason = "TP"
                    elif last_price >= pos["sl"]:
                        reason = "SL"

                if reason in ("TP", "SL"):
                    # закрываем позицию
                    close_position(symbol, last_price, reason=f"DRY_RUN {reason}", exit_reason=reason)
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

            # Если позиция открыта — ждём
            if pos:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Сигналы (BBRSI)
            price_last = float(df["Close"].iloc[-1])
            try:
                upper = None
                lower = None
                from utils import bol_h, bol_l, rsi
                lower = bol_l(df["Close"])[-1]
                upper = bol_h(df["Close"])[-1]
                rsi_val = rsi(df["Close"])[-1]
            except Exception:
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            if df["Close"].iloc[-2] > lower and df["Close"].iloc[-1] < lower and rsi_val < 30:
                open_position(symbol, "BUY")
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            elif df["Close"].iloc[-2] < upper and df["Close"].iloc[-1] > upper and rsi_val > 70:
                open_position(symbol, "SELL")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Breakout сигнал
            period = Breakout_Strategy.period
            if len(df) > period + 2:
                highest = df["High"].iloc[-period-1:-1].max()
                lowest = df["Low"].iloc[-period-1:-1].min()
                if price_last > highest:
                    open_position(symbol, "BUY")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue
                elif price_last < lowest:
                    open_position(symbol, "SELL")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

        except Exception as e:
            print(f"Ошибка цикла торговли {symbol}: {e}")
            traceback.print_exc()
        await asyncio.sleep(CHECK_INTERVAL)

async def main_async():
    # 1) Получаем список тикеров
    symbols = get_liquid_tickers(top_n=TOP_N_TICKERS, min_price=MIN_PRICE, min_volume=MIN_VOLUME, max_spread_percent=MAX_SPREAD_PERCENT)
    # возможен fallback: если пусто, берем пару BTCUSDT
    if not symbols:
        print("Не получили ликвидные тикеры, ставим BTCUSDT в список")
        symbols = ["BTCUSDT"]
    print("Selected symbols:", symbols)

    # 2) Download historical data (быстрый старт)
    print("Загружаем исторические свечи...")
    for s in symbols:
        df = fetch_historical_klines(s, interval=TIMEFRAME, limit=500)
        if not df.empty:
            klines_cache[s] = df
            print(f"✅ {s} loaded {len(df)} candles")
        else:
            print(f"❌ {s} failed to load history")

    # 3) start websocket
    start_websockets(symbols, interval=TIMEFRAME)
    print("Websockets started")

    # 4) optimization & selection
    print("Оптимизация и выбор топ-5...")
    top5 = optimize_and_select_top_ws(symbols)
    if not top5:
        print("Оптимизация вернула пустой список — используем исходные символы")
        top_symbols = symbols[:5]
    else:
        top_symbols = [s for s, _ in top5]
    print("Top symbols:", top_symbols)

    # 5) start tasks
    tasks = [trade_symbol_loop(sym) for sym in top_symbols]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    RESTART_DELAY = 10
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
