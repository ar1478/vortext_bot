# vortex_bot.py — Simplified Telegram Meme Coin Bot (Per-User Wallets)
"""
Telegram bot where each user gets their own Solana wallet and balance.
Commands:
 - /start : Welcome message
 - /help  : List commands
 - /wallets : Show or create your Solana wallet address
 - /balance : Check your SOL balance
"""
import os
import json
import logging
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from solana.rpc.async_api import AsyncClient

# === CONFIGURATION ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
USER_KEYS_DIR = "./user_wallets"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === SOLANA CLIENT ===
client = AsyncClient(SOLANA_RPC_URL)

# === WALLET MANAGEMENT ===
def get_or_create_user_keypair(user_id: int) -> Keypair:
    os.makedirs(USER_KEYS_DIR, exist_ok=True)
    key_path = os.path.join(USER_KEYS_DIR, f"{user_id}.json")
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            secret_list = json.load(f)
        return Keypair.from_bytes(bytes(secret_list))
    # create new keypair
    kp = Keypair()
    with open(key_path, "w") as f:
        json.dump(list(bytes(kp)), f)
    logger.info(f"Created new wallet for user {user_id}: {kp.pubkey()}")
    return kp

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡️ Welcome! Each user has a private Solana wallet.\n" 
        "Use /wallets to get your address and /balance to check your SOL."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start — Welcome message\n"
        "/help — List commands\n"
        "/wallets — Show or create your Solana wallet address\n"
        "/balance — Check your SOL balance"
    )
    await update.message.reply_text(help_text)

async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kp = get_or_create_user_keypair(user_id)
    pubkey = kp.pubkey()
    await update.message.reply_text(
        f"👜 Your Solana wallet address:\n`{pubkey}`",
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kp = get_or_create_user_keypair(user_id)
    pubkey = kp.pubkey()
    try:
        resp = await client.get_balance(pubkey)
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 Your balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Error fetching balance for user {user_id}: {e}")
        await update.message.reply_text("❌ Could not retrieve balance. Please try again later.")

# === MAIN ENTRY ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("wallets", wallets))
    app.add_handler(CommandHandler("balance", balance))
    # Set bot commands for UI
    app.bot.set_my_commands([
        BotCommand("start", "Welcome message"),
        BotCommand("help", "List commands"),
        BotCommand("wallets", "Show Solana wallet address"),
        BotCommand("balance", "Check your SOL balance"),
    ])
    logger.info("🚀 Bot started: per-user wallet mode")
    app.run_polling()

if __name__ == '__main__':
    main()
