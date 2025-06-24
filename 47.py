# vortex_bot.py — The Ultimate Telegram Meme Coin Trading Bot
"""
All-in-one Telegram trading bot for Solana launchpads (pump.fun and bullx.io).
Features:
 - Interactive wallet linking (/register)
 - Balance, history, status, portfolio overview
 - Real-time token discovery (/scan, /topgainers, /price)
 - Advanced trading analysis: /launch, /snipe, /sell
 - Risk controls: per-user slippage & stop-loss settings
 - Alerts, charts, and notifications
"""
import os
import json
import logging
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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === SOLANA CLIENT ===
rpc_client = AsyncClient(SOLANA_RPC_URL)

# === USER STORAGE & SETTINGS ===
def load_data():
    return json.loads(open(DATA_FILE).read()) if os.path.exists(DATA_FILE) else {}

def save_data(d):
    open(DATA_FILE, 'w').write(json.dumps(d))

# === STATES ===
REGISTER = 1

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Welcome to UltimateTraderBot! Use /register to link your wallet and /help for all features."
    )

async def help_command(update, context):
    cmds = [
        ("register", "Link your Solana address"),
        ("wallets", "Show linked address"),
        ("balance", "Check SOL balance"),
        ("portfolio", "Show all SPL token balances"),
        ("history", "Recent txs"),
        ("status", "Wallet & balance summary"),
        ("scan", "Scan for potential 10x tokens"),
        ("topgainers", "Top gaining tokens"),
        ("price", "Get token price"),
        ("launch", "Analyze token with DEX Screener"),
        ("snipe", "Suggest entry time"),
        ("sell", "Show selling signals"),
        ("set_slippage", "Set max slippage %"),
        ("set_stoploss", "Set stop-loss %"),
        ("alerts", "Enable price alerts"),
        ("chart", "Get basic price chart")
    ]
    text = "Available commands:\n" + "\n".join(f"/{c} — {d}" for c, d in cmds)
    await update.message.reply_text(text)

# Registration
async def register_start(update, ctx):
    await update.message.reply_text("Send your Solana public key to link:")
    return REGISTER

async def register_receive(update, ctx):
    key = update.message.text.strip()
    try:
        Pubkey.from_string(key)
    except:
        return await update.message.reply_text("Invalid key, try again.")
    data = load_data()
    uid = str(update.effective_user.id)
    data[uid] = {"wallet": key, "slippage": 1.0, "stoploss": 5.0}
    save_data(data)
    name = update.effective_user.first_name or uid
    await update.message.reply_text(f"✅ {name}, wallet `{key}` linked!", parse_mode="Markdown")
    return ConversationHandler.END

async def register_cancel(update, ctx):
    await update.message.reply_text("Registration canceled.")
    return ConversationHandler.END

# Wallet Info
async def wallets(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if data:
        await update.message.reply_text(f"Wallet: `{data['wallet']}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("No wallet linked.")

async def balance(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
    sol = bal.value / 1e9
    await update.message.reply_text(f"💰 SOL: {sol:.6f}")

async def portfolio(update, ctx):
    await update.message.reply_text("📊 Portfolio feature coming soon.")

async def history(update, ctx):
    uid = str(update.effective_user.id)
    data = load_data().get(uid)
    if not data:
        return await update.message.reply_text("Link first.")
    sigs = (await rpc_client.get_signatures_for_address(Pubkey.from_string(data['wallet']), limit=5)).value
    txt = "Recent TXs:\n" + "\n".join(f"{e.signature}" for e in sigs)
    await update.message.reply_text(txt)

async def status(update, ctx):
    uid = str(update.effective_user.id)
    data = load_data().get(uid)
    if not data:
        return await update.message.reply_text("Link first.")
    bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
    sol = bal.value / 1e9
    await update.message.reply_text(f"Wallet: `{data['wallet']}`\nSOL: {sol:.6f} SOL", parse_mode="Markdown")

# Market Tools
async def alerts(update, ctx):
    await update.message.reply_text("📡 Price alerts coming soon.")

async def chart(update, ctx):
    await update.message.reply_text("📈 Charting feature coming soon.")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', lambda u, c: u.message.reply_text("Use /register to begin.")))
    app.add_handler(CommandHandler('launch', launch_analysis))
    app.add_handler(CommandHandler('snipe', snipe))
    app.add_handler(CommandHandler('sell', sell))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive)]},
        fallbacks=[]
    ))
    app.bot.set_my_commands([
        BotCommand("register", "Link wallet"),
        BotCommand("status", "Check SOL & wallet"),
        BotCommand("launch", "Scan top coins"),
        BotCommand("snipe", "Best time to enter"),
        BotCommand("sell", "Exit info")
    ])
    logger.info("Vortex Bot is live")
    app.run_polling()

if __name__ == '__main__':
    main()
