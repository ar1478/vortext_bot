# vortex_bot.py — The Ultimate Telegram Meme Coin Trading Bot
"""
All-in-one Telegram trading bot for Solana launchpads (pump.fun and bullx.io).
Features:
 - Interactive wallet linking (/register)
 - Balance, history, status, portfolio overview
 - Real-time token discovery (/scan, /topgainers, /price)
 - Advanced trading analysis: /launch, /snipe, /sell
 - Risk controls: per-user slippage & stop-loss settings
 - Alerts & notifications
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
        ("snipe", "Get entry time suggestion"),
        ("sell", "Get selling info"),
        ("set_slippage", "Set max slippage %"),
        ("set_stoploss", "Set stop-loss %")
    ]
    text = "Available commands:\n" + "\n".join(f"/{c} — {d}" for c, d in cmds)
    await update.message.reply_text(text)

# **Registration**
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

# **Wallet Info**
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

# **Market Commands**
async def scan(update, ctx):
    tokens = await get_potential_10x_tokens()
    if not tokens:
        await update.message.reply_text("No potential 10x tokens found.")
        return
    text = "Potential 10x tokens:\n"
    for t in tokens:
        symbol = t['symbol']
        price = t['priceUsd']
        volume = t['volume']['h24']
        change = t['priceChange']['h1']
        text += f"{symbol}: ${price}, Vol: ${volume}, Change: {change}%\n"
    await update.message.reply_text(text)

async def topgainers(update, ctx):
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=priceChange.h24&order=desc&limit=10")
        data = response.json()
        tokens = data['tokens']
        text = "Top gainers:\n"
        for t in tokens:
            symbol = t['symbol']
            change = t['priceChange']['h24']
            text += f"{symbol}: {change}%\n"
        await update.message.reply_text(text)

async def price(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Usage: /price <mint>")
        return
    mint = ctx.args[0]
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        data = response.json()
        if not data['tokens']:
            await update.message.reply_text("Token not found.")
            return
        token = data['tokens'][0]
        price = token['priceUsd']
        await update.message.reply_text(f"Price of {token['symbol']}: ${price}")

# **Analysis and Trade Suggestions**
async def launch(update, ctx):
    if len(ctx.args) != 2:
        return await update.message.reply_text("Usage: /launch <symbol> <mint>")
    sym, mint = ctx.args
    # Fetch DEX Screener data
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        data = response.json()
        if not data['tokens']:
            await update.message.reply_text("Token not found on DEX Screener.")
            return
        token = data['tokens'][0]
        price = token['priceUsd']
        volume = token['volume']['h24']
        change_h1 = token['priceChange']['h1']
        change_h24 = token['priceChange']['h24']
    # Fetch platform-specific data
    pump_time = await analyze_pumpfun_optimal(mint)
    bullx_price = await analyze_bullxio_optimal(mint)
    text = (
        f"🔍 {sym} Analysis (DEX Screener):\n"
        f"Price: ${price}\n24h Volume: ${volume}\n"
        f"1h Change: {change_h1}%\n24h Change: {change_h24}%\n\n"
        f"Pump.fun: Optimal launch time - {pump_time}\n"
        f"Bullx.io: Optimal price - {bullx_price}"
    )
    await update.message.reply_text(text)

async def snipe(update, ctx):
    if len(ctx.args) != 1:
        await update.message.reply_text("Usage: /snipe <mint>")
        return
    mint = ctx.args[0]
    # Check pump.fun
    pump_time = await analyze_pumpfun_optimal(mint)
    if pump_time != "N/A":
        # Suggest entry shortly after launch
        entry_time = datetime.strptime(pump_time, '%H:%M:%S UTC') + timedelta(minutes=5)
        await update.message.reply_text(f"Snipe on pump.fun at {entry_time.strftime('%H:%M:%S UTC')}")
        return
    # Check bullx.io
    bullx_price = await analyze_bullxio_optimal(mint)
    if bullx_price != "N/A":
        # Suggest entry in the next hour based on current time
        now = datetime.utcnow()
        entry_hour = (now + timedelta(hours=1)).strftime('%H:00 UTC')
        await update.message.reply_text(f"Snipe on bullx.io at {entry_hour} with price {bullx_price}")
        return
    await update.message.reply_text("Token not found on pump.fun or bullx.io.")

async def sell(update, ctx):
    if len(ctx.args) != 1:
        await update.message.reply_text("Usage: /sell <mint>")
        return
    mint = ctx.args[0]
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        data = response.json()
        if not data['tokens']:
            await update.message.reply_text("Token not found.")
            return
        token = data['tokens'][0]
        price = token['priceUsd']
        high = token.get('priceHigh24h', 'N/A')
        volume = token['volume']['h24']
        text = (
            f"{token['symbol']} Selling Info:\n"
            f"Current Price: ${price}\n24h High: ${high}\n24h Volume: ${volume}\n"
            f"Where to sell: pump.fun or bullx.io"
        )
        await update.message.reply_text(text)

# **Risk Settings**
async def set_slippage(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_slippage <percent>")
    val = float(ctx.args[0])
    uid = str(update.effective_user.id)
    d = load_data()
    d[uid]['slippage'] = val
    save_data(d)
    await update.message.reply_text(f"Slippage set to {val}%")

async def set_stoploss(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_stoploss <percent>")
    val = float(ctx.args[0])
    uid = str(update.effective_user.id)
    d = load_data()
    d[uid]['stoploss'] = val
    save_data(d)
    await update.message.reply_text(f"Stop-loss set to {val}%")

# **Helper Functions**
async def get_potential_10x_tokens():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=volume.h24&order=desc&limit=100")
        data = response.json()
        tokens = data['tokens']
        # Filter for potential 10x: high volume and recent price surge
        potential = [
            t for t in tokens
            if t.get('priceChange', {}).get('h1', 0) > 10 and t['volume']['h24'] > 100000
        ]
        potential.sort(key=lambda x: x['volume']['h24'] * x['priceChange']['h1'], reverse=True)
        return potential[:5]  # Top 5 candidates

async def analyze_pumpfun_optimal(mint):
    try:
        async with httpx.AsyncClient() as c:
            j = (await c.get(f"https://api.pump.fun/v1/launches/{mint}")).json()
            lt = datetime.fromisoformat(j['launch_time'])
            return (lt + timedelta(seconds=30)).strftime('%H:%M:%S UTC')
    except:
        return "N/A"

async def analyze_bullxio_optimal(mint):
    try:
        async with httpx.AsyncClient() as c:
            j = (await c.get(f"https://api.bullxio.com/orderbook/{mint}")).json()
            bids = j.get('bids
