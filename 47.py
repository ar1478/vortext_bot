# vortex_bot.py — Telegram Meme Coin Bot with User-Provided Wallets
"""
Users register their own Solana public address; the bot tracks balances.
Commands:
 - /start     : Welcome message
 - /help      : List commands
 - /register <publicKey> : Save your Solana public address
 - /wallets   : Show your registered public address
 - /balance   : Check your SOL balance of that address
"""
import os
import json
import logging
from solders.pubkey import Pubkey
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from solana.rpc.async_api import AsyncClient

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

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡️ Welcome! Please register your own Solana wallet with /register <publicKey>\n"
        "Then use /balance to check your SOL."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start — Welcome message\n"
        "/help — List commands\n"
        "/register <publicKey> — Save your Solana address\n"
        "/wallets — Show your registered address\n"
        "/balance — Check your SOL balance"
    )
    await update.message.reply_text(help_text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /register <publicKey>")
        return
    addr = context.args[0]
    try:
        pubkey = Pubkey.from_string(addr)
    except Exception:
        await update.message.reply_text("❌ Invalid Solana public key format.")
        return
    data = load_user_data()
    user_id = str(update.effective_user.id)
    data[user_id] = str(pubkey)
    save_user_data(data)
    await update.message.reply_text(f"✅ Registered your wallet: `{pubkey}`", parse_mode="Markdown")
    logger.info(f"User {user_id} registered wallet {pubkey}")

async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if addr:
        await update.message.reply_text(f"👜 Your registered wallet:\n`{addr}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❌ You have no wallet registered. Use /register <publicKey> to register."
        )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if not addr:
        await update.message.reply_text(
            "❌ No wallet found. Please /register your public key first."
        )
        return
    try:
        pubkey = Pubkey.from_string(addr)
        resp = await client.get_balance(pubkey)
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 Your balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Balance error for user {user_id}: {e}")
        await update.message.reply_text("❌ Could not retrieve balance. Try again later.")

# === MAIN ENTRY ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("wallets", wallets))
    app.add_handler(CommandHandler("balance", balance))

    app.bot.set_my_commands([
        BotCommand("start", "Welcome message"),
        BotCommand("help", "List commands"),
        BotCommand("register", "Register your public key"),
        BotCommand("wallets", "Show registered wallet"),
        BotCommand("balance", "Check SOL balance"),
    ])
    logger.info("🚀 Bot started: user-provided wallets mode")
    app.run_polling()

if __name__ == '__main__':
    main()
