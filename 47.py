import os, json, logging, httpx, re, asyncio, hashlib, hmac
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
    DEX_SCREENER_URL = "https://api.dexscreener.com/latest/dex"
    BIRDEYE_API_URL = "https://public-api.birdeye.so"
    BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
    
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

# ============== BASIC COMMAND HANDLERS ==============
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
        # Validate wallet address
        Pubkey.from_string(wallet_address)
        
        # Save user data
        user_data = load_user_data()
        user_data[user_id] = {
            "wallet": wallet_address,
            "registered_at": datetime.now().isoformat()
        }
        save_user_data(user_data)
        
        await update.message.reply_text(
            "✅ Wallet linked successfully!\n\n"
            "⚙️ Configure your settings with /settings\n"
            "💼 Check your portfolio with /portfolio"
        )
        return ConversationHandler.END
    
    except Exception:
        await update.message.reply_text("❌ Invalid Solana address. Please try again.")
        return REGISTER

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration canceled.")
    return ConversationHandler.END

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data or "wallet" not in user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    try:
        wallet = Pubkey.from_string(user_data['wallet'])
        balance = await rpc_client.get_balance(wallet)
        sol_balance = balance.value / 1e9
        
        # Get SOL price (mock)
        sol_price = 100  # In real bot, fetch from API
        
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
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data or "wallet" not in user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    try:
        wallet = Pubkey.from_string(user_data['wallet'])
        token_accounts = await rpc_client.get_token_accounts_by_owner(wallet, commitment="confirmed")
        
        if not token_accounts.value:
            await update.message.reply_text("Your portfolio is empty.")
            return
        
        portfolio_items = []
        for acc in token_accounts.value:
            try:
                balance = await rpc_client.get_token_account_balance(acc.pubkey)
                mint = acc.account.data.parsed['info']['mint']
                amount = balance.value.ui_amount or 0
                
                if amount > 0:
                    portfolio_items.append({
                        'mint': str(mint),
                        'amount': amount
                    })
            except Exception as e:
                logger.error(f"Error processing token account: {e}")
                continue
        
        reply = "📊 <b>Your Portfolio</b>\n\n"
        if portfolio_items:
            for item in portfolio_items[:5]:  # Limit to 5 for initial response
                token_info = await get_token_info(item['mint'])
                symbol = token_info.get('baseToken', {}).get('symbol', 'Unknown') if token_info else 'Unknown'
                reply += f"• {symbol}: {item['amount']:.2f}\n"
            
            if len(portfolio_items) > 5:
                reply += f"\n📦 ...and {len(portfolio_items) - 5} more tokens"
        else:
            reply += "No tokens found in your wallet."
        
        await update.message.reply_html(reply)
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        await update.message.reply_text("⚠️ Error fetching portfolio. Try again later.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = load_user_data().get(user_id)
    
    if not user_data:
        await update.message.reply_text("❌ You're not registered. Use /register")
        return
    
    wallet = user_data.get('wallet', 'Not set')
    created_at = datetime.fromisoformat(user_data['registered_at']).strftime("%Y-%m-%d %H:%M")
    
    # Get watchlist count
    watchlist = load_watchlist().get(user_id, [])
    
    # Get alerts count
    alerts = [a for a in load_alerts().get(user_id, []) if a.get('is_active', True)]
    
    status_text = (
        f"👤 <b>Account Status</b>\n\n"
        f"🆔 User ID: {user_id}\n"
        f"🔗 Wallet: <code>{wallet}</code>\n"
        f"📅 Registered: {created_at}\n"
        f"🔔 Active Alerts: {len(alerts)}\n"
        f"👀 Watchlist Items: {len(watchlist)}\n\n"
        f"⚙️ Configure with /settings"
    )
    
    await update.message.reply_html(status_text)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient() as client:
            url = f"{Config.DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.h24&order=desc&limit=10"
            tokens = await fetch_tokens(client, url)
            
            if not tokens:
                await update.message.reply_text("No tokens found. Try again later.")
                return
            
            reply = "🔍 <b>Top Trending Tokens</b>\n\n"
            for i, token in enumerate(tokens[:5], 1):
                symbol = token.get('baseToken', {}).get('symbol', 'Unknown')
                price = token.get('priceUsd', 'N/A')
                change = token.get('priceChange', {}).get('h24', 'N/A')
                liquidity = token.get('liquidity', {}).get('usd', 0)
                
                reply += (
                    f"{i}. <b>{symbol}</b>\n"
                    f"   💲 Price: ${price}\n"
                    f"   📈 24h: {change}%\n"
                    f"   💧 Liquidity: ${liquidity:,.0f}\n"
                    f"   📍 <code>{token.get('baseToken', {}).get('address', 'N/A')}</code>\n\n"
                )
            
            await update.message.reply_html(reply)
            
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await update.message.reply_text("⚠️ Error scanning tokens. Try again later.")

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /watch <token_address>")
        return
    
    token_address = context.args[0]
    user_id = str(update.effective_user.id)
    
    try:
        Pubkey.from_string(token_address)
        token_info = await get_token_info(token_address)
        
        if not token_info:
            await update.message.reply_text("❌ Token not found")
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
        await update.message.reply_text("❌ Invalid token address")

async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist = load_watchlist().get(user_id, [])
    
    if not watchlist:
        await update.message.reply_text("Your watchlist is empty. Add tokens with /watch")
        return
    
    reply = "👀 <b>Your Watchlist</b>\n\n"
    for i, token in enumerate(watchlist, 1):
        reply += (
            f"{i}. <b>{token['symbol']}</b>\n"
            f"   📍 <code>{token['address']}</code>\n"
            f"   📅 Added: {datetime.fromisoformat(token['added_at']).strftime('%Y-%m-%d')}\n\n"
        )
    
    await update.message.reply_html(reply)

# ============== ANALYTICS ENGINE (Redis-free) ==============
class AnalyticsEngine:
    def __init__(self):
        # Simple in-memory cache instead of Redis
        self.cache = {}
    
    async def calculate_technical_indicators(self, price_data: List[float]) -> TechnicalIndicators:
        if len(price_data) < 14:
            return TechnicalIndicators()
        
        prices = np.array(price_data)
        rsi = self._calculate_rsi(prices)
        macd = self._calculate_macd(prices)
        bollinger_pos = self._calculate_bollinger_position(prices)
        support, resistance = self._find_support_resistance(prices)
        trend_strength = self._calculate_trend_strength(prices)
        
        return TechnicalIndicators(
            rsi=rsi,
            macd=macd,
            bollinger_position=bollinger_pos,
            support_level=support,
            resistance_level=resistance,
            trend_strength=trend_strength
        )
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = np.mean(gains[-period:])
        avg_losses = np.mean(losses[-period:])
        
        if avg_losses == 0:
            return 100.0
        
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)
    
    def _calculate_macd(self, prices: np.ndarray) -> float:
        if len(prices) < 26:
            return 0.0
        
        ema12 = self._ema(prices, 12)
        ema26 = self._ema(prices, 26)
        macd = ema12 - ema26
        return float(macd)
    
    def _ema(self, prices: np.ndarray, period: int) -> float:
        alpha = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    def _calculate_bollinger_position(self, prices: np.ndarray, period: int = 20) -> float:
        if len(prices) < period:
            return 0.0
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        upper_band = sma + (2 * std)
        lower_band = sma - (2 * std)
        current_price = prices[-1]
        
        if upper_band == lower_band:
            return 0.0
        
        position = (current_price - lower_band) / (upper_band - lower_band)
        return float(np.clip(position * 2 - 1, -1, 1))
    
    def _find_support_resistance(self, prices: np.ndarray) -> Tuple[float, float]:
        if len(prices) < 10:
            return float(np.min(prices)), float(np.max(prices))
        
        highs = []
        lows = []
        
        for i in range(2, len(prices) - 2):
            if prices[i] > prices[i-1] and prices[i] > prices[i+1]:
                highs.append(prices[i])
            elif prices[i] < prices[i-1] and prices[i] < prices[i+1]:
                lows.append(prices[i])
        
        resistance = float(np.mean(highs[-3:])) if highs else float(np.max(prices))
        support = float(np.mean(lows[-3:])) if lows else float(np.min(prices))
        
        return support, resistance
    
    def _calculate_trend_strength(self, prices: np.ndarray) -> float:
        if len(prices) < 10:
            return 0.0
        
        x = np.arange(len(prices))
        slope, _, r_value, _, _ = stats.linregress(x, prices)
        trend_strength = np.tanh(slope * 1000) * (r_value ** 2)
        return float(np.clip(trend_strength, -1, 1))

# ============== AI TRADING ENGINE ==============
class AITradingEngine:
    def __init__(self, analytics_engine: AnalyticsEngine):
        self.analytics = analytics_engine
        self.models = {}
    
    async def generate_trading_signal(self, token_address: str, historical_data: Dict) -> TradingSignal:
        try:
            prices = historical_data.get('prices', [])
            volumes = historical_data.get('volumes', [])
            
            if len(prices) < Config.MIN_DATA_POINTS:
                return self._create_neutral_signal(token_address)
            
            tech_indicators = await self.analytics.calculate_technical_indicators(prices)
            market_sentiment = await self._analyze_market_sentiment(token_address)
            predictions = await self._predict_prices(prices)
            signal_type, confidence, reasoning = self._analyze_signals(
                tech_indicators, market_sentiment, predictions
            )
            risk_reward = self._calculate_risk_reward(predictions, prices[-1])
            allocation = self._calculate_allocation(confidence, risk_reward)
            
            return TradingSignal(
                token_address=token_address,
                signal_type=signal_type,
                confidence=confidence,
                reasoning=reasoning,
                technical_indicators=tech_indicators,
                market_sentiment=market_sentiment,
                price_prediction=predictions,
                risk_reward_ratio=risk_reward,
                recommended_allocation=allocation
            )
        
        except Exception as e:
            logging.error(f"AI signal generation error: {e}")
            return self._create_neutral_signal(token_address)
    
    def _create_neutral_signal(self, token_address: str) -> TradingSignal:
        return TradingSignal(
            token_address=token_address,
            signal_type="hold",
            confidence=0.5,
            reasoning=["Insufficient data for analysis"],
            technical_indicators=TechnicalIndicators(),
            market_sentiment=MarketSentiment(),
            price_prediction={"1h": 0, "4h": 0, "24h": 0},
            risk_reward_ratio=1.0,
            recommended_allocation=0.0
        )
    
    async def _analyze_market_sentiment(self, token_address: str) -> MarketSentiment:
        # Placeholder for sentiment analysis integration
        return MarketSentiment()
    
    async def _predict_prices(self, prices: List[float]) -> Dict[str, float]:
        if len(prices) < 24:
            return {"1h": 0, "4h": 0, "24h": 0}
        
        try:
            X = np.arange(len(prices)).reshape(-1, 1)
            y = np.array(prices)
            model = LinearRegression()
            model.fit(X, y)
            
            current_price = prices[-1]
            future_1h = model.predict([[len(prices)]])[0]
            future_4h = model.predict([[len(prices) + 3]])[0]
            future_24h = model.predict([[len(prices) + 23]])[0]
            
            return {
                "1h": float((future_1h - current_price) / current_price * 100),
                "4h": float((future_4h - current_price) / current_price * 100),
                "24h": float((future_24h - current_price) / current_price * 100)
            }
        
        except Exception:
            return {"1h": 0, "4h": 0, "24h": 0}
    
    def _analyze_signals(self, tech: TechnicalIndicators, sentiment: MarketSentiment, 
                        predictions: Dict) -> Tuple[str, float, List[str]]:
        signals = []
        reasoning = []
        
        # Technical analysis
        if tech.rsi < 30:
            signals.append(0.7)
            reasoning.append("RSI indicates oversold conditions")
        elif tech.rsi > 70:
            signals.append(-0.7)
            reasoning.append("RSI indicates overbought conditions")
        
        if tech.trend_strength > 0.5:
            signals.append(0.6)
            reasoning.append("Strong upward trend detected")
        elif tech.trend_strength < -0.5:
            signals.append(-0.6)
            reasoning.append("Strong downward trend detected")
        
        if tech.bollinger_position < -0.8:
            signals.append(0.5)
            reasoning.append("Price near lower Bollinger Band")
        elif tech.bollinger_position > 0.8:
            signals.append(-0.5)
            reasoning.append("Price near upper Bollinger Band")
        
        # Price predictions
        if predictions["24h"] > 10:
            signals.append(0.8)
            reasoning.append("AI predicts significant price increase")
        elif predictions["24h"] < -10:
            signals.append(-0.8)
            reasoning.append("AI predicts significant price decrease")
        
        # Calculate overall signal
        if not signals:
            return "hold", 0.5, ["No clear signals detected"]
        
        avg_signal = np.mean(signals)
        confidence = min(abs(avg_signal), 1.0)
        
        if avg_signal > 0.3:
            signal_type = "buy"
        elif avg_signal < -0.3:
            signal_type = "sell"
        else:
            signal_type = "hold"
        
        return signal_type, confidence, reasoning
    
    def _calculate_risk_reward(self, predictions: Dict, current_price: float) -> float:
        predicted_change = predictions.get("24h", 0)
        
        if predicted_change > 0:
            reward = abs(predicted_change)
            risk = 5.0  # Assume 5% downside risk
            return reward / risk if risk > 0 else 1.0
        else:
            return 0.5
    
    def _calculate_allocation(self, confidence: float, risk_reward: float) -> float:
        if confidence < Config.CONFIDENCE_THRESHOLD:
            return 0.0
        
        # Kelly Criterion inspired allocation
        win_prob = (confidence + 1) / 2
        allocation = (win_prob * risk_reward - (1 - win_prob)) / risk_reward
        
        return max(0.0, min(0.2, allocation))

# ============== API FUNCTIONS ==============
async def get_token_info(token_address: str) -> Optional[Dict]:
    async with httpx.AsyncClient() as client:
        try:
            url = f"{Config.DEX_SCREENER_URL}/tokens/{token_address}"
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
    async with httpx.AsyncClient() as client:
        try:
            url = f"{Config.JUPITER_API_URL}/quote"
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
    if risk_level == "HIGH":
        return "⚠️ High risk - Consider small position or avoid"
    elif risk_level == "MEDIUM":
        return "⚡ Medium risk - Trade with caution"
    else:
        return "✅ Low risk - Good for larger positions"

async def generate_price_chart(token_data: Dict) -> Optional[bytes]:
    try:
        # Mock data for demonstration
        prices = [100, 105, 98, 110, 115, 108, 120, 125, 118, 130]
        times = list(range(len(prices)))
        
        plt.figure(figsize=(10, 6))
        plt.plot(times, prices, 'b-', linewidth=2)
        plt.title(f"{token_data.get('baseToken', {}).get('symbol', 'TOKEN')} Price Chart")
        plt.xlabel('Time')
        plt.ylabel('Price ($)')
        plt.grid(True, alpha=0.3)
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        chart_bytes = buffer.getvalue()
        plt.close()
        
        return chart_bytes
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        return None

async def fetch_tokens(client, url):
    try:
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        return data.get("pairs", []) or data.get("tokens", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching tokens: {e}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON response")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return []

# ============== COMMAND HANDLERS ==============
# ... [All the previous advanced commands from earlier code remain here] ...

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
    
    # Basic command handlers
    basic_handlers = [
        CommandHandler('start', start),
        CommandHandler('help', help_command),
        CommandHandler('balance', balance),
        CommandHandler('portfolio', portfolio),
        CommandHandler('status', status),
        CommandHandler('scan', scan),
        CommandHandler('watch', watch),
        CommandHandler('watchlist', watchlist),
    ]
    
    for handler in basic_handlers:
        app.add_handler(handler)
    
    # Advanced command handlers
    advanced_handlers = [
        CommandHandler('ai_analysis', ai_analysis),
        CommandHandler('portfolio_optimizer', portfolio_optimizer),
        CommandHandler('copy_trading', copy_trading),
        CommandHandler('market_maker', market_maker),
        CommandHandler('defi_opportunities', defi_opportunities),
        CommandHandler('advanced_scan', advanced_scan),
        CommandHandler('portfolio_analysis', portfolio_analysis),
        CommandHandler('alert', set_price_alert),
        CommandHandler('sentiment', market_sentiment),
        CommandHandler('simulate', trade_simulator),
        CommandHandler('whales', whale_tracker),
    ]
    
    for handler in advanced_handlers:
        app.add_handler(handler)
    
    # Post initialization
    async def post_init(application):
        all_commands = [
            ("start", "Start bot"), ("help", "List commands"), ("register", "Link wallet"),
            ("balance", "SOL balance"), ("portfolio", "Show tokens"), ("status", "Wallet summary"),
            ("scan", "Basic scan"), ("advanced_scan", "Advanced scanner"),
            ("sentiment", "Market sentiment"), ("whales", "Whale tracker"),
            ("alert", "Price alerts"), ("simulate", "Trade simulator"),
            ("watch", "Add to watchlist"), ("watchlist", "View watchlist"),
            ("ai_analysis", "AI token analysis"), ("portfolio_optimizer", "Portfolio optimization"),
            ("copy_trading", "Copy trading"), ("market_maker", "Market making opportunities"),
            ("defi_opportunities", "DeFi yield opportunities")
        ]
        
        await application.bot.set_my_commands([BotCommand(c, d) for c, d in all_commands])
        
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(check_price_alerts, interval=60, first=30)
            job_queue.run_repeating(check_watchlist, interval=300, first=60)
    
    app.post_init = post_init
    
    logger.info("🚀 UltimateSolanaTraderBot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
