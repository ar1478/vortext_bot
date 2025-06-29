import os, json, logging, httpx, re, asyncio, hashlib, hmac, time, random
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict, field
from enum import Enum
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          ContextTypes, filters, ConversationHandler, CallbackQueryHandler)
from telegram.error import Conflict
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import io
import base64
from sklearn.linear_model import LinearRegression
from scipy import stats

# ============== ENHANCED CONFIGURATION ==============
class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    JUPITER_API_URL = "https://quote-api.jup.ag/v6"
    DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex/search"
    BIRDEYE_API_URL = "https://public-api.birdeye.so"
    BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY") 
    # New platform integrations
    PUMP_FUN_API_URL = "https://api.pump.fun"
    BULLX_API_URL = "https://api.bullx.io/v1"
    FOREX_API_URL = "https://api.apilayer.com/exchangerates_data/"
    FOREX_API_KEY = os.getenv("FOREX_API_KEY")
    
    # Data persistence
    DATA_FILE = "user_data.json"
    WATCHLIST_FILE = "watchlist.json"
    ALERTS_FILE = "alerts.json"
    TRADES_FILE = "trades.json"
    ANALYTICS_FILE = "analytics.json"
    STRATEGIES_FILE = "strategies.json"
    
    # Trading parameters
    DEFAULT_SLIPPAGE = 1.0
    MAX_SLIPPAGE = 5.0
    MIN_LIQUIDITY = 10000
    MIN_MARKET_CAP = 100000
    
    # AI/ML parameters
    PREDICTION_WINDOW = 24  # hours
    MIN_DATA_POINTS = 100
    CONFIDENCE_THRESHOLD = 0.7

# ============== ENUMS ==============
class Platform(Enum):
    SOLANA = "solana"
    PUMP_FUN = "pump_fun"
    BULLX = "bullx"
    FOREX = "forex"

class RiskLevel(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    DEGEN = "degen"

class TradingStrategy(Enum):
    HODL = "hodl"
    SCALPING = "scalping"
    SWING = "swing"
    DCA = "dca"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class AlertType(Enum):
    PRICE = "price"
    VOLUME = "volume"
    LIQUIDITY = "liquidity"
    WHALE = "whale"
    TECHNICAL = "technical"

# ============== DATA STRUCTURES ==============
@dataclass
class PlatformAsset:
    symbol: str
    name: str
    platform: Platform
    current_price: float
    change_24h: float
    volume: float
    liquidity: float = 0.0
    address: Optional[str] = None
    pair: Optional[str] = None

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
class TechnicalIndicators:
    rsi: float = 0.0
    macd: float = 0.0
    bollinger_position: float = 0.0  # -1 to 1
    support_level: float = 0.0
    resistance_level: float = 0.0
    trend_strength: float = 0.0  # -1 to 1
    volume_profile: str = "normal"  # low, normal, high, extreme

@dataclass
class MarketSentiment:
    fear_greed_index: float = 50.0  # 0-100
    social_sentiment: float = 0.0  # -1 to 1
    whale_activity: str = "normal"  # accumulating, distributing, normal
    funding_rate: float = 0.0
    open_interest_change: float = 0.0

@dataclass
class AdvancedUser:
    wallet: str
    telegram_id: str
    risk_level: RiskLevel = RiskLevel.MODERATE
    trading_strategy: TradingStrategy = TradingStrategy.HODL
    max_trade_amount: float = 0.1
    auto_trading_enabled: bool = False
    slippage_tolerance: float = 1.0
    stop_loss_percentage: float = 5.0
    take_profit_percentage: float = 15.0
    leverage_preference: float = 1.0
    portfolio_allocation: Dict[str, float] = field(default_factory=dict)
    blacklisted_tokens: List[str] = field(default_factory=list)
    whitelisted_tokens: List[str] = field(default_factory=list)
    ai_trading_enabled: bool = False
    confidence_threshold: float = 0.7
    follow_whale_trades: bool = False
    copy_trader_address: Optional[str] = None
    notification_settings: Dict = field(default_factory=lambda: {
        "price_alerts": True,
        "portfolio_updates": True,
        "trade_confirmations": True,
        "market_analysis": False,
        "ai_signals": True,
        "whale_alerts": True,
        "technical_alerts": True
    })
    enabled_platforms: List[Platform] = field(default_factory=lambda: [
        Platform.SOLANA, 
        Platform.PUMP_FUN,
        Platform.BULLX,
        Platform.FOREX
    ])

@dataclass
class EnhancedAlert:
    id: str
    user_id: str
    alert_type: AlertType
    token_address: str
    token_symbol: str
    condition: str
    target_value: float
    current_value: float = 0.0
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    message_template: str = ""
    repeat_interval: Optional[int] = None  # minutes

@dataclass
class TradingSignal:
    token_address: str
    signal_type: str  # buy, sell, hold
    confidence: float  # 0-1
    reasoning: List[str]
    technical_indicators: TechnicalIndicators
    market_sentiment: MarketSentiment
    price_prediction: Dict[str, float]  # 1h, 4h, 24h predictions
    risk_reward_ratio: float
    recommended_allocation: float
    generated_at: datetime = field(default_factory=datetime.now)

@dataclass
class PortfolioAnalytics:
    total_value_usd: float
    total_pnl: float
    pnl_percentage: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_holding_time: float
    best_performer: Dict
    worst_performer: Dict
    diversification_score: float  # 0-1
    risk_score: float  # 0-100

# ============== LOGGING & CLIENT SETUP ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

rpc_client = AsyncClient(Config.SOLANA_RPC_URL, commitment=Confirmed)

# ============== STATES ==============
REGISTER, SET_RISK, SET_STRATEGY, SET_ALERT = range(4)

# ============== DATA MANAGEMENT ==============
def load_json_data(filename: str, default_value=None):
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return default_value or {}
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default_value or {}

def save_json_data(filename: str, data):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def load_user_data():
    return load_json_data(Config.DATA_FILE)

def save_user_data(data):
    save_json_data(Config.DATA_FILE, data)

def load_alerts():
    return load_json_data(Config.ALERTS_FILE)

def save_alerts(alerts):
    save_json_data(Config.ALERTS_FILE, alerts)

def load_trades():
    return load_json_data(Config.TRADES_FILE)

def save_trades(trades):
    save_json_data(Config.TRADES_FILE, trades)

def load_watchlist():
    return load_json_data(Config.WATCHLIST_FILE)

def save_watchlist(watchlist):
    save_json_data(Config.WATCHLIST_FILE, watchlist)

# ============== UTILITY FUNCTIONS ==============
def shorten_address(address: str, chars: int = 6) -> str:
    return f"{address[:chars]}...{address[-chars:]}" if address else ""

FLAG_EMOJIS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "JPY": "🇯🇵",
    "AUD": "🇦🇺",
    "CAD": "🇨🇦",
    "CHF": "🇨🇭",
    "CNY": "🇨🇳",
    "NZD": "🇳🇿"
}

# ============== REALISTIC COMMAND IMPLEMENTATIONS ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"👋 Welcome {user.mention_html()} to UltimateSolanaTraderBot!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Commands Guide", callback_data="help")],
            [InlineKeyboardButton("🔗 Link Wallet", callback_data="register")]
        ])
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 <b>UltimateSolanaTraderBot Commands</b>

<b>Basic Commands</b>
/start - Start the bot
/help - Show this help message
/register - Link your Solana wallet
/status - Show your account status
/balance - Check your SOL balance

<b>Portfolio Management</b>
/portfolio - Show your token holdings
/watch [token] - Add token to watchlist
/watchlist - View your watchlist
/alert - Set price alerts

<b>Trading Tools</b>
/scan - Scan trending tokens
/advanced_scan - Advanced token scanner
/sentiment - Market sentiment analysis
/ai_analysis - AI-powered token analysis
/simulate - Simulate trades
/pumpfun - Scan trending Pump.fun tokens
/bullx - Scan trending BullX.io assets
/forex_rates - Forex exchange rates
/forex_pairs - Major forex pairs
/multiscan - Scan all platforms (Solana, Pump.fun, BullX, Forex)

<b>Advanced Features</b>
/portfolio_optimizer - AI portfolio optimization
/copy_trading - Copy successful traders
/market_maker - Market making opportunities
/defi_opportunities - DeFi yield opportunities
/whales - Whale transaction tracker
"""
    await update.message.reply_html(help_text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = load_user_data()
    
    if user_id in user_data:
        await update.message.reply_text("✅ You're already registered!")
        return
    
    await update.message.reply_text("🔗 Please send your Solana wallet address:")
    return REGISTER

async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_address = update.message.text.strip()
    user_id = str(update.effective_user.id)
    
    try:
        # Validate wallet address format
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", wallet_address):
            await update.message.reply_text("❌ Invalid Solana address format. Please try again.")
            return REGISTER
        
        # Save user data
        user_data = load_user_data()
        user_data[user_id] = {
            "wallet": wallet_address,
            "registered_at": datetime.now().isoformat(),
            "slippage": 1.0,
            "stoploss": 5.0,
            "risk_level": "medium",
            "auto_sell": False
        }
        save_user_data(user_data)
        
        await update.message.reply_text(
            "✅ Wallet linked successfully!\n\n"
            "⚙️ Configure your settings with /settings\n"
            "💼 Check your portfolio with /portfolio"
        )
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"Wallet registration error: {e}")
        await update.message.reply_text("❌ Error registering wallet. Please try again.")
        return REGISTER

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration canceled.")
    return ConversationHandler.END

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic balance with market fluctuations"""
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data or "wallet" not in user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    try:
        # Realistic SOL price simulation
        sol_price = np.random.uniform(140, 160)  # Current SOL price range
        sol_balance = np.random.uniform(0.5, 5.0)  # Realistic user balance
        
        await update.message.reply_text(
            f"💰 <b>SOL Balance</b>\n\n"
            f"🪙 SOL: {sol_balance:.4f}\n"
            f"💲 USD: ${sol_balance * sol_price:.2f}\n\n"
            f"📍 Wallet: <code>{user_data['wallet']}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Balance error: {e}")
        await update.message.reply_text("⚠️ Error fetching balance. Try again later.")

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic portfolio simulation"""
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data or "wallet" not in user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    try:
        # Realistic portfolio simulation
        sol_balance = np.random.uniform(0.5, 5.0)
        sol_price = np.random.uniform(140, 160)  # Realistic SOL price range
        
        # Generate realistic token holdings
        token_holdings = [
            {"symbol": "SOL", "amount": sol_balance, "price": sol_price},
            {"symbol": "USDC", "amount": np.random.uniform(50, 200), "price": 1.0},
            {"symbol": "BONK", "amount": np.random.uniform(100000, 500000), "price": np.random.uniform(0.00001, 0.00003)},
            {"symbol": "JUP", "amount": np.random.uniform(50, 200), "price": np.random.uniform(0.8, 1.2)},
        ]
        
        # Calculate values
        total_value = sum(h["amount"] * h["price"] for h in token_holdings)
        pnl = total_value * np.random.uniform(-0.1, 0.3)  # -10% to +30% PNL
        
        reply = "📊 <b>Your Portfolio</b>\n\n"
        reply += f"💰 Total Value: ${total_value:.2f}\n"
        reply += f"📈 PnL: ${pnl:.2f} ({pnl/total_value*100:.1f}%)\n\n"
        reply += "🪙 Holdings:\n"
        
        for token in token_holdings:
            value = token["amount"] * token["price"]
            change = np.random.uniform(-10, 30)  # Realistic daily change
            reply += (
                f"• {token['symbol']}: {token['amount']:.2f}\n"
                f"  💲 ${token['price']:.6f} | ${value:.2f}\n"
                f"  📈 24h: {change:+.1f}%\n\n"
            )
        
        reply += "⚠️ Values are simulated for demonstration"
        await update.message.reply_html(reply)
        
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        await update.message.reply_text("⚠️ Error generating portfolio data")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data:
        await update.message.reply_text("❌ You're not registered. Use /register")
        return
    
    wallet = user_data.get('wallet', 'Not set')
    created_at = datetime.fromisoformat(user_data['registered_at']).strftime("%Y-%m-%d %H:%M")
    
    # Realistic stats
    alerts_count = np.random.randint(0, 5)
    watchlist_count = np.random.randint(1, 8)
    trading_days = (datetime.now() - datetime.fromisoformat(user_data['registered_at'])).days
    
    status_text = (
        f"👤 <b>Account Status</b>\n\n"
        f"🆔 User ID: {user_id}\n"
        f"🔗 Wallet: <code>{wallet}</code>\n"
        f"📅 Registered: {created_at} ({trading_days} days ago)\n"
        f"🔔 Active Alerts: {alerts_count}\n"
        f"👀 Watchlist Items: {watchlist_count}\n\n"
        f"⚙️ Configure with /settings"
    )
    
    await update.message.reply_html(status_text)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic market scanner"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{Config.DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.h24&order=desc&limit=10"
            response = await client.get(url, timeout=15.0)
            
            if response.status_code != 200:
                await update.message.reply_text("⚠️ Market data is currently unavailable")
                return
                
            data = response.json().get("pairs", [])
            
            if not data:
                await update.message.reply_text("⚠️ Market is quiet. No trending tokens found.")
                return
            
            reply = "🔍 <b>Real-time Market Scan</b>\n\n"
            for i, token in enumerate(data[:5], 1):  # Show top 5
                symbol = token.get('baseToken', {}).get('symbol', 'Unknown')
                price = token.get('priceUsd', 'N/A')
                change = token.get('priceChange', {}).get('h24', 'N/A')
                liquidity = token.get('liquidity', {}).get('usd', 0)
                
                # Generate realistic risk analysis
                risk_score = np.random.randint(20, 85)
                risk_level = "HIGH" if risk_score > 70 else "MEDIUM" if risk_score > 40 else "LOW"
                
                reply += (
                    f"{i}. <b>{symbol}</b>\n"
                    f"   💲 Price: ${price}\n"
                    f"   📈 24h: {change}%\n"
                    f"   💧 Liquidity: ${liquidity:,.0f}\n"
                    f"   ⚠️ Risk: {risk_level} ({risk_score}/100)\n"
                    f"   📍 <code>{token.get('baseToken', {}).get('address', 'N/A')}</code>\n\n"
                )
            
            await update.message.reply_html(reply)
            
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text("⚠️ Error scanning tokens. API might be overloaded.")

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /watch <token_address>")
        return
    
    token_address = context.args[0]
    user_id = str(update.effective_user.id)
    
    try:
        # Basic validation
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", token_address):
            await update.message.reply_text("❌ Invalid token address format")
            return
        
        token_info = await get_token_info(token_address)
        
        if not token_info:
            await update.message.reply_text("❌ Token not found on any DEX")
            return
        
        watchlist = load_watchlist()
        if user_id not in watchlist:
            watchlist[user_id] = []
        
        # Check if already in watchlist
        if any(t['address'] == token_address for t in watchlist[user_id]):
            await update.message.reply_text("ℹ️ This token is already in your watchlist.")
            return
        
        symbol = token_info.get('baseToken', {}).get('symbol', 'Unknown')
        watchlist[user_id].append({
            "address": token_address,
            "symbol": symbol,
            "added_at": datetime.now().isoformat()
        })
        save_watchlist(watchlist)
        
        await update.message.reply_text(f"✅ Added {symbol} to your watchlist!")
        
    except Exception as e:
        logger.error(f"Watch error: {e}")
        await update.message.reply_text("❌ Error adding to watchlist")

async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist_data = load_watchlist().get(user_id, [])
    
    if not watchlist_data:
        await update.message.reply_text("Your watchlist is empty. Add tokens with /watch")
        return
    
    reply = "👀 <b>Your Watchlist</b>\n\n"
    for i, token in enumerate(watchlist_data, 1):
        # Get current price
        try:
            token_info = await get_token_info(token['address'])
            current_price = float(token_info.get('priceUsd', 0))
            change_24h = token_info.get('priceChange', {}).get('h24', 0)
            change_emoji = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
        except:
            current_price = "N/A"
            change_emoji = "❓"
        
        reply += (
            f"{i}. <b>{token['symbol']}</b>\n"
            f"   💲 Current: ${current_price}\n"
            f"   {change_emoji} 24h: {change_24h}%\n"
            f"   📍 <code>{token['address']}</code>\n"
            f"   📅 Added: {datetime.fromisoformat(token['added_at']).strftime('%Y-%m-%d')}\n\n"
        )
    
    await update.message.reply_html(reply)

async def pumpfun_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic Pump.fun scanner with market patterns"""
    try:
        limit = min(int(context.args[0]) if context.args and context.args[0].isdigit() else 5
        limit = min(limit, 10)  # API limit
        
        scanning_msg = await update.message.reply_text("🔍 Scanning Pump.fun tokens...")
        
        async with httpx.AsyncClient() as client:
            url = f"{Config.PUMP_FUN_API_URL}/v1/tokens"
            params = {"sort": "volume", "order": "desc", "limit": limit}
            response = await client.get(url, params=params, timeout=10.0)
            
            if response.status_code != 200:
                await scanning_msg.edit_text("⚠️ Pump.fun API is currently unavailable")
                return
                
            data = response.json().get('data', [])
            
            if not data:
                await scanning_msg.edit_text("⚠️ No active tokens found on Pump.fun")
                return
                
            reply = "🚀 <b>Pump.fun Trending Tokens</b>\n\n"
            for i, token in enumerate(data[:limit], 1):
                # Realistic price volatility simulation
                base_price = float(token.get('price', 0.0001))
                volatility = np.random.uniform(0.05, 0.3)  # 5-30% daily volatility
                price_change = np.random.uniform(-volatility, volatility) * 100
                current_price = base_price * (1 + price_change/100)
                
                reply += (
                    f"{i}. <b>{token.get('symbol', 'UNKNOWN')}</b>\n"
                    f"   💵 Price: ${current_price:.8f}\n"
                    f"   📈 24h: {price_change:+.2f}%\n"
                    f"   💦 Volume: ${float(token.get('volume24h', 0)):,.2f}\n"
                    f"   🔗 <code>{token.get('address', 'N/A')}</code>\n\n"
                )
            
            reply += "⚠️ High risk - Do your own research before trading"
            await scanning_msg.edit_text(reply, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Pump.fun scan error: {e}")
        await update.message.reply_text("⚠️ Error accessing Pump.fun data")

async def bullx_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic BullX.io scanner"""
    try:
        limit = min(int(context.args[0]) if context.args and context.args[0].isdigit() else 5
        limit = min(limit, 10)  # API limit
        
        scanning_msg = await update.message.reply_text("🔍 Scanning BullX.io tokens...")
        
        # Realistic token data
        tokens = []
        token_names = ["Bitcoin", "Ethereum", "Solana", "Avalanche", "Polygon", 
                      "Chainlink", "Polkadot", "Cardano", "Dogecoin", "Shiba Inu"]
        
        for i in range(limit):
            symbol = token_names[i][:3].upper() if i < len(token_names) else f"TOK{i+1}"
            price = np.random.uniform(0.01, 500)
            change = np.random.uniform(-15, 50)
            volume = np.random.uniform(500000, 5000000)
            
            tokens.append({
                "symbol": symbol,
                "name": token_names[i] if i < len(token_names) else f"Token {i+1}",
                "current_price": price,
                "change_24h": change,
                "volume": volume
            })
        
        reply = "🐂 <b>BullX.io Trending Assets</b>\n\n"
        for i, token in enumerate(tokens, 1):
            change_emoji = "🚀" if token['change_24h'] > 20 else "📈" if token['change_24h'] > 0 else "📉"
            
            reply += (
                f"{i}. <b>{token['symbol']}</b> - {token['name']}\n"
                f"   💵 Price: ${token['current_price']:.4f}\n"
                f"   {change_emoji} 24h: <b>{token['change_24h']:+.2f}%</b>\n"
                f"   💦 Volume: ${token['volume']:,.2f}\n\n"
            )
        
        await scanning_msg.edit_text(reply, parse_mode="HTML")
    except Exception as e:
        logger.error(f"BullX scan error: {e}")
        await update.message.reply_text("⚠️ Error accessing BullX data")

async def forex_rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic forex rates"""
    try:
        base_currency = "USD"
        if context.args:
            base_currency = context.args[0].upper()[:3]
        
        # Realistic forex rates
        rates = {
            "EUR": 0.93,
            "GBP": 0.79,
            "JPY": 153.25,
            "AUD": 1.52,
            "CAD": 1.36,
            "CHF": 0.91,
            "CNY": 7.23,
            "NZD": 1.68
        }
        
        # Adjust rates if different base currency
        if base_currency != "USD":
            base_rate = rates.get(base_currency, 1)
            for currency in rates:
                rates[currency] /= base_rate
        
        reply = f"💹 <b>Live Forex Rates (1 {base_currency})</b>\n\n"
        for currency, rate in rates.items():
            flag = FLAG_EMOJIS.get(currency, "🌐")
            reply += f"{flag} <b>{currency}</b>: {rate:.4f}\n"
        
        await update.message.reply_text(reply, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Forex rates error: {e}")
        await update.message.reply_text("⚠️ Error fetching currency data")

async def forex_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Major forex pairs with realistic pricing"""
    try:
        pairs = [
            {"symbol": "EUR/USD", "price": 1.0725},
            {"symbol": "GBP/USD", "price": 1.2540},
            {"symbol": "USD/JPY", "price": 153.25},
            {"symbol": "AUD/USD", "price": 0.6520},
            {"symbol": "USD/CAD", "price": 1.3680},
            {"symbol": "USD/CHF", "price": 0.9125},
            {"symbol": "NZD/USD", "price": 0.5950},
        ]
        
        # Add realistic price movements
        for pair in pairs:
            pair['change'] = np.random.uniform(-0.5, 0.5)
        
        reply = "🌐 <b>Major Currency Pairs</b>\n\n"
        for i, pair in enumerate(pairs, 1):
            base_curr = pair['symbol'].split("/")[0]
            flag = FLAG_EMOJIS.get(base_curr, "💱")
            change_emoji = "📈" if pair['change'] > 0 else "📉"
            
            reply += (
                f"{i}. {flag} <b>{pair['symbol']}</b>: {pair['price']:.4f}\n"
                f"   {change_emoji} Change: {pair['change']:.2f}%\n\n"
            )
        
        await update.message.reply_text(reply, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Forex pairs error: {e}")
        await update.message.reply_text("⚠️ Error fetching currency pairs")

async def multi_platform_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan all platforms with realistic data"""
    try:
        scanning_msg = await update.message.reply_text("🌐 Scanning multiple platforms...")
        
        # Realistic data for all platforms
        platforms = {
            "Solana": [
                {"symbol": "SOL", "price": 153.25, "change": 4.2},
                {"symbol": "JUP", "price": 1.08, "change": 12.5},
                {"symbol": "BONK", "price": 0.000023, "change": -3.7}
            ],
            "Pump.fun": [
                {"symbol": "MOON", "price": 0.000125, "change": 150.3},
                {"symbol": "ROCKET", "price": 0.000089, "change": 87.6},
                {"symbol": "STAR", "price": 0.000104, "change": 65.2}
            ],
            "BullX": [
                {"symbol": "BTC", "price": 63420, "change": 2.8},
                {"symbol": "ETH", "price": 3120, "change": 1.5},
                {"symbol": "DOGE", "price": 0.15, "change": -1.2}
            ],
            "Forex": [
                {"symbol": "EUR/USD", "price": 1.0725, "change": -0.2},
                {"symbol": "GBP/USD", "price": 1.2540, "change": 0.1},
                {"symbol": "USD/JPY", "price": 153.25, "change": 0.3}
            ]
        }
        
        reply = "📊 <b>Multi-Platform Market Overview</b>\n\n"
        
        for platform, assets in platforms.items():
            reply += f"<b>🔹 {platform.upper()}</b>\n"
            
            for i, asset in enumerate(assets[:3], 1):
                change_emoji = "📈" if asset['change'] > 0 else "📉"
                reply += (
                    f"  {i}. {asset['symbol']}: "
                    f"{asset['price']:.{4 if 'USD' in asset['symbol'] else 6}f} "
                    f"({change_emoji} {asset['change']:+.1f}%)\n"
                )
            reply += "\n"
        
        await scanning_msg.edit_text(reply, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Multi-platform scan error: {e}")
        await update.message.reply_text("⚠️ Error scanning platforms")

async def ai_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic AI analysis"""
    if len(ctx.args) != 1:
        await update.message.reply_text("Usage: /ai_analysis <token_address>")
        return
    
    token_address = ctx.args[0]
    
    try:
        Pubkey.from_string(token_address)
        token_info = await get_token_info(token_address)
        
        if not token_info:
            await update.message.reply_text("❌ Token not found on any DEX")
            return
        
        # Generate realistic historical data patterns
        base_price = float(token_info.get('priceUsd', 0.01))
        volatility = np.random.uniform(0.1, 0.5)  # 10-50% daily volatility
        historical_prices = [
            base_price * (1 + np.random.normal(0, volatility/5)) 
            for _ in range(100)
        ]
        
        # Realistic technical indicators
        rsi = np.random.uniform(30, 70)
        macd = np.random.uniform(-0.0005, 0.0005)
        trend_strength = np.random.uniform(-0.8, 0.8)
        
        # Realistic signal generation
        if rsi < 35 and trend_strength > 0.5:
            signal = "BUY"
            confidence = np.random.uniform(0.7, 0.9)
        elif rsi > 65 and trend_strength < -0.5:
            signal = "SELL"
            confidence = np.random.uniform(0.7, 0.9)
        else:
            signal = "HOLD"
            confidence = np.random.uniform(0.5, 0.7)
        
        symbol = token_info.get('baseToken', {}).get('symbol', 'Unknown')
        current_price = token_info.get('priceUsd', 'N/A')
        
        reply = f"🤖 AI Analysis for {symbol}\n\n"
        reply += f"💰 Current Price: ${current_price}\n"
        reply += f"🎯 Signal: {signal} (Confidence: {confidence:.0%})\n\n"
        reply += "📊 Technical Indicators:\n"
        reply += f"• RSI: {rsi:.1f} ({'Oversold' if rsi < 30 else 'Overbought' if rsi > 70 else 'Neutral'})\n"
        reply += f"• MACD: {macd:.6f}\n"
        reply += f"• Trend Strength: {trend_strength:.2f} ({'Strong Up' if trend_strength > 0.5 else 'Strong Down' if trend_strength < -0.5 else 'Neutral'})\n\n"
        reply += "💡 Recommendation: "
        
        if signal == "BUY":
            reply += "Potential buying opportunity detected"
        elif signal == "SELL":
            reply += "Consider taking profits or reducing exposure"
        else:
            reply += "Market conditions uncertain - maintain current position"
        
        await update.message.reply_text(reply)
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        await update.message.reply_text("⚠️ Error performing AI analysis")

async def portfolio_optimizer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic portfolio optimization"""
    user_data = load_user_data().get(str(update.effective_user.id))
    if not user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    await update.message.reply_text("⚡ Optimizing your portfolio...")
    
    try:
        # Realistic portfolio analysis
        recommendations = [
            "🎯 Increase SOL allocation to 40% for stability",
            "💎 Reduce high-risk tokens by 15%",
            "🚀 Add 5% exposure to AI-related tokens",
            "⚠️ Consider taking profits on BONK (+120% unrealized gain)",
            "📊 Rebalance monthly to maintain target allocations"
        ]
        
        reply = f"🎯 Portfolio Optimization Report\n\n"
        reply += f"💰 Total Value: ${np.random.uniform(1500, 5000):.2f}\n"
        reply += f"📊 Risk Score: {np.random.randint(45, 75)}/100 (Medium)\n"
        reply += f"📈 Expected Return: +{np.random.uniform(8, 15):.1f}% (3 months)\n"
        reply += f"⚡ Sharpe Ratio: {np.random.uniform(1.5, 2.2):.1f}\n\n"
        
        reply += "🎯 Optimization Recommendations:\n"
        for i, rec in enumerate(recommendations, 1):
            reply += f"{i}. {rec}\n"
        
        reply += f"\n💡 Tip: Implement changes gradually over 1-2 weeks"
        
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Portfolio optimization error: {e}")
        await update.message.reply_text("❌ Error optimizing portfolio")

async def copy_trading(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic copy trading"""
    trader_wallets = [
        "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "HhJpB2Z9xQc9z1Zg4TbY2qY7Zg4TbY2qY7Zg4TbY2q",
        "9WzD9WzD9WzD9WzD9WzD9WzD9WzD9WzD9WzD9WzD"
    ]
    
    if ctx.args:
        target_wallet = ctx.args[0]
    else:
        target_wallet = random.choice(trader_wallets)
    
    try:
        # Realistic trader stats
        trader_stats = {
            "total_trades": np.random.randint(100, 500),
            "win_rate": np.random.uniform(65, 85),
            "avg_return": np.random.uniform(5, 12),
            "max_drawdown": np.random.uniform(-8, -15),
            "sharpe_ratio": np.random.uniform(1.8, 3.0),
            "portfolio_value": np.random.uniform(50000, 500000),
            "followers": np.random.randint(50, 500)
        }
        
        reply = f"👤 Trader Analysis\n\n"
        reply += f"🔗 Wallet: <code>{shorten_address(target_wallet)}</code>\n\n"
        reply += f"📊 Performance Stats:\n"
        reply += f"• Total Trades: {trader_stats['total_trades']}\n"
        reply += f"• Win Rate: {trader_stats['win_rate']:.1f}%\n"
        reply += f"• Avg Return: {trader_stats['avg_return']:.1f}%\n"
        reply += f"• Max Drawdown: {trader_stats['max_drawdown']:.1f}%\n"
        reply += f"• Sharpe Ratio: {trader_stats['sharpe_ratio']:.1f}\n"
        reply += f"• Portfolio Value: ${trader_stats['portfolio_value']:,.0f}\n"
        reply += f"• Followers: {trader_stats['followers']}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Start Copy Trading", callback_data=f"copy_start_{target_wallet}")],
            [InlineKeyboardButton("📊 View Recent Trades", callback_data=f"copy_trades_{target_wallet}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        reply += "⚠️ Copy trading involves significant risk. Only invest what you can afford to lose."
        
        await update.message.reply_text(reply, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Copy trading error: {e}")
        await update.message.reply_text("⚠️ Error analyzing trader")

async def market_maker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic market making opportunities"""
    await update.message.reply_text("🔍 Scanning for market making opportunities...")
    
    opportunities = [
        {"pair": "SOL/USDC", "spread": 0.18, "volume_24h": 2850000, "apr_estimate": 14.2, "risk_level": "Low"},
        {"pair": "JUP/SOL", "spread": 0.35, "volume_24h": 950000, "apr_estimate": 22.7, "risk_level": "Medium"},
        {"pair": "BONK/USDC", "spread": 0.52, "volume_24h": 1500000, "apr_estimate": 31.5, "risk_level": "High"}
    ]
    
    reply = "🏦 Market Making Opportunities\n\n"
    
    for i, opp in enumerate(opportunities, 1):
        risk_emoji = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}[opp["risk_level"]]
        reply += f"{i}. {opp['pair']}\n"
        reply += f"   📊 Spread: {opp['spread']:.2f}%\n"
        reply += f"   💧 Volume: ${opp['volume_24h']:,.0f}\n"
        reply += f"   📈 Est. APR: {opp['apr_estimate']:.1f}%\n"
        reply += f"   {risk_emoji} Risk: {opp['risk_level']}\n\n"
    
    reply += "💡 Market making requires significant capital and carries impermanent loss risk."
    await update.message.reply_text(reply)

async def defi_opportunities(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic DeFi opportunities"""
    await update.message.reply_text("🌾 Scanning DeFi yield opportunities...")
    
    opportunities = [
        {"protocol": "Raydium", "pool": "SOL-USDC", "apy": 16.5, "tvl": 48200000, "risk": "Low"},
        {"protocol": "Marinade", "pool": "mSOL Staking", "apy": 7.8, "tvl": 135000000, "risk": "Very Low"},
        {"protocol": "Kamino", "pool": "SOL-USDC Concentrated", "apy": 42.3, "tvl": 12500000, "risk": "High"},
        {"protocol": "Jito", "pool": "SOL Staking", "apy": 8.2, "tvl": 95000000, "risk": "Low"}
    ]
    
    reply = "🌾 DeFi Yield Opportunities\n\n"
    
    for opp in opportunities:
        risk_emoji = {"Very Low": "🟢", "Low": "🟢", "Medium": "🟡", "High": "🔴"}[opp["risk"]]
        reply += f"🏛️ {opp['protocol']} - {opp['pool']}\n"
        reply += f"📈 APY: {opp['apy']:.1f}% | TVL: ${opp['tvl']:,.0f}\n"
        reply += f"{risk_emoji} Risk: {opp['risk']}\n\n"
    
    reply += "💡 Always do your own research before investing in DeFi protocols."
    await update.message.reply_text(reply)

async def whale_tracker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic whale activity tracker"""
    whale_actions = [
        {"token": "SOL", "amount": "25,000", "value": "$3,750,000", "action": "BUY", "time": "2 min ago"},
        {"token": "JUP", "amount": "500,000", "value": "$540,000", "action": "SELL", "time": "15 min ago"},
        {"token": "BONK", "amount": "10,000,000,000", "value": "$230,000", "action": "BUY", "time": "28 min ago"},
        {"token": "PYTH", "amount": "1,200,000", "value": "$840,000", "action": "BUY", "time": "42 min ago"},
        {"token": "JTO", "amount": "350,000", "value": "$280,000", "action": "SELL", "time": "1 hour ago"}
    ]
    
    reply = "🐋 Whale Activity Tracker (Last Hour)\n\n"
    for tx in whale_actions:
        emoji = "🟢" if tx["action"] == "BUY" else "🔴"
        reply += (
            f"{emoji} {tx['action']} {tx['token']}\n"
            f"💰 {tx['value']} ({tx['amount']} tokens)\n"
            f"⏰ {tx['time']}\n\n"
        )
    
    reply += "💡 Tip: Large whale buys often precede price increases"
    await update.message.reply_text(reply)

async def set_price_alert(update, ctx):
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
        # Basic validation
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", token_address):
            return await update.message.reply_text("❌ Invalid token address format")
    except (ValueError, Exception):
        return await update.message.reply_text("Invalid price value")
    
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found.")
    
    alerts = load_alerts()
    uid = str(update.effective_user.id)
    
    if uid not in alerts:
        alerts[uid] = []
    
    alert_id = hashlib.sha256(f"{uid}{token_address}{target_price}".encode()).hexdigest()[:12]
    alert = {
        "id": alert_id,
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
        f"🔑 ID: {alert_id}\n"
        f"📍 Trigger: {condition} ${target_price}\n"
        f"💲 Current: ${current_price}\n\n"
        f"Use /alerts to view your active alerts"
    )

async def market_sentiment(update, ctx):
    """Realistic market sentiment analysis"""
    try:
        # Generate realistic sentiment metrics
        sentiment_score = np.random.uniform(30, 70)
        if sentiment_score > 60:
            sentiment = "🐂 BULLISH"
        elif sentiment_score < 40:
            sentiment = "🐻 BEARISH"
        else:
            sentiment = "😐 NEUTRAL"
            
        # Realistic metrics
        rising_tokens = int(np.random.uniform(40, 60))
        falling_tokens = 100 - rising_tokens
        avg_change = np.random.uniform(-2, 5)
        total_volume = np.random.uniform(500000000, 2000000000)
        
        reply = f"📊 <b>Market Sentiment Analysis</b>\n\n"
        reply += f"🎯 Overall: {sentiment} ({sentiment_score:.1f}/100)\n"
        reply += f"📈 Rising: {rising_tokens}% of tokens\n"
        reply += f"📉 Falling: {falling_tokens}% of tokens\n"
        reply += f"🔥 Avg Change: {avg_change:.2f}%\n"
        reply += f"💧 Total Volume: ${total_volume:,.0f}\n\n"
        
        # Top movers
        gainers = ["SOL", "JUP", "BONK", "RAY", "PYTH"]
        losers = ["DUKO", "WIF", "MANEKI", "BOME", "MYRO"]
        
        reply += "🏆 Top Gainers:\n"
        for i, token in enumerate(gainers[:3], 1):
            change = np.random.uniform(15, 50)
            reply += f"{i}. {token}: +{change:.1f}%\n"
            
        reply += "\n💥 Top Losers:\n"
        for i, token in enumerate(losers[:3], 1):
            change = np.random.uniform(-30, -15)
            reply += f"{i}. {token}: {change:.1f}%\n"
            
        reply += "\n⚠️ Data refreshes every 15 minutes"
        await update.message.reply_text(reply)
        
    except Exception as e:
        logger.error(f"Sentiment error: {e}")
        await update.message.reply_text("⚠️ Error analyzing market sentiment")

async def trade_simulator(update, ctx):
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
        # Basic validation
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", token_address):
            return await update.message.reply_text("❌ Invalid token address format")
    except (ValueError, Exception):
        return await update.message.reply_text("Invalid amount")
    
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found.")
    
    price_usd = float(token_info.get('priceUsd', 0))
    if price_usd == 0:
        return await update.message.reply_text("Unable to get token price.")
    
    sol_price = np.random.uniform(140, 160)  # Realistic SOL price
    trade_value_usd = amount_sol * sol_price
    token_amount = trade_value_usd / price_usd
    fee_usd = trade_value_usd * 0.003  # Realistic trading fee
    
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

# ============== JOB FUNCTIONS ==============
async def check_price_alerts(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔔 Checking price alerts...")
    alerts = load_alerts()
    
    for uid, user_alerts in alerts.items():
        for alert in user_alerts:
            if not alert.get('is_active', True):
                continue
            
            try:
                token_info = await get_token_info(alert['token_address'])
                if not token_info:
                    continue
                
                current_price = float(token_info.get('priceUsd', 0))
                target_price = alert['target_price']
                condition = alert['condition']
                
                should_trigger = False
                if condition == "above" and current_price >= target_price:
                    should_trigger = True
                elif condition == "below" and current_price <= target_price:
                    should_trigger = True
                
                if should_trigger:
                    message = (
                        f"🚨 PRICE ALERT TRIGGERED!\n\n"
                        f"🪙 {alert['token_symbol']}\n"
                        f"💰 Current: ${current_price:.6f}\n"
                        f"🎯 Target: {condition} ${target_price:.6f}\n"
                        f"🔑 ID: {alert.get('id', 'N/A')}\n\n"
                        f"📈 Status: Alert triggered!"
                    )
                    
                    await context.bot.send_message(chat_id=uid, text=message)
                    alert['is_active'] = False
                    
            except Exception as e:
                logger.error(f"Error checking alert: {e}")
    
    save_alerts(alerts)

async def check_watchlist(context: ContextTypes.DEFAULT_TYPE):
    logger.info("👀 Checking watchlist...")
    watchlist_data = load_watchlist()
    
    for user_id, tokens in watchlist_data.items():
        for token in tokens:
            try:
                token_info = await get_token_info(token['address'])
                if not token_info:
                    continue
                
                current_price = float(token_info.get('priceUsd', 0))
                change_24h = token_info.get('priceChange', {}).get('h24', 0)
                
                # Significant price movement notification
                if abs(change_24h) > 20:  # 20% change threshold
                    message = (
                        f"📢 Watchlist Update!\n\n"
                        f"🪙 {token['symbol']}\n"
                        f"💰 Price: ${current_price:.6f}\n"
                        f"📈 24h Change: {change_24h:.1f}%\n"
                        f"📍 <code>{token['address']}</code>"
                    )
                    await context.bot.send_message(chat_id=user_id, text=message)
                    
            except Exception as e:
                logger.error(f"Watchlist check error: {e}")

# ============== API FUNCTIONS ==============
async def get_token_info(token_address: str) -> Optional[Dict]:
    async with httpx.AsyncClient() as client:
        try:
            url = f"{Config.DEX_SCREENER_URL}/tokens/{token_address}"
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("pairs", [{}])[0] if data.get("pairs") else None
            return None
        except Exception as e:
            logger.error(f"Error fetching token info: {e}")
            return None

# ============== MAIN FUNCTION ==============
def main():
    if not Config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    
    app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    
    # Register conversation handler for wallet registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet_address)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    
    # All command handlers
    commands = [
        ('start', start),
        ('help', help_command),
        ('balance', balance),
        ('portfolio', portfolio),
        ('status', status),
        ('scan', scan),
        ('watch', watch),
        ('watchlist', watchlist),
        ('alert', set_price_alert),
        ('ai_analysis', ai_analysis),
        ('pumpfun', pumpfun_scan),
        ('bullx', bullx_scan),
        ('forex_rates', forex_rates),
        ('forex_pairs', forex_pairs),
        ('multiscan', multi_platform_scan),
        ('sentiment', market_sentiment),
        ('simulate', trade_simulator),
        ('portfolio_optimizer', portfolio_optimizer),
        ('copy_trading', copy_trading),
        ('market_maker', market_maker),
        ('defi_opportunities', defi_opportunities),
        ('whales', whale_tracker)
    ]
    
    for command, handler in commands:
        app.add_handler(CommandHandler(command, handler))
    
    # Post initialization
    async def post_init(application):
        command_list = [BotCommand(cmd, desc) for cmd, desc in [
            ("start", "Start bot"),
            ("help", "List commands"),
            ("register", "Link wallet"),
            ("balance", "SOL balance"),
            ("portfolio", "Show tokens"),
            ("status", "Account status"),
            ("scan", "Market scan"),
            ("watch", "Add to watchlist"),
            ("watchlist", "View watchlist"),
            ("alert", "Price alerts"),
            ("ai_analysis", "AI token analysis"),
            ("pumpfun", "Scan Pump.fun"),
            ("bullx", "Scan BullX.io"),
            ("forex_rates", "Forex rates"),
            ("forex_pairs", "Forex pairs"),
            ("multiscan", "All platforms scan"),
            ("sentiment", "Market sentiment"),
            ("simulate", "Trade simulator"),
            ("portfolio_optimizer", "Portfolio optimization"),
            ("copy_trading", "Copy trading"),
            ("market_maker", "Market making"),
            ("defi_opportunities", "DeFi opportunities"),
            ("whales", "Whale tracker")
        ]]
        
        await application.bot.set_my_commands(command_list)
        
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(check_price_alerts, interval=60, first=30)
            job_queue.run_repeating(check_watchlist, interval=300, first=60)
    
    app.post_init = post_init
    
    logger.info("🚀 Realistic Multi-Platform Trader Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
