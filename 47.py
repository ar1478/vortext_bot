# vortex_bot.py
"""
Telegram Meme Coin Trading Bot (Vortex Alternative)

Self-hosted framework for Solana launchpad interactions via Telegram.
Features:
 - /start, /help, /wallets, /balance, /status
 - On-chain Solana keypair loading via solders
 - Placeholder stubs: /launch, /snipe, /sell
"""
import os
import json
import logging
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from solana.rpc.async_api import AsyncClient

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8152282783:AAH0ylvc63x_u1e15ST0-4zjQe_K4b4bVRc")
KEYPAIR_PATH = os.getenv("KEYPAIR_PATH", "./id.json")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# --- LOGGING ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- LOAD KEYPAIR ---
try:
    with open(KEYPAIR_PATH, "r") as f:
        secret_list = json.load(f)
    secret_bytes = bytes(secret_list)
    keypair = Keypair.from_bytes(secret_bytes)
    WALLET_PUBKEY = Pubkey.from_string(str(keypair.pubkey()))
    logger.info(f"Loaded wallet: {WALLET_PUBKEY}")
except FileNotFoundError:
    logger.error(f"Keypair file not found: {KEYPAIR_PATH}")
    raise SystemExit("Error loading Solana keypair: file not found.")
except Exception as e:
    logger.error(f"Failed to load keypair: {e}")
    raise SystemExit("Error loading Solana keypair. Check KEYPAIR_PATH and id.json format.")

# --- SOLANA CLIENT ---
client = AsyncClient(SOLANA_RPC_URL)

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('⚡️ VortexTrader is online!\nType /help to see commands.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        ("start", "Welcome message"),
        ("help", "List commands"),
        ("wallets", "Show loaded wallet public key"),
        ("balance", "Show SOL balance"),
        ("status", "Wallet + balance summary"),
        ("launch", "(coming soon) Launch token"),
        ("snipe", "(coming soon) Snipe token"),
        ("sell", "(coming soon) Sell tokens")
    ]
    text = "Available commands:\n" + "\n".join(f"/{c} — {d}" for c, d in commands)
    await update.message.reply_text(text)

async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👜 Loaded wallet: {WALLET_PUBKEY}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        resp = await client.get_balance(WALLET_PUBKEY)
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 SOL Balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text("Error fetching balance.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Wallet: {WALLET_PUBKEY}\nSOL Balance: {(await client.get_balance(WALLET_PUBKEY)).value / 1e9:.6f} SOL")

async def launch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/launch not implemented yet. Coming soon 🔧")

async def snipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/snipe not implemented yet. Coming soon 🔧")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/sell not implemented yet. Coming soon 🔧")

# --- ENTRY POINT ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Register commands
    for cmd, handler in [
        ("start", start),
        ("help", help_command),
        ("wallets", wallets),
        ("balance", balance),
        ("status", status),
        ("launch", launch),
        ("snipe", snipe),
        ("sell", sell),
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    # Set Telegram UI menu
    app.bot.set_my_commands([
        BotCommand("start", "Welcome message"),
        BotCommand("help", "List commands"),
        BotCommand("wallets", "Show wallet public key"),
        BotCommand("balance", "Show SOL balance"),
        BotCommand("status", "Wallet + balance summary"),
    ])
    logger.info("Starting VortexTrader bot...")
    # Blocking call, no extra asyncio.run
    app.run_polling()

if __name__ == '__main__':
    main()
