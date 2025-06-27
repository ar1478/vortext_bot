import os, json, logging, httpx, re, asyncio, hashlib, hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from solders.pubkey import Pubkey
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, ConversationHandler, CallbackQueryHandler)
from telegram.error import Conflict
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
import matplotlib.pyplot as plt
import io
import base64

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
JUPITER_API_URL = "https://quote-api.jup.ag/v6"
DATA_FILE = "user_data.json"
WATCHLIST_FILE = "watchlist.json"
ALERTS_FILE = "alerts.json"
TRADES_FILE = "trades.json"
DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex"

# Enhanced Data Structures
@dataclass
class User:
    wallet: str
    slippage: float = 1.0
    stoploss: float = 5.0
    risk_level: str = "medium"  # low, medium, high
    auto_sell: bool = False
    notification_settings: Dict = None
    trading_strategy: str = "conservative"  # conservative, aggressive, scalping
    max_trade_amount: float = 0.1  # SOL
    
    def __post_init__(self):
        if self.notification_settings is None:
            self.notification_settings = {
                "price_alerts": True,
                "portfolio_updates": True,
                "market_news": False,
                "whale_alerts": True
            }

@dataclass
class PriceAlert:
    token_address: str
    target_price: float
    condition: str  # "above", "below"
    created_at: datetime
    is_active: bool = True

@dataclass
class Trade:
    token_address: str
    action: str  # "buy", "sell"
    amount_sol: float
    price_usd: float
    timestamp: datetime
    profit_loss: Optional[float] = None

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# RPC Client
rpc_client = AsyncClient(SOLANA_RPC_URL, commitment=Confirmed)

# === STATES ===
REGISTER, SET_RISK, SET_STRATEGY, SET_ALERT = range(4)

# === ENHANCED DATA MANAGEMENT ===
def load_json_data(filename: str, default_value=None):
    """Generic JSON loader with error handling"""
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return default_value or {}
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default_value or {}

def save_json_data(filename: str, data):
    """Generic JSON saver with error handling"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def load_user_data():
    return load_json_data(DATA_FILE)

def save_user_data(data):
    save_json_data(DATA_FILE, data)

def load_alerts():
    return load_json_data(ALERTS_FILE)

def save_alerts(alerts):
    save_json_data(ALERTS_FILE, alerts)

def load_trades():
    return load_json_data(TRADES_FILE)

def save_trades(trades):
    save_json_data(TRADES_FILE, trades)

# === ENHANCED API FUNCTIONS ===
async def get_token_info(token_address: str) -> Optional[Dict]:
    """Get comprehensive token information"""
    async with httpx.AsyncClient() as client:
        try:
            # Get basic token data
            url = f"{DEX_SCREENER_URL}/tokens/{token_address}"
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if data.get("pairs"):
                return data["pairs"][0]
            return None
        except Exception as e:
            logger.error(f"Error fetching token info: {e}")
            return None

async def get_jupiter_quote(input_mint: str, output_mint: str, amount: int) -> Optional[Dict]:
    """Get quote from Jupiter for token swaps"""
    async with httpx.AsyncClient() as client:
        try:
            url = f"{JUPITER_API_URL}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": 50
            }
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Jupiter quote error: {e}")
            return None

async def analyze_token_risk(token_data: Dict) -> Dict:
    """Advanced token risk analysis"""
    risk_score = 0
    risk_factors = []
    
    # Liquidity analysis
    liquidity = token_data.get('liquidity', {}).get('usd', 0)
    if liquidity < 10000:
        risk_score += 30
        risk_factors.append("Low liquidity")
    elif liquidity < 100000:
        risk_score += 15
        risk_factors.append("Medium liquidity")
    
    # Volume analysis
    volume_24h = token_data.get('volume', {}).get('h24', 0)
    if volume_24h < 50000:
        risk_score += 25
        risk_factors.append("Low trading volume")
    
    # Price volatility
    price_change_24h = abs(token_data.get('priceChange', {}).get('h24', 0))
    if price_change_24h > 50:
        risk_score += 20
        risk_factors.append("High volatility")
    
    # Market cap analysis
    market_cap = token_data.get('fdv', 0)
    if market_cap < 1000000:
        risk_score += 25
        risk_factors.append("Low market cap")
    
    # Determine risk level
    if risk_score >= 70:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "recommendation": get_risk_recommendation(risk_level, risk_score)
    }

def get_risk_recommendation(risk_level: str, risk_score: int) -> str:
    """Get trading recommendation based on risk"""
    if risk_level == "HIGH":
        return "⚠️ High risk - Consider small position or avoid"
    elif risk_level == "MEDIUM":
        return "⚡ Medium risk - Trade with caution"
    else:
        return "✅ Low risk - Good for larger positions"

async def generate_price_chart(token_data: Dict) -> Optional[bytes]:
    """Generate a simple price chart"""
    try:
        # Mock data for demonstration - in real implementation, you'd fetch historical data
        prices = [100, 105, 98, 110, 115, 108, 120, 125, 118, 130]
        times = list(range(len(prices)))
        
        plt.figure(figsize=(10, 6))
        plt.plot(times, prices, 'b-', linewidth=2)
        plt.title(f"{token_data.get('baseToken', {}).get('symbol', 'TOKEN')} Price Chart")
        plt.xlabel('Time')
        plt.ylabel('Price ($)')
        plt.grid(True, alpha=0.3)
        
        # Save to bytes
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        chart_bytes = buffer.getvalue()
        plt.close()
        
        return chart_bytes
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        return None

# === ENHANCED COMMAND HANDLERS ===

async def advanced_scan(update, ctx):
    """Advanced token scanner with multiple filters and risk analysis"""
    # Parse arguments for advanced filtering
    filters = {
        "min_volume": 100000,
        "min_change": 20,
        "max_risk": 70,
        "min_liquidity": 50000,
        "timeframe": "h24"
    }
    
    for arg in ctx.args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            if key in filters:
                try:
                    filters[key] = float(value) if key != "timeframe" else value
                except ValueError:
                    await update.message.reply_text(f"Invalid value for {key}")
                    return
    
    async with httpx.AsyncClient() as client:
        url = f"{DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.{filters['timeframe']}&order=desc&limit=100"
        tokens = await fetch_tokens(client, url)
        
        if not tokens:
            await update.message.reply_text("No tokens found. Try again later.")
            return
        
        # Apply advanced filtering
        candidates = []
        for token in tokens:
            volume = token.get('volume', {}).get(filters['timeframe'], 0)
            price_change = token.get('priceChange', {}).get(filters['timeframe'], 0)
            liquidity = token.get('liquidity', {}).get('usd', 0)
            
            if (volume >= filters['min_volume'] and 
                abs(price_change) >= filters['min_change'] and
                liquidity >= filters['min_liquidity']):
                
                # Perform risk analysis
                risk_analysis = await analyze_token_risk(token)
                if risk_analysis['risk_score'] <= filters['max_risk']:
                    token['risk_analysis'] = risk_analysis
                    candidates.append(token)
        
        if not candidates:
            await update.message.reply_text("No tokens match your criteria. Try adjusting filters.")
            return
        
        # Sort by risk score (lower is better)
        candidates.sort(key=lambda x: x['risk_analysis']['risk_score'])
        
        reply = f"🔍 Advanced Scan Results (Top {min(5, len(candidates))}):\n\n"
        for i, token in enumerate(candidates[:5], 1):
            risk = token['risk_analysis']
            symbol = token.get('baseToken', {}).get('symbol', 'N/A')
            price = token.get('priceUsd', 'N/A')
            change = token.get('priceChange', {}).get(filters['timeframe'], 'N/A')
            
            reply += (
                f"{i}. {symbol} — ${price}\n"
                f"📈 {filters['timeframe']}: {change}%\n"
                f"🎯 Risk: {risk['risk_level']} ({risk['risk_score']}/100)\n"
                f"💡 {risk['recommendation']}\n"
                f"📍 {token.get('baseToken', {}).get('address', 'N/A')}\n\n"
            )
        
        await update.message.reply_text(reply)

async def portfolio_analysis(update, ctx):
    """Advanced portfolio analysis with P&L tracking"""
    user_data = load_user_data().get(str(update.effective_user.id))
    if not user_data:
        return await update.message.reply_text("Link with /register.")
    
    try:
        wallet = Pubkey.from_string(user_data['wallet'])
        
        # Get SOL balance
        sol_balance = await rpc_client.get_balance(wallet)
        sol_amount = sol_balance.value / 1e9
        
        # Get token accounts
        token_accounts = await rpc_client.get_token_accounts_by_owner(wallet, commitment="confirmed")
        
        if not token_accounts.value:
            await update.message.reply_text("No tokens found in portfolio.")
            return
        
        # Calculate portfolio value
        total_value_usd = sol_amount * 100  # Assuming SOL = $100 for demo
        portfolio_items = []
        
        for acc in token_accounts.value:
            try:
                balance = await rpc_client.get_token_account_balance(acc.pubkey)
                mint = acc.account.data.parsed['info']['mint']
                amount = balance.value.ui_amount or 0
                
                if amount > 0:
                    # Get token price
                    token_info = await get_token_info(mint)
                    if token_info:
                        price_usd = float(token_info.get('priceUsd', 0))
                        value_usd = amount * price_usd
                        total_value_usd += value_usd
                        
                        portfolio_items.append({
                            'symbol': token_info.get('baseToken', {}).get('symbol', 'Unknown'),
                            'amount': amount,
                            'price': price_usd,
                            'value': value_usd,
                            'change_24h': token_info.get('priceChange', {}).get('h24', 0)
                        })
            except Exception as e:
                logger.error(f"Error processing token account: {e}")
                continue
        
        # Generate portfolio report
        reply = f"📊 Portfolio Analysis\n\n"
        reply += f"💰 Total Value: ${total_value_usd:.2f}\n"
        reply += f"🪙 SOL: {sol_amount:.4f} (${sol_amount * 100:.2f})\n\n"
        
        if portfolio_items:
            reply += "🎯 Token Holdings:\n"
            for item in sorted(portfolio_items, key=lambda x: x['value'], reverse=True):
                change_emoji = "📈" if item['change_24h'] > 0 else "📉"
                reply += (
                    f"{item['symbol']}: {item['amount']:.2f}\n"
                    f"  💲 ${item['price']:.6f} | ${item['value']:.2f}\n"
                    f"  {change_emoji} 24h: {item['change_24h']:.2f}%\n\n"
                )
        
        await update.message.reply_text(reply)
        
    except Exception as e:
        logger.error(f"Portfolio analysis error: {e}")
        await update.message.reply_text("⚠️ Error analyzing portfolio. Try again later.")

async def set_price_alert(update, ctx):
    """Set price alerts for tokens"""
    if len(ctx.args) < 3:
        return await update.message.reply_text(
            "Usage: /alert <token_address> <above/below> <price>\n"
            "Example: /alert So11111111111111111111111111111111111111112 above 150"
        )
    
    token_address = ctx.args[0]
    condition = ctx.args[1].lower()
    
    if condition not in ["above", "below"]:
        return await update.message.reply_text("Condition must be 'above' or 'below'")
    
    try:
        target_price = float(ctx.args[2])
        Pubkey.from_string(token_address)  # Validate address
    except (ValueError, Exception):
        return await update.message.reply_text("Invalid token address or price.")
    
    # Get token info to validate
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found or invalid address.")
    
    # Save alert
    alerts = load_alerts()
    uid = str(update.effective_user.id)
    
    if uid not in alerts:
        alerts[uid] = []
    
    alert = {
        "token_address": token_address,
        "token_symbol": token_info.get('baseToken', {}).get('symbol', 'Unknown'),
        "target_price": target_price,
        "condition": condition,
        "created_at": datetime.now().isoformat(),
        "is_active": True
    }
    
    alerts[uid].append(alert)
    save_alerts(alerts)
    
    current_price = token_info.get('priceUsd', 'N/A')
    await update.message.reply_text(
        f"🔔 Alert set for {alert['token_symbol']}!\n"
        f"📍 Trigger: {condition} ${target_price}\n"
        f"💲 Current: ${current_price}"
    )

async def market_sentiment(update, ctx):
    """Analyze overall market sentiment"""
    async with httpx.AsyncClient() as client:
        # Get top tokens by volume
        url = f"{DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.h24&order=desc&limit=50"
        tokens = await fetch_tokens(client, url)
        
        if not tokens:
            await update.message.reply_text("Unable to fetch market data.")
            return
        
        # Calculate sentiment metrics
        total_tokens = len(tokens)
        positive_tokens = sum(1 for t in tokens if t.get('priceChange', {}).get('h24', 0) > 0)
        negative_tokens = total_tokens - positive_tokens
        
        avg_change = sum(t.get('priceChange', {}).get('h24', 0) for t in tokens) / total_tokens
        
        total_volume = sum(t.get('volume', {}).get('h24', 0) for t in tokens)
        
        # Determine sentiment
        if avg_change > 5:
            sentiment = "🚀 BULLISH"
        elif avg_change > 0:
            sentiment = "📈 POSITIVE"
        elif avg_change > -5:
            sentiment = "😐 NEUTRAL"
        else:
            sentiment = "📉 BEARISH"
        
        reply = f"📊 Market Sentiment Analysis\n\n"
        reply += f"🎯 Overall: {sentiment}\n"
        reply += f"📈 Rising: {positive_tokens} tokens ({positive_tokens/total_tokens*100:.1f}%)\n"
        reply += f"📉 Falling: {negative_tokens} tokens ({negative_tokens/total_tokens*100:.1f}%)\n"
        reply += f"🔥 Avg Change: {avg_change:.2f}%\n"
        reply += f"💧 Total Volume: ${total_volume:,.0f}\n\n"
        
        # Top movers
        top_gainers = sorted(tokens, key=lambda x: x.get('priceChange', {}).get('h24', 0), reverse=True)[:3]
        top_losers = sorted(tokens, key=lambda x: x.get('priceChange', {}).get('h24', 0))[:3]
        
        reply += "🏆 Top Gainers:\n"
        for token in top_gainers:
            symbol = token.get('baseToken', {}).get('symbol', 'N/A')
            change = token.get('priceChange', {}).get('h24', 0)
            reply += f"• {symbol}: +{change:.1f}%\n"
        
        reply += "\n💥 Top Losers:\n"
        for token in top_losers:
            symbol = token.get('baseToken', {}).get('symbol', 'N/A')
            change = token.get('priceChange', {}).get('h24', 0)
            reply += f"• {symbol}: {change:.1f}%\n"
        
        await update.message.reply_text(reply)

async def trade_simulator(update, ctx):
    """Simulate trades for learning"""
    if len(ctx.args) < 3:
        return await update.message.reply_text(
            "Usage: /simulate <buy/sell> <token_address> <amount_sol>\n"
            "Example: /simulate buy So11111111111111111111111111111111111111112 0.1"
        )
    
    action = ctx.args[0].lower()
    token_address = ctx.args[1]
    
    if action not in ["buy", "sell"]:
        return await update.message.reply_text("Action must be 'buy' or 'sell'")
    
    try:
        amount_sol = float(ctx.args[2])
        Pubkey.from_string(token_address)
    except (ValueError, Exception):
        return await update.message.reply_text("Invalid token address or amount.")
    
    # Get token info
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found.")
    
    # Simulate the trade
    price_usd = float(token_info.get('priceUsd', 0))
    if price_usd == 0:
        return await update.message.reply_text("Unable to get token price.")
    
    sol_price = 100  # Assuming SOL = $100
    trade_value_usd = amount_sol * sol_price
    token_amount = trade_value_usd / price_usd
    
    # Calculate fees (simulate 0.3% fee)
    fee_usd = trade_value_usd * 0.003
    
    # Store simulated trade
    trades = load_trades()
    uid = str(update.effective_user.id)
    
    if uid not in trades:
        trades[uid] = []
    
    trade_record = {
        "token_address": token_address,
        "token_symbol": token_info.get('baseToken', {}).get('symbol', 'Unknown'),
        "action": action,
        "amount_sol": amount_sol,
        "token_amount": token_amount,
        "price_usd": price_usd,
        "trade_value_usd": trade_value_usd,
        "fee_usd": fee_usd,
        "timestamp": datetime.now().isoformat(),
        "is_simulation": True
    }
    
    trades[uid].append(trade_record)
    save_trades(trades)
    
    reply = f"📊 Trade Simulation\n\n"
    reply += f"🎯 Action: {action.upper()}\n"
    reply += f"🪙 Token: {trade_record['token_symbol']}\n"
    reply += f"💰 Amount: {amount_sol} SOL (${trade_value_usd:.2f})\n"
    reply += f"🎨 Price: ${price_usd:.6f}\n"
    reply += f"📦 Tokens: {token_amount:.2f}\n"
    reply += f"💸 Fee: ${fee_usd:.2f}\n"
    reply += f"✅ Trade simulated successfully!"
    
    await update.message.reply_text(reply)

async def whale_tracker(update, ctx):
    """Track large transactions (whale movements)"""
    # This would typically connect to a real whale tracking service
    # For demo purposes, we'll simulate some whale activity
    
    mock_whale_transactions = [
        {
            "token_symbol": "SOL",
            "amount": "25,000",
            "value_usd": "2,500,000",
            "action": "BUY",
            "wallet": "7xKX...AsU8",
            "timestamp": "2 min ago"
        },
        {
            "token_symbol": "BONK",
            "amount": "1,000,000,000",
            "value_usd": "450,000",
            "action": "SELL",
            "wallet": "9WzD...AWM",
            "timestamp": "5 min ago"
        },
        {
            "token_symbol": "JUP",
            "amount": "500,000",
            "value_usd": "750,000",
            "action": "BUY",
            "wallet": "HhJp...Zg4",
            "timestamp": "8 min ago"
        }
    ]
    
    reply = "🐋 Whale Activity Tracker\n\n"
    for tx in mock_whale_transactions:
        emoji = "🟢" if tx["action"] == "BUY" else "🔴"
        reply += (
            f"{emoji} {tx['action']} {tx['token_symbol']}\n"
            f"💰 ${tx['value_usd']} ({tx['amount']} tokens)\n"
            f"👤 {tx['wallet']}\n"
            f"⏰ {tx['timestamp']}\n\n"
        )
    
    reply += "💡 Tip: Follow whale movements for market insights!"
    await update.message.reply_text(reply)

# === ENHANCED UTILITY FUNCTIONS ===
async def fetch_tokens(client, url):
    """Enhanced token fetching with better error handling"""
    try:
        response = await client.get(url, timeout=15.0)
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

async def check_price_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Check and trigger price alerts"""
    logger.info("🔔 Checking price alerts...")
    alerts = load_alerts()
    
    for uid, user_alerts in alerts.items():
        for alert in user_alerts:
            if not alert.get('is_active', True):
                continue
            
            try:
                # Get current price
                token_info = await get_token_info(alert['token_address'])
                if not token_info:
                    continue
                
                current_price = float(token_info.get('priceUsd', 0))
                target_price = alert['target_price']
                condition = alert['condition']
                
                # Check if alert should trigger
                should_trigger = False
                if condition == "above" and current_price >= target_price:
                    should_trigger = True
                elif condition == "below" and current_price <= target_price:
                    should_trigger = True
                
                if should_trigger:
                    # Send alert
                    message = (
                        f"🚨 PRICE ALERT TRIGGERED!\n\n"
                        f"🪙 {alert['token_symbol']}\n"
                        f"💰 Current: ${current_price:.6f}\n"
                        f"🎯 Target: {condition} ${target_price:.6f}\n"
                        f"📈 Status: Alert triggered!"
                    )
                    
                    await context.bot.send_message(chat_id=uid, text=message)
                    
                    # Deactivate alert
                    alert['is_active'] = False
                    
            except Exception as e:
                logger.error(f"Error checking alert: {e}")
    
    # Save updated alerts
    save_alerts(alerts)

# === ORIGINAL COMMANDS (keeping the existing ones) ===
# ... (include all the original command handlers from the previous code)

# === MAIN FUNCTION ===
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Enhanced command handlers
    enhanced_handlers = [
        CommandHandler('advanced_scan', advanced_scan),
        CommandHandler('portfolio_analysis', portfolio_analysis),
        CommandHandler('alert', set_price_alert),
        CommandHandler('sentiment', market_sentiment),
        CommandHandler('simulate', trade_simulator),
        CommandHandler('whales', whale_tracker),
    ]
    
    # Add all handlers
    for handler in enhanced_handlers:
        app.add_handler(handler)
    
    # Set up enhanced job queue
    async def post_init(application):
        # Set enhanced commands
        enhanced_commands = [
            ("advanced_scan", "Advanced token scanner"),
            ("portfolio_analysis", "Detailed portfolio analysis"),
            ("alert", "Set price alerts"),
            ("sentiment", "Market sentiment analysis"),
            ("simulate", "Trade simulator"),
            ("whales", "Whale tracker"),
        ]
        
        # Add to existing commands
        all_commands = [
            ("start", "Start bot"), ("help", "List commands"), ("register", "Link wallet"),
            ("balance", "SOL balance"), ("portfolio", "Show tokens"), ("status", "Wallet summary"),
             ("advanced_scan", "Advanced scanner"),
            ("sentiment", "Market sentiment"), ("whales", "Whale tracker"),
            ("alert", "Price alerts"), ("simulate", "Trade simulator"),
            ("watch", "Add to watchlist"), ("watchlist", "View watchlist")
        ]
        
        await application.bot.set_my_commands([BotCommand(c, d) for c, d in all_commands])
        
        # Enhanced job scheduling
        job_queue = application.job_queue
        if job_queue:
            # Check price alerts every minute
            job_queue.run_repeating(check_price_alerts, interval=60, first=30)
            # Check watchlist every 5 minutes
            job_queue.run_repeating(check_watchlist, interval=300, first=60)
    
    app.post_init = post_init
    
    logger.info("🚀 Enhanced UltimateTraderBot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
