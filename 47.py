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
        ("portfolio", "Show SPL token balances"),
        ("history", "Recent transactions"),
        ("status", "Wallet & balance summary"),
        ("scan", "Scan for potential 10x tokens"),
        ("topgainers", "Top gaining tokens"),
        ("price", "Get token price"),
        ("launch", "Analyze token with DEX Screener"),
        ("snipe", "Best time to enter"),
        ("sell", "Selling insights"),
        ("set_slippage", "Set max slippage %"),
        ("set_stoploss", "Set stop-loss %")
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

# Enhanced Portfolio Command
async def portfolio(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    wallet = Pubkey.from_string(data['wallet'])
    token_accounts = await rpc_client.get_token_accounts_by_owner(wallet, commitment="confirmed")
    if not token_accounts.value:
        await update.message.reply_text("No SPL tokens found.")
        return
    reply = "Your SPL Tokens:\n"
    for acc in token_accounts.value:
        token_account = acc.pubkey
        balance = await rpc_client.get_token_account_balance(token_account)
        mint = balance.value.mint
        amount = balance.value.ui_amount
        reply += f"- {mint}: {amount}\n"
    await update.message.reply_text(reply)

# Enhanced History Command
async def history(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    wallet = Pubkey.from_string(data['wallet'])
    signatures = await rpc_client.get_signatures_for_address(wallet, limit=5)
    if not signatures.value:
        await update.message.reply_text("No recent transactions.")
        return
    reply = "Recent Transactions:\n"
    for sig in signatures.value:
        reply += f"- {sig.signature} (slot {sig.slot})\n"
    await update.message.reply_text(reply)

async def status(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
    sol = bal.value / 1e9
    await update.message.reply_text(
        f"📊 Wallet Status:\n"
        f"Wallet: `{data['wallet']}`\n"
        f"SOL: {sol:.6f}\n"
        f"Slippage: {data['slippage']}%\n"
        f"Stop-loss: {data['stoploss']}%",
        parse_mode="Markdown"
    )

# Enhanced Scan Command with Filters
async def scan(update, ctx):
    args = ctx.args
    min_volume = 100000
    min_change = 20
    for arg in args:
        if arg.startswith("min_volume="):
            min_volume = float(arg.split("=")[1])
        elif arg.startswith("min_change="):
            min_change = float(arg.split("=")[1])
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=volume.h24&order=desc&limit=50")
        tokens = response.json().get("tokens", [])
    candidates = [
        t for t in tokens
        if t.get('priceChange', {}).get('h1', 0) > min_change and t['volume']['h24'] > min_volume
    ]
    if not candidates:
        await update.message.reply_text("No high-potential tokens found with the given filters.")
        return
    reply = "🔍 Potential 10x Tokens:\n"
    for t in candidates[:5]:
        reply += f"\n{t['symbol']} — ${t['priceUsd']}, 1h: {t['priceChange']['h1']}%\nhttps://pump.fun/{t['address']}"
    await update.message.reply_text(reply)

# Enhanced Top Gainers Command with Timeframe
async def topgainers(update, ctx):
    timeframe = "h24"
    if ctx.args and ctx.args[0].startswith("timeframe="):
        timeframe = ctx.args[0].split("=")[1]
        if timeframe not in ["h1", "h6", "h24"]:
            return await update.message.reply_text("Invalid timeframe. Use h1, h6, or h24.")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=priceChange.{timeframe}&order=desc&limit=10")
        tokens = response.json().get("tokens", [])
    if not tokens:
        await update.message.reply_text("No top gainers available right now.")
        return
    reply = f"🏆 Top Gainers ({timeframe}):\n"
    for t in tokens[:5]:
        reply += f"\n{t['symbol']} — ${t['priceUsd']}, {timeframe}: {t['priceChange'][timeframe]}%\nhttps://pump.fun/{t['address']}"
    await update.message.reply_text(reply)

# Enhanced Price Command with More Details
async def price(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /price <token_address>")
    mint = ctx.args[0]
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        token = response.json().get("tokens", [{}])[0]
    if not token:
        await update.message.reply_text("Token not found.")
        return
    liquidity = token.get('liquidity', {}).get('usd', 'N/A')
    market_cap = token.get('fdv', 'N/A')
    await update.message.reply_text(
        f"💰 {token['symbol']} — ${token['priceUsd']}\n"
        f"24h Change: {token['priceChange']['h24']}%\n"
        f"Liquidity: ${liquidity}\n"
        f"Market Cap: ${market_cap}\n"
        f"https://pump.fun/{mint}"
    )

# Enhanced Launch Command with More Details
async def launch(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /launch <token_address>")
    mint = ctx.args[0]
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        token = response.json().get("tokens", [{}])[0]
    if not token:
        await update.message.reply_text("Token not found.")
        return
    liquidity = token.get('liquidity', {}).get('usd', 'N/A')
    market_cap = token.get('fdv', 'N/A')
    await update.message.reply_text(
        f"🚀 {token['symbol']} Launch Analysis:\n"
        f"Price: ${token['priceUsd']}\n"
        f"Volume (24h): ${token['volume']['h24']}\n"
        f"1h Change: {token['priceChange']['h1']}%\n"
        f"Liquidity: ${liquidity}\n"
        f"Market Cap: ${market_cap}\n"
        f"https://pump.fun/{mint}"
    )

async def snipe(update, ctx):
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=volume.h24&order=desc&limit=50")
        tokens = response.json().get("tokens", [])
    candidates = [
        t for t in tokens
        if t.get('priceChange', {}).get('h1', 0) > 15 and t['volume']['h24'] > 150000
    ]
    if not candidates:
        await update.message.reply_text("No sniper targets found right now. Check later.")
        return
    now = datetime.utcnow()
    reply = "🎯 Best sniper targets (next hour):\n"
    for t in candidates[:5]:
        symbol = t['symbol']
        price = t['priceUsd']
        vol = t['volume']['h24']
        mint = t['address']
        entry = now + timedelta(minutes=5)
        reply += f"\n{symbol} — ${price}, Vol: ${vol}, Entry: {entry.strftime('%H:%M:%S UTC')}\nhttps://pump.fun/{mint}"
    await update.message.reply_text(reply)

async def sell(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    await update.message.reply_text(
        f"💸 Sell Strategy:\n"
        f"Slippage: {data['slippage']}%\n"
        f"Stop-loss: {data['stoploss']}%\n"
        f"Selling insights coming soon!"
    )

async def set_slippage(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_slippage <percentage>")
    data = load_data()
    uid = str(update.effective_user.id)
    if uid not in data:
        return await update.message.reply_text("Link with /register.")
    try:
        slippage = float(ctx.args[0])
        if slippage < 0 or slippage > 100:
            raise ValueError
    except ValueError:
        return await update.message.reply_text("Invalid percentage (0-100).")
    data[uid]["slippage"] = slippage
    save_data(data)
    await update.message.reply_text(f"Slippage set to {slippage}%")

async def set_stoploss(update, ctx):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_stoploss <percentage>")
    data = load_data()
    uid = str(update.effective_user.id)
    if uid not in data:
        return await update.message.reply_text("Link with /register.")
    try:
        stoploss = float(ctx.args[0])
        if stoploss < 0 or stoploss > 100:
            raise ValueError
    except ValueError:
        return await update.message.reply_text("Invalid percentage (0-100).")
    data[uid]["stoploss"] = stoploss
    save_data(data)
    await update.message.reply_text(f"Stop-loss set to {stoploss}%")

# Main
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive)]},
        fallbacks=[CommandHandler('cancel', register_cancel)]
    )
    # Add all handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(conv)
    app.add_handler(CommandHandler('wallets', wallets))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('portfolio', portfolio))
    app.add_handler(CommandHandler('history', history))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('scan', scan))
    app.add_handler(CommandHandler('topgainers', topgainers))
    app.add_handler(CommandHandler('price', price))
    app.add_handler(CommandHandler('launch', launch))
    app.add_handler(CommandHandler('snipe', snipe))
    app.add_handler(CommandHandler('sell', sell))
    app.add_handler(CommandHandler('set_slippage', set_slippage))
    app.add_handler(CommandHandler('set_stoploss', set_stoploss))
    
    # Register all commands with Telegram
    app.bot.set_my_commands([
        BotCommand("start", "Welcome"),
        BotCommand("help", "Commands"),
        BotCommand("register", "Link wallet"),
        BotCommand("wallets", "Show wallet"),
        BotCommand("balance", "SOL balance"),
        BotCommand("portfolio", "Portfolio overview
