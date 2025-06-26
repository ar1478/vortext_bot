# vortex_bot.py — Enhanced Telegram Meme Coin Trading Bot
import os, json, logging, httpx, re, asyncio
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, ConversationHandler, CallbackQueryHandler)
from telegram.error import Conflict
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"
WATCHLIST_FILE = "watchlist.json"
DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# RPC Client
rpc_client = AsyncClient(SOLANA_RPC_URL, commitment=Confirmed)
REGISTER = 1
# === USER STORAGE & SETTINGS ===
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        return {}
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
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Watchlist load error: {e}")
        return {}

def save_watchlist(watchlist):
    try:
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(watchlist, f, indent=2)
    except Exception as e:
        logger.error(f"Watchlist save error: {e}")

# === STATES ===
REGISTER = 1

# === HELPER FUNCTION FOR API CALLS ===
async def fetch_tokens(client, url):
    """Fetch token data from DexScreener API with error handling."""
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        return data.get("pairs", []) or data.get("tokens", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching tokens from {url}: {e}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON response from {url}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching tokens from {url}: {e}")
        return []

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message for the bot."""
    await update.message.reply_text(
        "🚀 Welcome to UltimateTraderBot! Use /register to link your wallet and /help for all features."
    )

async def help_command(update, context):
    """Display all available commands."""
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
        ("set_stoploss", "Set stop-loss %"),
        ("watch", "Add token to watchlist"),
        ("watchlist", "View watchlist")
    ]
    text = "Available commands:\n" + "\n".join(f"/{c} — {d}" for c, d in cmds)
    await update.message.reply_text(text)

# Registration Commands
async def register_start(update, ctx):
    """Start the wallet registration process."""
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_register")]]
    await update.message.reply_text(
        "🔑 Send your Solana public key to link:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REGISTER

async def register_receive(update, ctx):
    """Receive and validate the Solana public key."""
    key = update.message.text.strip()
    try:
        Pubkey.from_string(key)
        if len(key) < 32 or not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', key):
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Invalid Solana address. Try again.")
        return REGISTER
    data = load_data()
    uid = str(update.effective_user.id)
    data[uid] = {"wallet": key, "slippage": 1.0, "stoploss": 5.0}
    save_data(data)
    name = update.effective_user.first_name or uid
    await update.message.reply_text(f"✅ {name}, wallet `{key}` linked!", parse_mode="Markdown")
    return ConversationHandler.END

async def register_cancel(update, ctx):
    """Cancel the registration process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Registration canceled.")
    return ConversationHandler.END

# Wallet Info Commands
async def wallets(update, ctx):
    """Show the linked wallet address."""
    data = load_data().get(str(update.effective_user.id))
    if data:
        keyboard = [[InlineKeyboardButton("View on Solscan", url=f"https://solscan.io/account/{data['wallet']}")]]
        await update.message.reply_text(
            f"👛 Wallet: `{data['wallet']}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("No wallet linked. Use /register.")

async def balance(update, ctx):
    """Check the SOL balance of the linked wallet."""
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    try:
        bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
        sol = bal.value / 1e9
        await update.message.reply_text(f"💰 SOL: {sol:.6f}")
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text("⚠️ Error fetching balance. Try again later.")

async def portfolio(update, ctx):
    """Show SPL token balances in the linked wallet."""
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    try:
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
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        await update.message.reply_text("⚠️ Error fetching portfolio. Try again later.")

async def history(update, ctx):
    """Show recent transactions for the linked wallet."""
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    try:
        wallet = Pubkey.from_string(data['wallet'])
        signatures = await rpc_client.get_signatures_for_address(wallet, limit=5)
        if not signatures.value:
            await update.message.reply_text("No recent transactions.")
            return
        reply = "Recent Transactions:\n"
        for sig in signatures.value:
            reply += f"- {sig.signature} (slot {sig.slot})\n"
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"History error: {e}")
        await update.message.reply_text("⚠️ Error fetching transactions. Try again later.")

async def status(update, ctx):
    """Show a summary of wallet status."""
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    try:
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
    except Exception as e:
        logger.error(f"Status error: {e}")
        await update.message.reply_text("⚠️ Error fetching status. Try again later.")

# Market Analysis Commands
async def scan(update, ctx):
    """Scan for potential 10x tokens based on volume and price change."""
    args = ctx.args
    min_volume = 100000
    min_change = 20
    for arg in args:
        if arg.startswith("min_volume="):
            try:
                min_volume = float(arg.split("=")[1])
            except ValueError:
                await update.message.reply_text("Invalid min_volume value.")
                return
        elif arg.startswith("min_change="):
            try:
                min_change = float(arg.split("=")[1])
            except ValueError:
                await update.message.reply_text("Invalid min_change value.")
                return
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/dex/search/pairs?q=solana&sort=volume.h24&order=desc&limit=50"
        tokens = await fetch_tokens(client, url)
        candidates = [
            t for t in tokens
            if t.get('priceChange', {}).get('h1', 0) > min_change and t.get('volume', {}).get('h24', 0) > min_volume
        ]
        if not candidates:
            await update.message.reply_text("No high-potential tokens found. Try adjusting filters or check later.")
            return
        reply = "🔍 Potential 10x Tokens:\n"
        for t in candidates[:5]:
            reply += (
                f"\n{t.get('baseToken', {}).get('symbol', 'N/A')} — ${t.get('priceUsd', 'N/A')}\n"
                f"1h: {t.get('priceChange', {}).get('h1', 'N/A')}%, 24h: {t.get('priceChange', {}).get('h24', 'N/A')}%\n"
                f"https://pump.fun/{t.get('baseToken', {}).get('address', 'N/A')}"
            )
        await update.message.reply_text(reply)

async def topgainers(update, ctx):
    """Show top gaining tokens over a specified timeframe."""
    timeframe = "h24"
    if ctx.args and ctx.args[0].startswith("timeframe="):
        timeframe = ctx.args[0].split("=")[1]
        if timeframe not in ["h1", "h6", "h24"]:
            return await update.message.reply_text("Invalid timeframe. Use h1, h6, or h24.")
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/dex/search/pairs?q=solana&sort=priceChange.{timeframe}&order=desc&limit=10"
        tokens = await fetch_tokens(client, url)
        if not tokens:
            await update.message.reply_text("No top gainers available right now. Try again later.")
            return
        tokens.sort(key=lambda x: x.get('priceChange', {}).get(timeframe, 0), reverse=True)
        reply = f"🏆 Top Gainers ({timeframe}):\n"
        for t in tokens[:5]:
            reply += (
                f"\n{t.get('baseToken', {}).get('symbol', 'N/A')} — ${t.get('priceUsd', 'N/A')}\n"
                f"{timeframe}: {t.get('priceChange', {}).get(timeframe, 'N/A')}%\n"
                f"https://pump.fun/{t.get('baseToken', {}).get('address', 'N/A')}"
            )
        await update.message.reply_text(reply)

async def price(update, ctx):
    """Get the current price and details of a specific token."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /price <token_address>, e.g., /price So11111111111111111111111111111111111111112")
    mint = ctx.args[0]
    try:
        Pubkey.from_string(mint)
    except:
        return await update.message.reply_text("Invalid token address.")
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/dex/tokens/{mint}"
        tokens = await fetch_tokens(client, url)
        if not tokens:
            await update.message.reply_text("Token not found or API error. Try again later.")
            return
        token = tokens[0]
        liquidity = token.get('liquidity', {}).get('usd', 'N/A')
        market_cap = token.get('fdv', 'N/A')
        keyboard = [
            [InlineKeyboardButton("Chart", url=f"https://dexscreener.com/solana/{mint}")]]
        await update.message.reply_text(
            f"💰 {token.get('baseToken', {}).get('symbol', 'N/A')} — ${token.get('priceUsd', 'N/A')}\n"
            f"24h Change: {token.get('priceChange', {}).get('h24', 'N/A')}%\n"
            f"Liquidity: ${liquidity}\n"
            f"Market Cap: ${market_cap}\n",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def launch(update, ctx):
    """Analyze a token's launch details."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /launch <token_address>, e.g., /launch So11111111111111111111111111111111111111112")
    mint = ctx.args[0]
    try:
        Pubkey.from_string(mint)
    except:
        return await update.message.reply_text("Invalid token address.")
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/dex/tokens/{mint}"
        tokens = await fetch_tokens(client, url)
        if not tokens:
            await update.message.reply_text("Token not found or API error. Try again later.")
            return
        token = tokens[0]
        liquidity = token.get('liquidity', {}).get('usd', 'N/A')
        market_cap = token.get('fdv', 'N/A')
        created_at = token.get('pairCreatedAt', 'N/A')
        keyboard = [
            [InlineKeyboardButton("Chart", url=f"https://dexscreener.com/solana/{mint}")]]
        await update.message.reply_text(
            f"🚀 {token.get('baseToken', {}).get('symbol', 'N/A')} Launch Analysis:\n"
            f"Price: ${token.get('priceUsd', 'N/A')}\n"
            f"Volume (24h): ${token.get('volume', {}).get('h24', 'N/A')}\n"
            f"1h Change: {token.get('priceChange', {}).get('h1', 'N/A')}%\n"
            f"Liquidity: ${liquidity}\n"
            f"Market Cap: ${market_cap}\n"
            f"Created: {datetime.fromtimestamp(created_at/1000).strftime('%Y-%m-%d %H:%M UTC') if created_at != 'N/A' else 'N/A'}\n",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def snipe(update, ctx):
    """Identify the best tokens to snipe in the next hour."""
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/dex/search/pairs?q=solana&sort=volume.h24&order=desc&limit=50"
        tokens = await fetch_tokens(client, url)
        candidates = [
            t for t in tokens
            if t.get('priceChange', {}).get('h1', 0) > 15 and t.get('volume', {}).get('h24', 0) > 150000
        ]
        if not candidates:
            await update.message.reply_text("No sniper targets found right now. Check later or try /scan with different filters.")
            return
        now = datetime.utcnow()
        reply = "🎯 Best sniper targets (next hour):\n"
        for t in candidates[:5]:
            symbol = t.get('baseToken', {}).get('symbol', 'N/A')
            price = t.get('priceUsd', 'N/A')
            vol = t.get('volume', {}).get('h24', 'N/A')
            mint = t.get('baseToken', {}).get('address', 'N/A')
            entry = now + timedelta(minutes=5)
            reply += (
                f"\n{symbol} — ${price}, Vol: ${vol}\n"
                f"Entry: {entry.strftime('%H:%M:%S UTC')}\n"
                f"https://pump.fun/{mint}"
            )
        await update.message.reply_text(reply)

async def sell(update, ctx):
    """Provide selling strategy insights."""
    data = load_data().get(str(update.effective_user.id))
    if not data:
        return await update.message.reply_text("Link with /register.")
    try:
        bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
        sol = bal.value / 1e9
        if sol < 0.01:
            return await update.message.reply_text("Low SOL balance. Add funds to trade.")
        await update.message.reply_text(
            f"💸 Sell Strategy:\n"
            f"Slippage: {data['slippage']}%\n"
            f"Stop-loss: {data['stoploss']}%\n"
            f"Balance: {sol:.6f} SOL\n"
            f"Consider selling if price drops below stop-loss or market conditions change."
        )
    except Exception as e:
        logger.error(f"Sell error: {e}")
        await update.message.reply_text("⚠️ Error fetching sell data. Try again later.")

async def set_slippage(update, ctx):
    """Set the maximum slippage percentage."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_slippage <percentage>, e.g., /set_slippage 2.5")
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
    """Set the stop-loss percentage."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_stoploss <percentage>, e.g., /set_stoploss 10")
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

async def watch_token(update, ctx):
    """Add a token to the user's watchlist."""
    if not ctx.args:
        return await update.message.reply_text("Usage: /watch <token_address>")
    mint = ctx.args[0]
    try:
        Pubkey.from_string(mint)
    except:
        return await update.message.reply_text("Invalid token address.")
    watchlist = load_watchlist()
    uid = str(update.effective_user.id)
    watchlist.setdefault(uid, [])
    if mint in watchlist[uid]:
        await update.message.reply_text("Token already in your watchlist.")
        return
    watchlist[uid].append(mint)
    save_watchlist(watchlist)
    await update.message.reply_text(f"✅ Token added to watchlist: `{mint}`", parse_mode="Markdown")

async def show_watchlist(update, ctx):
    """Display the user's watchlist."""
    watchlist = load_watchlist()
    uid = str(update.effective_user.id)
    tokens = watchlist.get(uid, [])
    if not tokens:
        await update.message.reply_text("Your watchlist is empty. Add tokens with /watch.")
        return
    reply = "👀 Your Watchlist:\n"
    for i, mint in enumerate(tokens, 1):
        reply += f"{i}. `{mint}`\n"
    await update.message.reply_text(reply, parse_mode="Markdown")

async def check_watchlist(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check watchlist tokens for price changes."""
    logger.info("🔔 Running watchlist check...")
    watchlist = load_watchlist()
    async with httpx.AsyncClient() as client:
        for uid, tokens in watchlist.items():
            for mint in tokens:
                try:
                    url = f"{DEX_SCREENER_URL}/dex/tokens/{mint}"
                    tokens_data = await fetch_tokens(client, url)
                    if not tokens_data:
                        continue
                    token = tokens_data[0]
                    price_change = token.get('priceChange', {}).get('h1', 0)
                    if abs(price_change) > 10:
                        await context.bot.send_message(
                            chat_id=uid,
                            text=(
                                f"🔔 Watchlist Alert: {token.get('baseToken', {}).get('symbol', 'N/A')}\n"
                                f"Price: ${token.get('priceUsd', 'N/A')}\n"
                                f"1h Change: {price_change}%"
                            )
                        )
                except Exception as e:
                    logger.error(f"Watchlist check error for {mint}: {e}")

# === BUTTON HANDLER ===
async def button_handler(update, ctx):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel_register":
        await query.edit_message_text("❌ Registration canceled.")

# === POST-INIT FUNCTION ===
async def post_init(application):
    """Initialize periodic tasks after bot startup."""
    job_queue = application.job_queue
    job_queue.run_repeating(check_watchlist, interval=300, first=10)  # Check every 5 minutes

# === MAIN FUNCTION ===
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Registration convo
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={REGISTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, register_receive),
            CallbackQueryHandler(register_cancel, pattern="^cancel_register$")
        ]},
        fallbacks=[CommandHandler('cancel', register_cancel)]
    )

    # Register all commands
    handlers = [
        CommandHandler('start', start),
        CommandHandler('help', help_command),
        conv_handler,
        CommandHandler('wallets', wallets),
        CommandHandler('balance', balance),
        CommandHandler('history', history),
        CommandHandler('status', status),
        CommandHandler('scan', scan),
        CommandHandler('topgainers', topgainers),
        CommandHandler('price', price),
        CommandHandler('launch', analyze_launch),
        CommandHandler('snipe', snipe),
        CommandHandler('sell', sell),
        CommandHandler('watch', watch_token),
        CommandHandler('unwatch', unwatch_token),
        CommandHandler('watchlist', show_watchlist),
        CommandHandler('set_slippage', set_slippage),
        CommandHandler('set_stoploss', set_stoploss),
        CommandHandler('alert', set_alert)
    ]

    for h in handlers:
        app.add_handler(h)

    # Button callback
    app.add_handler(CallbackQueryHandler(button_handler))

    # Set bot commands
    cmds = [
        ("start","Start bot"),("help","List commands"),("register","Link wallet"),
        ("wallets","Show wallet"),("balance","SOL balance"),("history","Recent txs"),
        ("status","Wallet summary"),("scan","Scan 10× tokens"),("topgainers","24h gainers"),
        ("price","Token price"),("launch","Analyze token"),("snipe","Entry timing"),
        ("sell","Exit analysis"),("watch","Add watch"),("unwatch","Remove watch"),
        ("watchlist","View watchlist"),("set_slippage","Set slippage"),
        ("set_stoploss","Set stop-loss"),("alert","Price alert")
    ]
    app.post_init(lambda app: app.bot.set_my_commands([BotCommand(c,d) for c,d in cmds]))

    # Jobs
    if app.job_queue:
        app.job_queue.run_repeating(check_watchlist, interval=300, first=10)

    logger.info("🚀 Vortex Bot running")
    app.run_polling()

if __name__ == '__main__':
    main()
