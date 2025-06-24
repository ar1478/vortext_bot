# vortex_bot.py — Telegram Meme Coin Bot (User-Provided Wallets + Trading Stubs)
"""
Commands:
 - /start             : Welcome message
 - /help              : List commands
 - /register <pubkey> : Save your Solana public address
 - /wallets           : Show your registered address
 - /deposit           : Get your address QR code
 - /balance           : Check your SOL balance
 - /history           : View recent transactions
 - /status            : Summary (wallet + balance)
 - /launch <symbol>   : (coming soon) Launch token
 - /snipe <symbol>    : (coming soon) Snipe token
 - /sell <symbol>     : (coming soon) Sell tokens
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
        "⚡️ Welcome! Register your wallet with /register <publicKey> and use /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start — Welcome message\n"
        "/help — List commands\n"
        "/register <pubkey> — Save your public key\n"
        "/wallets — Show registered address\n"
        "/deposit — Get QR code to deposit SOL\n"
        "/balance — Check your SOL balance\n"
        "/history — View recent transaction signatures\n"
        "/status — Wallet + balance summary\n"
        "/launch <symbol> — Launch a token (coming soon)\n"
        "/snipe <symbol> — Snipe a token (coming soon)\n"
        "/sell <symbol> — Sell tokens (coming soon)"
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
    addr = data.get(str(update.effective_user.id))
    if addr:
        await update.message.reply_text(f"👜 Your wallet:\n`{addr}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ No wallet registered. Use /register <publicKey>.")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
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
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        resp = await client.get_balance(Pubkey.from_string(addr))
        sol = resp.value / 1e9
        await update.message.reply_text(f"💰 Your balance: {sol:.6f} SOL")
    except Exception as e:
        logger.error(f"Balance error for user {update.effective_user.id}: {e}")
        await update.message.reply_text("❌ Could not fetch balance.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        entries = (await client.get_signatures_for_address(Pubkey.from_string(addr), limit=10)).value
        if not entries:
            await update.message.reply_text("No recent transactions found.")
            return
        lines = []
        for e in entries:
            ts = e.block_time or 0
            time = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else 'N/A'
            lines.append(f"{e.signature} @ {time}")
        await update.message.reply_text("📝 Recent txs:\n" + "\n".join(lines))
    except Exception as e:
        logger.error(f"History error for user {update.effective_user.id}: {e}")
        await update.message.reply_text("❌ Could not fetch history.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_user_data()
    addr = data.get(str(update.effective_user.id))
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        resp = await client.get_balance(Pubkey.from_string(addr))
        sol = resp.value / 1e9
        await update.message.reply_text(f"Wallet: `{addr}`\nBalance: {sol:.6f} SOL", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Status error for user {update.effective_user.id}: {e}")
        await update.message.reply_text("❌ Could not fetch status.")

async def launch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Analyze optimal launch/trade timing on Pump.fun and BullX for a given token.
    Usage: /launch <symbol> <mintAddress>
    """
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Usage: /launch <symbol> <mintAddress>")
        return
    symbol, mint_address = args
    data = load_user_data()
    user_id = str(update.effective_user.id)
    addr = data.get(user_id)
    if not addr:
        await update.message.reply_text("❌ Register first with /register <publicKey>.")
        return
    try:
        # Analyze best time to trade
        pump_time = await analyze_pumpfun_optimal(mint_address)
        bull_time = await analyze_bullxio_optimal(mint_address)
        reply = (
            f"🔍 Analysis for {symbol}:
"
            f"• Pump.fun optimal entry: {pump_time}
"
            f"• BullX.io optimal entry: {bull_time}
"
            "Ready to launch/trade when ready."
        )
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Launch analysis error for {user_id}: {e}")
        await update.message.reply_text("❌ Analysis failed. Please try again later.")

# --- ANALYSIS HELPERS ---
import httpx

async def analyze_pumpfun_optimal(mint_address: str) -> str:
    """
    Fetch upcoming launch info from Pump.fun public API and compute entry window.
    """
    try:
        async with httpx.AsyncClient() as client_api:
            # Example Pump.fun API endpoint for upcoming launches
            resp = await client_api.get(f"https://api.pump.fun/v1/launches/{mint_address}")
            data = resp.json()
            # Assume data contains 'launch_time' in ISO format
            launch_time = datetime.fromisoformat(data['launch_time'])
            # Recommend entry 30 seconds after launch to avoid MEV
            optimal = launch_time + timedelta(seconds=30)
            return optimal.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        return "Unable to fetch Pump.fun analysis."

async def analyze_bullxio_optimal(mint_address: str) -> str:
    """
    Query BullX.io REST API for orderbook snapshot and suggest entry with minimal slippage.
    """
    try:
        async with httpx.AsyncClient() as client_api:
            # Example BullX API for orderbook
            resp = await client_api.get(f"https://api.bullxio.com/orderbook/{mint_address}")
            ob = resp.json()
            # Determine price depth at 1% slippage
            bids = ob['bids']  # list of [price, size]
            cum_size = 0
            for price, size in bids:
                cum_size += size
                if cum_size >= ob['total_depth'] * 0.01:
                    return f"Enter at {price} to limit slippage ~1%"
            return "Enter at market with caution"
    except Exception:
        return "Unable to fetch BullX.io analysis."

async def snipe(update: Update, context: ContextTypes.DEFAULT_TYPE):(update: Update, context: ContextTypes.DEFAULT_TYPE):(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /snipe <symbol>")
        return
    symbol = context.args[0]
    await update.message.reply_text(f"⚡ Sniping token {symbol} (coming soon)")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /sell <symbol>")
        return
    symbol = context.args[0]
    await update.message.reply_text(f"💸 Selling token {symbol} (coming soon)")

# === MAIN ENTRY ===
from telegram.ext import CommandHandler

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    for cmd, handler in [
        ("start", start), ("help", help_command), ("register", register),
        ("wallets", wallets), ("deposit", deposit), ("balance", balance),
        ("history", history), ("status", status), ("launch", launch),
        ("snipe", snipe), ("sell", sell)
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    app.bot.set_my_commands([
        BotCommand("start", "Welcome message"), BotCommand("help", "List commands"),
        BotCommand("register", "Register your public key"), BotCommand("wallets", "Show your address"),
        BotCommand("deposit", "Get QR code to deposit"), BotCommand("balance", "Check your SOL"),
        BotCommand("history", "View recent txs"), BotCommand("status", "Wallet+balance summary"),
        BotCommand("launch", "Launch token (stub)"), BotCommand("snipe", "Snipe token (stub)"),
        BotCommand("sell", "Sell token (stub)")
    ])
    logger.info("🚀 Bot started: full command set enabled")
    app.run_polling()

if __name__ == '__main__':
    main()
