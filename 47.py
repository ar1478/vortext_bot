# vortex_bot.py — Enhanced Telegram Meme Coin Trading Bot
import os, json, logging, httpx, re, asyncio
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, ConversationHandler, CallbackQueryHandler)
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"
WATCHLIST_FILE = "watchlist.json"
DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("vortex_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
rpc_client = AsyncClient(SOLANA_RPC_URL, commitment=Confirmed)

REGISTER = 1
WATCH_TOKEN = 1

# --- Data Management ---
def load_data():
    try:
        return json.load(open(DATA_FILE)) if os.path.exists(DATA_FILE) else {}
    except Exception as e:
        logger.error(f"Data load error: {e}")
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Data save error: {e}")

def load_watchlist():
    try:
        return json.load(open(WATCHLIST_FILE)) if os.path.exists(WATCHLIST_FILE) else {}
    except Exception as e:
        logger.error(f"Watchlist load error: {e}")
        return {}

def save_watchlist(watchlist):
    try:
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(watchlist, f, indent=2)
    except Exception as e:
        logger.error(f"Watchlist save error: {e}")

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Welcome to Vortex Bot - Ultimate Meme Coin Trading Assistant!\n\n"
        "• Use /register to link your wallet\n"
        "• /help for command list\n"
        "• /watch to monitor tokens\n\n"
        "⚡ Real-time alerts | 📈 Market analysis | ⏱️ Trade timing"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmds = [
        ("register", "Link Solana wallet"),
        ("wallets", "Show wallet address"),
        ("balance", "Check SOL balance"),
        ("history", "Recent transactions"),
        ("watch", "Monitor token price"),
        ("unwatch", "Remove token from watchlist"),
        ("watchlist", "View your watchlist"),
        ("scan", "Scan 10× potential tokens"),
        ("topgainers", "24h top gainers"),
        ("price", "Get token price"),
        ("launch", "Analyze new token"),
        ("snipe", "Optimal entry timing"),
        ("sell", "Exit strategy analysis"),
        ("set_slippage", "Set slippage %"),
        ("set_stoploss", "Set stop-loss %"),
        ("alert", "Set price alert")
    ]
    text = "📋 <b>Available Commands:</b>\n" + "\n".join(
        f"/{cmd} — {desc}" for cmd, desc in cmds
    )
    await update.message.reply_text(text, parse_mode="HTML")

# --- Wallet Registration ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 Please send your Solana public key:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel_register")]
        ])
    )
    return REGISTER

async def register_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip()
    try:
        pubkey = Pubkey.from_string(key)
        if len(key) < 32 or not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', key):
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Invalid Solana address. Please try again.")
        return REGISTER
    
    data = load_data()
    uid = str(update.effective_user.id)
    data.setdefault(uid, {})
    data[uid]["wallet"] = key
    data[uid].setdefault("slippage", 1.0)
    data[uid].setdefault("stoploss", 5.0)
    save_data(data)
    
    await update.message.reply_text(
        f"✅ Wallet successfully linked:\n<code>{key}</code>",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def register_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Registration canceled.")
    return ConversationHandler.END

# --- Wallet Operations ---
async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data().get(str(update.effective_user.id))
    if not data or "wallet" not in data:
        await update.message.reply_text("❌ No wallet linked. Use /register first.")
        return
    
    keyboard = [
        [InlineKeyboardButton("View on Explorer", 
         url=f"https://solscan.io/account/{data['wallet']}")]
    ]
    await update.message.reply_text(
        f"👛 Your wallet:\n<code>{data['wallet']}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data().get(str(update.effective_user.id))
    if not data or "wallet" not in data:
        await update.message.reply_text("❌ Link wallet first: /register")
        return
    
    try:
        bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
        sol = bal.value / 1e9
        await update.message.reply_text(f"💰 SOL Balance: <b>{sol:.4f}</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text("⚠️ Error fetching balance. Try again later.")

# --- Market Tools ---
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning for high-potential tokens...")
    
    try:
        tokens = await fetch_filtered_tokens(
            min_volume=50000,
            min_liquidity=10000,
            min_hourly_change=15
        )
        
        if not tokens:
            await update.message.reply_text("❌ No strong candidates found. Try again later.")
            return
        
        response = "🔥 <b>Top Potential Tokens:</b>\n\n"
        for i, token in enumerate(tokens[:5], 1):
            response += (
                f"{i}. <b>{token['symbol']}</b>\n"
                f"   💰 Price: ${token['priceUsd']}\n"
                f"   📈 1h: <b>{token['priceChange']['h1']}%</b> | "
                f"24h: {token['priceChange']['h24']}%\n"
                f"   💧 Liquidity: ${token['liquidity']['usd']:,.0f}\n"
                f"   🪙 Mint: <code>{token['address']}</code>\n\n"
            )
        
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text("⚠️ Market scan failed. Try again later.")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /price <token_address>")
        return
    
    mint = context.args[0]
    try:
        token_data = await fetch_token_data(mint)
        if not token_data:
            await update.message.reply_text("❌ Token not found or no trading data.")
            return
        
        response = (
            f"📊 <b>{token_data['symbol']} Analysis</b>\n\n"
            f"💰 Price: <b>${token_data['priceUsd']}</b>\n"
            f"🔄 24h Vol: <b>${token_data['volume']['h24']:,.0f}</b>\n"
            f"📈 1h: <b>{token_data['priceChange']['h1']}%</b> | "
            f"24h: <b>{token_data['priceChange']['h24']}%</b>\n"
            f"💧 Liquidity: <b>${token_data['liquidity']['usd']:,.0f}</b>\n"
            f"🔗 Dex: {token_data['dexId']}\n"
            f"🪙 Mint: <code>{token_data['address']}</code>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}"),
                InlineKeyboardButton("💸 Trade", callback_data=f"trade_{mint}")
            ],
            [InlineKeyboardButton("🔔 Add Alert", callback_data=f"alert_{mint}")]
        ]
        
        await update.message.reply_text(
            response,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.error(f"Price error: {e}")
        await update.message.reply_text("⚠️ Error fetching token data. Try again later.")

# --- Watchlist Features ---
async def watch_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /watch <token_address>")
        return
    
    mint = context.args[0]
    try:
        Pubkey.from_string(mint)
    except:
        await update.message.reply_text("❌ Invalid token address.")
        return
    
    watchlist = load_watchlist()
    uid = str(update.effective_user.id)
    watchlist.setdefault(uid, [])
    
    if mint in watchlist[uid]:
        await update.message.reply_text("ℹ️ Token already in your watchlist.")
        return
    
    watchlist[uid].append(mint)
    save_watchlist(watchlist)
    await update.message.reply_text(f"✅ Token added to watchlist: <code>{mint}</code>", parse_mode="HTML")

async def show_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watchlist = load_watchlist()
    uid = str(update.effective_user.id)
    tokens = watchlist.get(uid, [])
    
    if not tokens:
        await update.message.reply_text("ℹ️ Your watchlist is empty. Add tokens with /watch")
        return
    
    response = "👀 <b>Your Watchlist:</b>\n\n"
    for i, mint in enumerate(tokens, 1):
        try:
            token_data = await fetch_token_data(mint)
            symbol = token_data['symbol'] if token_data else "Unknown"
            response += f"{i}. {symbol} - <code>{mint}</code>\n"
        except:
            response += f"{i}. <code>{mint}</code>\n"
    
    await update.message.reply_text(response, parse_mode="HTML")

# --- Core Trading Features ---
async def analyze_launch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 Scanning new launches...")
        tokens = await fetch_new_listings()
        
        if not tokens:
            await update.message.reply_text("❌ No new listings found.")
            return
        
        token = tokens[0]
        response = (
            f"🚀 <b>Top New Launch:</b> {token['symbol']}\n\n"
            f"💰 Price: ${token['priceUsd']}\n"
            f"⏰ Listed: {token['listing_time']}\n"
            f"💧 Liquidity: ${token['liquidity']['usd']:,.0f}\n"
            f"🪙 Mint: <code>{token['address']}</code>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{token['address']}"),
                InlineKeyboardButton("🚀 Snipe", callback_data=f"snipe_{token['address']}")
            ]
        ]
        
        await update.message.reply_text(
            response,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Deep analysis mode
    mint = context.args[0]
    await update.message.reply_text(f"🔍 Analyzing token: {mint[:6]}...")
    
    try:
        token_data = await fetch_token_data(mint)
        if not token_data:
            await update.message.reply_text("❌ Token data unavailable.")
            return
        
        volatility = await calculate_volatility(mint)
        liquidity_depth = await analyze_liquidity_depth(mint)
        
        response = (
            f"🔬 <b>Deep Analysis:</b> {token_data['symbol']}\n\n"
            f"📈 Volatility: <b>{volatility:.2f}%</b> (15min)\n"
            f"💧 Liquidity Depth: <b>{liquidity_depth:.2f}%</b> of market cap\n"
            f"👥 Holders: <b>{token_data.get('holders', 'N/A')}</b>\n"
            f"🔄 5m Volume: <b>${token_data['volume']['m5']:,.0f}</b>\n\n"
            f"💡 <i>Recommendation: {'Strong potential' if volatility > 20 and liquidity_depth > 15 else 'Caution advised'}</i>"
        )
        
        await update.message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Launch analysis error: {e}")
        await update.message.reply_text("⚠️ Analysis failed. Try again later.")

# --- Enhanced Utilities ---
async def fetch_filtered_tokens(
    min_volume=20000,
    min_liquidity=5000,
    min_hourly_change=10,
    max_age_hours=24
):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{DEX_SCREENER_URL}/tokens?chainId=solana")
            data = response.json()
        
        tokens = data.get("tokens", [])
        now = datetime.utcnow()
        
        filtered = []
        for token in tokens:
            try:
                # Calculate token age
                pair_created = datetime.fromtimestamp(token['pairCreatedAt'] / 1000)
                age_hours = (now - pair_created).total_seconds() / 3600
                
                if (token['volume']['h24'] >= min_volume and
                    token['liquidity']['usd'] >= min_liquidity and
                    token['priceChange']['h1'] >= min_hourly_change and
                    age_hours <= max_age_hours):
                    filtered.append(token)
            except KeyError:
                continue
        
        # Sort by potential score (volume * price change)
        filtered.sort(
            key=lambda x: x['volume']['h24'] * x['priceChange']['h1'],
            reverse=True
        )
        return filtered[:10]
    except Exception as e:
        logger.error(f"Token fetch error: {e}")
        return []

async def calculate_volatility(mint, period_minutes=15):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DEX_SCREENER_URL}/tokens/{mint}/history?range={period_minutes}m")
            data = response.json()
        
        prices = [float(entry["price"]) for entry in data["history"]]
        if len(prices) < 2:
            return 0.0
        
        min_price = min(prices)
        max_price = max(prices)
        return ((max_price - min_price) / min_price) * 100
    except Exception as e:
        logger.error(f"Volatility calc error: {e}")
        return 0.0

# --- Background Tasks ---
async def check_watchlist(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔔 Running watchlist check...")
    watchlist = load_watchlist()
    for uid, tokens in watchlist.items():
        for mint in tokens:
            try:
                token_data = await fetch_token_data(mint)
                if not token_data:
                    continue
                
                # Check for significant price movement
                price_change = token_data['priceChange']['m5']
                if abs(price_change) > 10:  > 10% change
                    alert_msg = (
                        f"🚨 Price Alert!\n"
                        f"{token_data['symbol']} changed {price_change:.2f}% in 5 minutes\n"
                        f"Current Price: ${token_data['priceUsd']}\n"
                        f"<code>{mint}</code>"
                    )
                    await context.bot.send_message(
                        chat_id=uid,
                        text=alert_msg,
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                logger.error(f"Watchlist check error for {mint}: {e}")

# --- Main Application ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Conversation handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            REGISTER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive),
                CallbackQueryHandler(register_cancel, pattern="^cancel_register$")
            ]
        },
        fallbacks=[CommandHandler('cancel', register_cancel)]
    )
    
    # Command handlers
    command_handlers = [
        CommandHandler('start', start),
        CommandHandler('help', help_command),
        conv_handler,
        CommandHandler('wallets', wallets),
        CommandHandler('balance', balance),
        CommandHandler('scan', scan),
        CommandHandler('price', price),
        CommandHandler('watch', watch_token),
        CommandHandler('watchlist', show_watchlist),
        CommandHandler('launch', analyze_launch),
        CommandHandler('topgainers', topgainers)
    ]
    
    for handler in command_handlers:
        app.add_handler(handler)
    
    # Set menu commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show command list"),
        BotCommand("register", "Link Solana wallet"),
        BotCommand("balance", "Check SOL balance"),
        BotCommand("scan", "Find potential tokens"),
        BotCommand("price", "Check token price"),
        BotCommand("launch", "Analyze new token"),
        BotCommand("watch", "Monitor token"),
        BotCommand("watchlist", "View your watchlist")
    ]
    app.bot.set_my_commands(commands)
    
    # Setup background tasks
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            check_watchlist,
            interval=300,  # 5 minutes
            first=10
        )
    
    logger.info("🚀 Vortex Bot is now running")
    app.run_polling()

if __name__ == "__main__":
    main()
