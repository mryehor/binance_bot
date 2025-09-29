from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update # pyright: ignore[reportMissingImports]
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes # pyright: ignore[reportMissingImports]
import matplotlib.pyplot as plt # pyright: ignore[reportMissingImports]
from io import BytesIO
from pos_manager import user_data_cache, INITIAL_CASH  # твои существующие данные
from logger import realized_total_pnl
# Флаг паузы торговли
TRADING_PAUSED = False

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⏸ Пауза/Возобновить", callback_data="toggle_pause")],
        [InlineKeyboardButton("💰 Баланс и позиции", callback_data="balance")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Управление торговлей:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRADING_PAUSED
    query = update.callback_query
    await query.answer()

    if query.data == "toggle_pause":
        TRADING_PAUSED = not TRADING_PAUSED
        state = "⏸ Пауза" if TRADING_PAUSED else "▶️ Торговля возобновлена"
        await query.edit_message_text(text=f"Текущее состояние: {state}")

    elif query.data == "balance":
        balance = INITIAL_CASH + realized_total_pnl
        positions = user_data_cache.get("positions", {})
        text = f"💳 Баланс: {balance:.2f}\n"
        text += "📌 Открытые позиции:\n"
        if positions:
            for sym, info in positions.items():
                text += f"- {sym}: {info}\n"
        else:
            text += "Нет открытых позиций"
        await query.edit_message_text(text=text)

    elif query.data == "stats":
        # Пример графика PnL (заменить на реальные данные)
        equity_history = user_data_cache.get("equity_history", [INITIAL_CASH])
        plt.figure(figsize=(6,4))
        plt.plot(equity_history, marker='o')
        plt.title("История баланса")
        plt.xlabel("Тик")
        plt.ylabel("Баланс")
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        await query.edit_message_text("📊 Статистика баланса:")
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=buf)
        buf.close()
