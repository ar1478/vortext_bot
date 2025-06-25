# vortex_bot.py — Ultimate Telegram Meme Coin Trading Bot
import os, json, logging, httpx
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from telegram import Update, BotCommand
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, ConversationHandler)
from solana.rpc.async_api import AsyncClient

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DATA_FILE = "user_data.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
rpc_client = AsyncClient(SOLANA_RPC_URL)

REGISTER = 1
def load_data():
    return json.loads(open(DATA_FILE).read()) if os.path.exists(DATA_FILE) else {}
def save_data(d):
    open(DATA_FILE, 'w').write(json.dumps(d))

# --- Handlers ---
async def start(update, ctx):
    await update.message.reply_text("🚀 Welcome! Use /register to link your wallet, then /help.")

async def help_command(update, ctx):
    cmds = [("register","Link Solana wallet"),("wallets","Show wallet"),
            ("balance","SOL balance"),("history","Recent txs"),
            ("status","Wallet summary"),("scan","Scan 10× candidates"),
            ("topgainers","24h top gainers"),("price","Get token price"),
            ("launch","Pick best launch coin"),("snipe","Timing to enter"),
            ("sell","Best exit info"),("set_slippage","Set slippage %"),
            ("set_stoploss","Set stop-loss %")]
    text = "Available commands:\n" + "\n".join(f"/{c} — {d}" for c, d in cmds)
    await update.message.reply_text(text)

# Register
async def register_start(update, ctx):
    await update.message.reply_text("Send your Solana public key:")
    return REGISTER

async def register_receive(update, ctx):
    key = update.message.text.strip()
    try: Pubkey.from_string(key)
    except: return await update.message.reply_text("❌ Invalid key.")
    data = load_data(); uid = str(update.effective_user.id)
    data[uid] = {"wallet":key,"slippage":1.0,"stoploss":5.0}
    save_data(data)
    return await update.message.reply_text(f"✅ Wallet `{key}` linked.", parse_mode="Markdown")

async def register_cancel(update, ctx):
    await update.message.reply_text("Registration canceled.")
    return ConversationHandler.END

# Wallet Info
async def wallets(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    await update.message.reply_text(f"Wallet: `{data['wallet']}`" if data else "No wallet linked.", parse_mode="Markdown")

async def balance(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data: return await update.message.reply_text("Link first: /register")
    bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
    await update.message.reply_text(f"💰 SOL: {bal.value/1e9:.6f}")

async def history(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data: return await update.message.reply_text("Link first: /register")
    sigs = (await rpc_client.get_signatures_for_address(Pubkey.from_string(data['wallet']), limit=5)).value
    txt = "Recent TXs:\n" + "\n".join(e.signature for e in sigs)
    await update.message.reply_text(txt)

async def status(update, ctx):
    data = load_data().get(str(update.effective_user.id))
    if not data: return await update.message.reply_text("Link first: /register")
    bal = await rpc_client.get_balance(Pubkey.from_string(data['wallet']))
    await update.message.reply_text(f"Wallet: `{data['wallet']}`\nSOL: {bal.value/1e9:.6f} SOL", parse_mode="Markdown")

# Market Tools
async def topgainers(update, ctx):
    async with httpx.AsyncClient() as client:
        d = (await client.get(
            "https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=priceChange.h24&order=desc&limit=5"
        )).json().get("tokens",[])
    if not d: return await update.message.reply_text("No top gainers.")
    text = "📈 Top gainers (24h):\n" + "\n".join(f"{t['symbol']}: {t['priceChange']['h24']}%" for t in d)
    await update.message.reply_text(text)

async def price(update, ctx):
    if not ctx.args: return await update.message.reply_text("Usage: /price <mint>")
    m = ctx.args[0]
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{m}").json().get("tokens",[])
    if not res: return await update.message.reply_text("Token not found.")
    t = res[0]; await update.message.reply_text(f"{t['symbol']}: ${t['priceUsd']}")

async def scan(update, ctx):
    arr = await fetch_filter_gain()
    if not arr: return await update.message.reply_text("No strong 10× candidates.")
    text = "🔍 10× scan results:\n"
    for t in arr: text += f"{t['symbol']}: {t['priceChange']['h1']}% | Vol: ${t['volume']['h24']}\n"
    await update.message.reply_text(text)

# Core Launch/Snipe/Sell
async def launch(update, ctx):
    args = ctx.args
    if not args:
        # scan mode
        await update.message.reply_text("🔍 Scanning top 10× candidates…")
        tokens = await fetch_filter_gain(limit=50)
        if not tokens:
            return await update.message.reply_text("❌ No strong candidates right now.")
        t = tokens[0]
        return await update.message.reply_text(
            f"🚀 Top candidate:\n"
            f"• {t['symbol']} @ ${t['priceUsd']}\n"
            f"• 1h: {t['priceChange']['h1']}%, 24h: {t['priceChange']['h24']}%\n"
            f"• Mint: `{t['address']}`"
        , parse_mode="Markdown")
    # deep-dive mode
    symbol, mint = args[0].upper(), args[1]
    await update.message.reply_text(f"🔍 Analyzing {symbol} ({mint})…")
    # fetch from DEX Screener
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
        arr = resp.json().get("tokens", [])
    if not arr:
        return await update.message.reply_text("❌ Token not found on DEX Screener.")
    tok = arr[0]
    p1h, p24h, vol = tok['priceChange']['h1'], tok['priceChange']['h24'], tok['volume']['h24']
    pump_time = await analyze_pumpfun_optimal(mint)
    bull_price = await analyze_bullxio_optimal(mint)
    await update.message.reply_text(
        f"🔎 *{symbol}* Analysis:\n"
        f"• Price: ${tok['priceUsd']}\n"
        f"• 1h Δ: {p1h}%, 24h Δ: {p24h}%\n"
        f"• Vol(24h): ${vol}\n\n"
        f"⏰ Pump.fun entry: `{pump_time}`\n"
        f"💲 BullX.io target: `{bull_price}`\n"
    , parse_mode="Markdown")


async def snipe(update, ctx):
    if not ctx.args: return await update.message.reply_text("Usage: /snipe <mint>")
    mint = ctx.args[0]
    ptime = await analyze_pumpfun_optimal(mint)
    if ptime!="N/A":
        et = datetime.utcnow() + timedelta(minutes=5)
        return await update.message.reply_text(f"⏰ Enter ~{et.strftime('%H:%M')} UTC (Pump.fun)")
    bp = await analyze_bullxio_optimal(mint)
    return await update.message.reply_text(f"📌 BullX.io target: {bp}")

async def sell(update, ctx):
    if not ctx.args: return await update.message.reply_text("Usage: /sell <mint>")
    await update.message.reply_text("💸 Sell on DEX where liquidity is highest: pump.fun or bullx.io")

# Risk Settings
async def set_slippage(update, ctx):
    if not ctx.args: return await update.message.reply_text("Usage: /set_slippage <percent>")
    try:
        val = float(ctx.args[0]); data = load_data()
        data[str(update.effective_user.id)]['slippage']=val; save_data(data)
        await update.message.reply_text(f"✅ Slippage set to {val}%")
    except: await update.message.reply_text("Invalid number.")

async def set_stoploss(update, ctx):
    if not ctx.args: return await update.message.reply_text("Usage: /set_stoploss <percent>")
    try:
        val = float(ctx.args[0]); data = load_data()
        data[str(update.effective_user.id)]['stoploss']=val; save_data(data)
        await update.message.reply_text(f"✅ Stop-loss set to {val}%")
    except: await update.message.reply_text("Invalid number.")

# Helper & API
async def fetch_filter_gain():
    async with httpx.AsyncClient() as client:
        tokens = (await client.get(
            "https://api.dexscreener.com/latest/dex/tokens?chainIds=solana&sort=volume.h24&order=desc&limit=50"
        )).json().get("tokens",[])
    filtered = [t for t in tokens if t['priceChange']['h1']>10 and t['volume']['h24']>100000]
    return sorted(filtered, key=lambda t: t['priceChange']['h1']*t['volume']['h24'], reverse=True)

async def analyze_pumpfun_optimal(m):
    try:
        j = await (await httpx.AsyncClient().get(f"https://api.pump.fun/v1/launches/{m}")).json()
        lt = datetime.fromisoformat(j['launch_time'].replace("Z","+00:00"))
        return lt.strftime("%H:%M UTC")
    except: return "N/A"

async def analyze_bullxio_optimal(m):
    try:
        j = await (await httpx.AsyncClient().get(f"https://api.bullx.io/orderbook/{m}")).json()
        bids=j.get('bids',[]); total=j.get('total_depth',0)
        s=0
        for pr,sz in bids:
            s+=sz
            if s>=total*0.01: return f"${pr:.6f}"
        return "market"
    except: return "N/A"

# Main
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('register',register_start)],
        states={REGISTER:[MessageHandler(filters.TEXT&~filters.COMMAND,register_receive)]},
        fallbacks=[CommandHandler('cancel',register_cancel)])
    for h in [CommandHandler('start',start),CommandHandler('help',help_command),
              conv,CommandHandler('wallets',wallets),CommandHandler('balance',balance),
              CommandHandler('history',history),CommandHandler('status',status),
              CommandHandler('scan',scan),CommandHandler('topgainers',topgainers),
              CommandHandler('price',price),CommandHandler('launch',launch),
              CommandHandler('snipe',snipe),CommandHandler('sell',sell),
              CommandHandler('set_slippage',set_slippage),CommandHandler('set_stoploss',set_stoploss)]:
        app.add_handler(h)
    app.bot.set_my_commands([BotCommand(c,d) for c,d in [
        ("start","Welcome"),("help","Commands"),("register","Link wallet"),
        ("wallets","Show wallet"),("balance","SOL balance"),("history","Recent txs"),
        ("status","Wallet summary"),("scan","Scan 10× tokens"),("topgainers","24h gainers"),
        ("price","Token price"),("launch","Best launch coin"),("snipe","Entry advice"),
        ("sell","Exit advice"),("set_slippage","Slippage %"),("set_stoploss","Stop-loss %")]])
    logger.info("🚀 Bot online")
    app.run_polling()

if __name__=="__main__":
    main()
