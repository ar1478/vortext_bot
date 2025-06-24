# vortex_bot.py — Telegram Meme Coin Bot (User-Provided Wallets with QR & History)
"""
Commands:
 - /start               : Welcome message
 - /help                : List commands
 - /register <pubkey>   : Save your Solana public address
 - /wallets             : Show your registered address
 - /balance             : Check your SOL balance
 - /deposit             : Get your address QR code for deposit
 - /history             : View recent transaction signatures
"""
import os
import json
import logging
import qrcode
from io import BytesIO
from datetime import datetime
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
        "⚡️ Welcome! Register your wallet with /register <publicKey>\n"
        "Then use /deposit to get a QR code, and /balance or /history to view your funds."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start — Welcome message\n"
        "/help — List commands\n"
        "/register <pubkey> — Save your public key\n"
        "/wallets — Show registered address\n"
        "/deposit — Get QR code for deposit\n"
        "/balance — Check your SOL balance\n"
        "/history — View recent transaction signatures"
    )
    await update.message.reply_text(help_text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /register <publicKey>")
        return
    addr = context.args[0]
    try:
        Pubkey.from_string(addr)
    except Exception:
        await update.message.reply_text("❌ Invalid Solana public key.")
        return
    data = load_user_data()
    user_id = str(update.effective_user.id)
    data[user_id] = addr
    save_user_data(data)
    await update.message.reply_text(f"✅ Registered your wallet: `{addr}`", parse_mode="Markdown")

async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if addr:
        await update.message.reply_text(f"👜 Your wallet:\n`{addr}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No wallet registered. Use /register <publicKey>.")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    # Generate QR code
    img = qrcode.make(addr)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    await update.message.reply_photo(photo=buf, caption="Scan to deposit SOL:")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        pubkey = Pubkey.from_string(addr)
        resp = await client.get_balance(pubkey)
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 Your balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Balance error for {user_id}: {e}")
        await update.message.reply_text("❌ Could not fetch balance.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        pubkey = Pubkey.from_string(addr)
        sigs = await client.get_signatures_for_address(pubkey, limit=10)
        entries = sigs.value
        if not entries:
            await update.message.reply_text("No recent transactions found.")
            return
        lines = []
        for e in entries:
            time = datetime.utcfromtimestamp(e.block_time).strftime('%Y-%m-%d %H:%M:%S') if e.block_time else 'N/A'
            lines.append(f"{e.signature} @ {time}")
        await update.message.reply_text("📝 Recent txs:\n" + "\n".join(lines))
    except Exception as e:
        logger.error(f"History error for {user_id}: {e}")
        await update.message.reply_text("❌ Could not fetch history.")

# === MAIN ENTRY ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    for cmd, handler in [
        ("start", start), ("help", help_command), ("register", register),
        ("wallets", wallets), ("deposit", deposit), ("balance", balance), ("history", history)
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    app.bot.set_my_commands([
        BotCommand("start", "Welcome message"),
        BotCommand("help", "List commands"),
        BotCommand("register", "Register your public key"),
        BotCommand("wallets", "Show your address"),
        BotCommand("deposit", "Get QR code to deposit"),
        BotCommand("balance", "Check your SOL balance"),
        BotCommand("history", "View recent txs"),
    ])
    logger.info("🚀 Bot started: QR & history enabled")
    app.run_polling()

if __name__ == '__main__':
    main()
