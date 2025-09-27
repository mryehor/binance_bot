import json
import pandas as pd
from telegram_bot import send_telegram_message
from config import POSITIONS_LOG_FILE, INITIAL_CASH, DRY_RUN
from data_store import user_data_cache
from position_manager import simulate_realtime_pnl

realized_total_pnl = 0.0

def _write_log_entry(entry: dict):
    with open(POSITIONS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def log_position(action, symbol, side, price, qty, pnl=0.0, reason="DRY_RUN", exit_reason=None):
    global realized_total_pnl
    if action == "CLOSE":
        realized_total_pnl += pnl

    # unrealized
    unrealized = 0.0
    for s, p in user_data_cache.get("positions", {}).items():
        u = simulate_realtime_pnl(s)
        if u is not None:
            unrealized += u

    total_equity = realized_total_pnl + unrealized
    account_balance = INITIAL_CASH + realized_total_pnl if DRY_RUN else None

    log_entry = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": price,
        "qty": qty,
        "pnl": pnl,
        "total_equity": total_equity,
        "account_balance": account_balance,
        "reason": reason,
        "exit_reason": exit_reason
    }

    print(f"[{log_entry['timestamp']}] {action} {side} {symbol} @ {price:.4f} "
          f"QTY={qty:.4f} PnL={pnl:.4f} TotalEquity={total_equity:.4f}")

    _write_log_entry(log_entry)

    # send to telegram
    try:
        text = (
            f"*{action}* {side} `{symbol}` @ `{price:.4f}`\n"
            f"QTY: `{qty:.4f}`\nPnL: `{pnl:.4f}`\nTotalEquity: `{total_equity:.4f}`\n"
            f"AccountBalance: `{account_balance}`\nReason: {reason}"
        )
        if exit_reason:
            text += f"\nExitReason: {exit_reason}"
        send_telegram_message(text)
    except Exception as e:
        print("Ошибка отправки лога в Telegram:", e)
