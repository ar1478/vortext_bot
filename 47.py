# vortex_bot.py — Enhanced Telegram Meme Coin Trading Bot
import os
import json
import logging
import httpx
import re
import asyncio
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.error import Conflict
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"
WATCHLIST_FILE = "watchlist.json"
DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Solana RPC Client ---
rpc_client = AsyncClient(SOLANA_RPC_URL, commitment=Confirmed)

# --- Conversation States ---
REGISTER = 1

# --- Data Management Functions ---
def load_data():
    """Load user data from JSON file."""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Data load error: {e}")
        return {}

def save_data(data):
    """Save user data to JSON file."""
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Data save error: {e}")

def load_watchlist():
    """Load watchlist data from JSON file."""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Watchlist load error: {e}")
        return {}

def save_watchlist(watchlist):
    """Save watchlist data to JSON file."""
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(watchlist, f, indent=2)
    except Exception as e:
        logger.error(f"Watchlist save error: {e}")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "🚀 Welcome to Vortex Bot - Ultimate Meme Coin Trading Assistant!\n\n"
        "• Use /register to link your wallet\n"
        "• /help for command list\n"
        "• /watch to monitor tokens\n\n"
        "⚡ Real-time alerts | 📈 Market analysis | ⏱️ Trade timing"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command."""
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
        ("alert", "Set price alert"),
    ]
    text = "📋 **Available Commands:**\n" + "\n".join(
        f"/{cmd} — {desc}" for cmd, desc in cmds
    )
    await update.message.reply_text(text, parse_mode="HTML")

# --- Wallet Registration Handlers ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the wallet registration process."""
    await update.message.reply_text(
        "🔑 Please send your Solana public key:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel_register")]
        ])
    )
    return REGISTER

async def register_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate the Solana public key."""
    key = update.message.text.strip()
    try:
        pubkey = Pubkey.from_string(key)
        if len(key) < 32 or not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", key):
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
    """Cancel the wallet registration process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Registration canceled.")
    return ConversationHandler.END

# --- Wallet Operation Handlers ---
async def wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the user's linked wallet."""
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
    """Check the SOL balance of the linked wallet."""
    data = load_data().get(str(update.effective_user.id))
    if not data or "wallet" not in data:
        await update.message.reply_text("❌ Link wallet first: /register")
        return

    try:
        bal = await rpc_client.get_balance(Pubkey.from_string(data["wallet"]))
        sol = bal.value / 1e9
        await update.message.reply_text(f"💰 SOL Balance: **{sol:.4f}**", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text("⚠️ Error fetching balance. Try again later.")

# --- Market Tool Handlers ---
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for high-potential tokens."""
    await update.message.reply_text("🔍 Scanning for high-potential tokens...")

    try:
        # Simulated token data (replace with real API call if available)
        tokens = [
            {
                "symbol": "TOKEN1",
                "priceUsd": "0.000123",
                "priceChange": {"h1": "25.5", "h24": "300.2"},
                "liquidity": {"usd": "25000"},
                "address": "7vF5...bC9d"
            },
            {
                "symbol": "TOKEN2",
                "priceUsd": "0.000456",
                "priceChange": {"h1": "18.2", "h24": "250.7"},
                "liquidity": {"usd": "18000"},
                "address": "8gH3...dE2f"
            }
        ]

        if not tokens:
            await update.message.reply_text("❌ No strong candidates found. Try again later.")
            return

        response = "🔥 **Top Potential Tokens:**\n\n"
        for i, token in enumerate(tokens[:5], 1):
            response += (
                f"{i}. **{token['symbol']}**\n"
                f"   💰 Price: ${token['priceUsd']}\n"
                f"   📈 1h: **{token['priceChange']['h1']}%** | "
                f"24h: {token['priceChange']['h24']}%\n"
                f"   💧 Liquidity: ${float(token['liquidity']['usd']):,.0f}\n"
                f"   🪙 Mint: <code>{token['address']}</code>\n\n"
            )

        await update.message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text("⚠️ Market scan failed. Try again later.")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the price and details of a specific token."""
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /price <token_address>")
        return

    mint = context.args[0]
    try:
        # Simulated token data
        token_data = {
            "symbol": "EXAMPLE",
            "priceUsd": "0.000123",
            "volume": {"h24": "150000"},
            "priceChange": {"h1": "25.5", "h24": "300.2"},
            "liquidity": {"usd": "50000"},
            "dexId": "raydium",
            "address": mint
        }

        response = (
            f"📊 **{token_data['symbol']} Analysis**\n\n"
            f"💰 Price: **${token_data['priceUsd']}**\n"
            f"🔄 24h Vol: **${float(token_data['volume']['h24']):,.0f}**\n"
            f"📈 1h: **{token_data['priceChange']['h1']}%** | "
            f"24h: **{token_data['priceChange']['h24']}%**\n"
            f"💧 Liquidity: **${float(token_data['liquidity']['usd']):,.0f}**\n"
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
        )
    except Exception as e:
        logger.error(f"Price error: {e}")
        await update.message.reply_text("⚠️ Error fetching token data. Try again later.")

# --- Watchlist Handlers ---
async def watch_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a token to the user's watchlist."""
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
    """Display the user's watchlist."""
    watchlist = load_watchlist()
    uid = str(update.effective_user.id)
    tokens = watchlist.get(uid, [])

    if not tokens:
        await update.message.reply_text("ℹ️ Your watchlist is empty. Add tokens with /watch")
        return

    response = "👀 **Your Watchlist:**\n\n"
    for i, mint in enumerate(tokens, 1):
        response += f"{i}. <code>{mint}</code>\n"

    await update.message.reply_text(response, parse_mode="HTML")

# --- Core Trading Handlers ---
async def analyze_launch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze a new token launch or scan for recent launches."""
    if not context.args:
        await update.message.reply_text("🔍 Scanning new launches...")

        # Simulated token data
        token = {
            "symbol": "NEWLIST",
            "priceUsd": "0.000456",
            "liquidity": {"usd": "75000"},
            "address": "7vF5...bC9d",
            "listing_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        }

        response = (
            f"🚀 **Top New Launch:** {token['symbol']}\n\n"
            f"💰 Price: ${token['priceUsd']}\n"
            f"⏰ Listed: {token['listing_time']}\n"
            f"💧 Liquidity: ${float(token['liquidity']['usd']):,.0f}\n"
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
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Deep analysis mode
    mint = context.args[0]
    await update.message.reply_text(f"🔍 Analyzing token: {mint[:6]}...")

    try:
        # Simulated analysis
        volatility = 28.7
        liquidity_depth = 18.3

        response = (
            f"🔬 **Deep Analysis:** EXAMPLE\n\n"
            f"📈 Volatility: **{volatility:.2f}%** (15min)\n"
            f"💧 Liquidity Depth: **{liquidity_depth:.2f}%** of market cap\n"
            f"👥 Holders: **1250**\n"
            f"🔄 5m Volume: **$42,500**\n\n"
            f"💡 *Recommendation: Strong potential*"
        )

        await update.message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Launch analysis error: {e}")
        await update.message.reply_text("⚠️ Analysis failed. Try again later.")

# --- Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("trade_"):
        mint = data.split("_")[1]
        await query.edit_message_text(f"🔄 Trading initiated for token: {mint[:6]}...")
    elif data.startswith("alert_"):
        mint = data.split("_")[1]
        await query.edit_message_text(
            f"🔔 Set alert for token:\n• Mint: <code>{mint}</code>\n"
            "• Send alert price (e.g., 0.0005)",
            parse_mode="HTML"
        )
    elif data == "cancel_register":
        await query.edit_message_text("❌ Registration canceled.")

# --- Background Tasks ---
async def check_watchlist(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check watchlist tokens (placeholder)."""
    logger.info("🔔 Running watchlist check...")
    # Add watchlist monitoring logic here

# --- Main Application ---
async def main():
    """Main entry point for the bot."""
    # Prevent multiple instances
    pid_file = "vortex_bot.pid"
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read())
            os.kill(pid, 0)  # Check if process exists
            logger.error("❌ Another instance is running. Exiting.")
            return
        except:
            pass  # Process doesn't exist

    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    try:
        # Validate token
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN is not set")
            return

        # Build application
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        if not app.bot:
            logger.error("Failed to initialize bot. Check TELEGRAM_TOKEN.")
            return

        # Define conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("register", register_start)],
            states={
                REGISTER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive),
                    CallbackQueryHandler(register_cancel, pattern="^cancel_register$")
                ]
            },
            fallbacks=[CommandHandler("cancel", register_cancel)]
        )

        # Register command handlers
        command_handlers = [
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            conv_handler,
            CommandHandler("wallets", wallets),
            CommandHandler("balance", balance),
            CommandHandler("scan", scan),
            CommandHandler("price", price),
            CommandHandler("watch", watch_token),
            CommandHandler("watchlist", show_watchlist),
            CommandHandler("launch", analyze_launch),
        ]

        for handler in command_handlers:
            app.add_handler(handler)

        # Add button handler
        app.add_handler(CallbackQueryHandler(button_handler))

        # Define bot commands
        commands = [
  BotCommand("start", "Start the bot"),
  BotCommand("help", "Show command list"),
  BotCommand("register", "Link Solana wallet"),
  BotCommand("wallets", "Show linked wallet"),
  BotCommand("balance", "Check SOL balance"),
  BotCommand("history", "Recent transactions"),
  BotCommand("status", "Wallet summary"),
  BotCommand("scan", "Scan potentials"),
  BotCommand("topgainers", "24h top gainers"),
  BotCommand("price", "Price check"),
  BotCommand("launch", "Analyze new token"),
  BotCommand("snipe", "Entry timing"),
  BotCommand("sell", "Exit strategy"),
  BotCommand("watch", "Add watch"),
  BotCommand("unwatch", "Remove watch"),
  BotCommand("watchlist", "View your watchlist"),
  BotCommand("set_slippage", "Set slippage %"),
  BotCommand("set_stoploss", "Set stop-loss %"),
  BotCommand("alert", "Set price alert"),
]


        # Post-initialization function with error handling
        async def post_init(application):
            """Set bot commands after initialization."""
            if application.bot is None:
                logger.error("application.bot is None, cannot set commands")
                return
            try:
                await application.bot.set_my_commands(commands)
                logger.info("✅ Bot commands registered")
            except Exception as e:
                logger.error(f"Failed to set bot commands: {e}")

        app.post_init(post_init)

        # Setup background tasks
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(
                check_watchlist,
                interval=300,  # 5 minutes
                first=10
            )

        logger.info("🚀 Vortex Bot is now running")
        await app.run_polling()

    except Conflict as e:
        logger.error(f"Conflict error: {e}")
        logger.error("Ensure only one instance is running")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        try:
            os.remove(pid_file)
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
