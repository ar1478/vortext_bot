# vortex_bot.py — Telegram Meme Coin Bot (Interactive Registration)
"""
Commands:
 - /start     : Welcome message
 - /help      : List commands
 - /register  : Start interactive wallet registration
 - /wallets   : Show your registered address
 - /deposit   : Get QR code to deposit SOL
 - /balance   : Check your SOL balance
 - /history   : View recent transactions
 - /status    : Wallet + balance summary
 - /launch    : Analyze optimal entry timing
 - /snipe     : (stub) Snipe token
 - /sell      : (stub) Sell token
"""
import os
import json
import logging
import qrcode
from io import BytesIO
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from solana.rpc.async_api import AsyncClient
import httpx

# === CONFIGURATION ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === SOLANA CLIENT ===
client = AsyncClient(SOLANA_RPC_URL)

# === USER DATA STORAGE ===

def load_user_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_user_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# === STATES ===
REGISTER = 1

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡️ Welcome! Use /register to link your Solana wallet, then /help for commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start — Welcome message\n"
        "/help — List commands\n"
        "/register — Begin wallet registration\n"
        "/wallets — Show registered address\n"
        "/deposit — QR code to deposit SOL\n"
        "/balance — Check your SOL balance\n"
        "/history — Recent transactions\n"
        "/status — Wallet + balance summary\n"
        "/launch <symbol> <mint> — Analyze timing\n"
        "/snipe <symbol> — Sniping stub\n"
        "/sell <symbol> — Selling stub"
    )
    await update.message.reply_text(help_text)

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please send me your Solana public key (starts with ‘A’ to ‘Z’, 44 chars)."
    )
    return REGISTER

async def register_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    addr = update.message.text.strip()
    try:
        pubkey = Pubkey.from_string(addr)
    except Exception:
        await update.message.reply_text("❌ Invalid Solana public key. Try again or /cancel.")
        return REGISTER
    data = load_user_data()
    user_id = str(update.effective_user.id)
    data[user_id] = addr
    save_user_data(data)
    name = update.effective_user.first_name or update.effective_user.username or user_id
    await update.message.reply_text(f"✅ Registered wallet for {name}: `{addr}`", parse_mode="Markdown")
    return ConversationHandler.END

async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Registration canceled.")
    return ConversationHandler.END

async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if addr:
        await update.message.reply_text(f"👜 Your wallet:\n`{addr}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No wallet registered. Use /register.")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if not addr:
        await update.message.reply_text("❌ Register first with /register.")
        return
    img = qrcode.make(addr)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    await update.message.reply_photo(photo=buf, caption="Scan to deposit SOL:")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if not addr:
        await update.message.reply_text("❌ Register first with /register.")
        return
    try:
        resp = await client.get_balance(Pubkey.from_string(addr))
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 Your balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Balance error for {update.effective_user.id}: {e}")
        await update.message.reply_text("❌ Could not fetch balance.")

# (Other handlers: history, status, launch, snipe, sell omitted for brevity)

# === MAIN ENTRY ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive)]},
        fallbacks=[CommandHandler('cancel', register_cancel)]
    )
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(conv)
    app.add_handler(CommandHandler('wallets', wallets))
    app.add_handler(CommandHandler('deposit', deposit))
    app.add_handler(CommandHandler('balance', balance))
    # ... register other command handlers similarly

    app.bot.set_my_commands([
        BotCommand('start','Welcome'), BotCommand('help','Commands'), BotCommand('register','Link wallet'),
        BotCommand('wallets','Show wallet'), BotCommand('deposit','Deposit QR'), BotCommand('balance','SOL balance')
        # add others
    ])
    logger.info("🚀 Bot started: interactive registration enabled")
    app.run_polling()

if __name__ == '__main__':
    main()
