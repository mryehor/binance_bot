import json
import pandas as pd
from telegram_bot import send_telegram_message
from config import POSITIONS_LOG_FILE, INITIAL_CASH, DRY_RUN
from data_store import user_data_cache
from pnl_utils import simulate_realtime_pnl

realized_total_pnl = 0.0
opened_positions = set()  # (symbol, side, entry_price) для отслеживания открытых позиций
def _write_log_entry(entry: dict):
    with open(POSITIONS_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def escape_markdown(text):
    if text is None:
        return "N/A"
    text = str(text)
    for ch in "_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def log_position(action, symbol, side, price, qty, pnl=0.0,
                 reason="DRY_RUN", exit_reason=None, tp=None, sl=None):
    global realized_total_pnl, opened_positions
    key = (symbol, side, price,)
    if action.upper() == "OPEN":
        if key in opened_positions:
            # Уже открыта — пропускаем
            return
        opened_positions.add(key)

    if action.upper() == "CLOSE":
        # Удаляем из открытых при закрытии
        opened_positions.discard(key)
        realized_total_pnl += pnl

    # unrealized PnL
    unrealized = 0.0
    for s, p in user_data_cache.get("positions", {}).items():
        u = simulate_realtime_pnl(s)
        if u is not None:
            unrealized += u

    # баланс аккаунта = стартовый капитал + PnL закрытых + PnL открытых
    total_equity = INITIAL_CASH + realized_total_pnl + unrealized
    account_balance = total_equity

    # лог всегда создаётся
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
        "exit_reason": exit_reason,
        "tp": tp,
        "sl": sl
    }

    print(f"[{log_entry['timestamp']}] {action} {side} {symbol} @ {price:.4f} "
          f"QTY={qty:.4f} PnL={pnl:.4f} TotalEquity={total_equity:.4f}")

    _write_log_entry(log_entry)

    # отправка в Telegram
    try:
        side_emoji = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        action_emoji = "📌" if action.upper() == "OPEN" else "✅"

        text = (
            f"{action_emoji} *{escape_markdown(action)}* {side_emoji} *{escape_markdown(symbol)}*\n"
            f"💰 Price: `{price:.4f}`\n"
            f"📊 Qty: `{qty:.4f}`\n"
            f"💵 PnL: `{pnl:.4f}`\n"
            f"💹 Total Equity: `{total_equity:.4f}`\n"
            f"🏦 Account Balance: `{account_balance:.4f}`\n"
            f"📝 Reason: {escape_markdown(reason)}"
        )

        # добавляем TP/SL, если заданы
        if tp is not None:
            text += f"\n🎯 TP: `{tp:.4f}`"
        if sl is not None:
            text += f"\n🛑 SL: `{sl:.4f}`"

        if exit_reason:
            text += f"\n⚡ Exit Reason: {escape_markdown(exit_reason)}"

        send_telegram_message(text)
    except Exception as e:
        print("Ошибка отправки лога в Telegram:", e)


def get_recent_logs(limit=50):
    logs = []
    try:
        with open(POSITIONS_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                logs.append(json.loads(line))
    except Exception as e:
        print("Ошибка чтения логов:", e)
    return logs
