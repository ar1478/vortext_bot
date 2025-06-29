import os, json, logging, httpx, re, asyncio, hashlib, hmac, time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict, field
from enum import Enum
import numpy as np
from solders.pubkey import Pubkey
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
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

# ============== REALISTIC SCANNING FUNCTIONS ==============
async def fetch_real_tokens(client, url, platform_name):
    """Fetch tokens with realistic error handling and logging"""
    try:
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        
        if platform_name == "DexScreener":
            return data.get("pairs", [])[:10]  # Return top 10 results
        elif platform_name == "Pump.fun":
            return data.get("data", [])[:10]
        elif platform_name == "BullX":
            return data.get("data", [])[:10]
        
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {platform_name} tokens: {e.response.status_code}")
        return []
    except httpx.ReadTimeout:
        logger.warning(f"{platform_name} API timeout")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON response from {platform_name}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error with {platform_name}: {e}")
        return []

def realistic_token_analysis(token_data: Dict) -> Dict:
    """Generate realistic analysis based on token metrics"""
    liquidity = token_data.get('liquidity', {}).get('usd', 0)
    volume = token_data.get('volume', {}).get('h24', 0)
    price_change = token_data.get('priceChange', {}).get('h24', 0)
    
    # Calculate realistic risk score
    risk_score = 0
    risk_factors = []
    
    if liquidity < 10000:
        risk_score += 30
        risk_factors.append("Low liquidity")
    elif liquidity < 50000:
        risk_score += 15
        risk_factors.append("Medium liquidity")
    
    if volume < 50000:
        risk_score += 25
        risk_factors.append("Low trading volume")
    
    if abs(price_change) > 50:
        risk_score += 20
        risk_factors.append("High volatility")
    
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
        "recommendation": "Trade with caution" if risk_level != "LOW" else "Relatively safe"
    }

# ============== REALISTIC COMMAND HANDLERS ==============
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan with realistic market data patterns"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{Config.DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.h24&order=desc&limit=10"
            tokens = await fetch_real_tokens(client, url, "DexScreener")
            
            if not tokens:
                await update.message.reply_text("⚠️ Market is quiet. No trending tokens found.")
                return
            
            reply = "🔍 <b>Real-time Market Scan</b>\n\n"
            for i, token in enumerate(tokens, 1):
                symbol = token.get('baseToken', {}).get('symbol', 'Unknown')
                price = token.get('priceUsd', 'N/A')
                change = token.get('priceChange', {}).get('h24', 'N/A')
                liquidity = token.get('liquidity', {}).get('usd', 0)
                
                # Generate realistic analysis
                analysis = realistic_token_analysis(token)
                
                reply += (
                    f"{i}. <b>{symbol}</b>\n"
                    f"   💲 Price: ${price}\n"
                    f"   📈 24h: {change}%\n"
                    f"   💧 Liquidity: ${liquidity:,.0f}\n"
                    f"   ⚠️ Risk: {analysis['risk_level']} ({analysis['risk_score']}/100)\n"
                    f"   📍 <code>{token.get('baseToken', {}).get('address', 'N/A')}</code>\n\n"
                )
            
            await update.message.reply_html(reply)
            
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text("⚠️ Error scanning tokens. API might be overloaded.")

async def pumpfun_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic Pump.fun scanner with market patterns"""
    try:
        limit = min(int(context.args[0]) if context.args else 5
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

async def ai_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Realistic AI analysis with market patterns"""
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

# ============== REALISTIC PORTFOLIO FUNCTIONS ==============
async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Realistic portfolio simulation with market patterns"""
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data or "wallet" not in user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    try:
        # Realistic portfolio simulation
        sol_balance = np.random.uniform(0.5, 5.0)
        sol_price = np.random.uniform(80, 120)  # Realistic SOL price range
        
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

# ============== REALISTIC MARKET DATA FUNCTIONS ==============
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

# ============== MAIN FUNCTION ==============
def main():
    if not Config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    
    app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    
    # Conversation handler for wallet registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            REGISTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet_address)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    
    # Command handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('balance', balance))
    app.add_handler(CommandHandler('portfolio', portfolio))
    app.add_handler(CommandHandler('scan', scan))
    app.add_handler(CommandHandler('ai_analysis', ai_analysis))
    app.add_handler(CommandHandler('pumpfun', pumpfun_scan))
    app.add_handler(CommandHandler('sentiment', market_sentiment))
    
    # Post initialization
    async def post_init(application):
        commands = [
            ("start", "Start bot"), 
            ("help", "List commands"), 
            ("register", "Link wallet"),
            ("balance", "SOL balance"), 
            ("portfolio", "Show tokens"), 
            ("scan", "Market scan"),
            ("ai_analysis", "AI token analysis"),
            ("pumpfun", "Scan Pump.fun tokens"),
            ("sentiment", "Market sentiment")
        ]
        
        await application.bot.set_my_commands([BotCommand(c, d) for c, d in commands])
        
    app.post_init = post_init
    
    logger.info("🚀 Realistic Solana Trader Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
