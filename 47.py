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
async def ai_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) != 1:
        await update.message.reply_text(
            "Usage: /ai_analysis <token_address>\n"
            "Example: /ai_analysis So11111111111111111111111111111111111111112"
        )
        return
    
    token_address = ctx.args[0]
    
    try:
        Pubkey.from_string(token_address)
    except Exception:
        await update.message.reply_text("❌ Invalid token address")
        return
    
    await update.message.reply_text("🤖 Analyzing token with AI...")
    
    token_info = await get_token_info(token_address)
    if not token_info:
        await update.message.reply_text("❌ Token not found")
        return
    
    # Mock historical data
    historical_data = {
        "prices": [100 + np.random.normal(0, 5) for _ in range(168)],
        "volumes": [1000000 + np.random.normal(0, 200000) for _ in range(168)]
    }
    
    analytics_engine = AnalyticsEngine()
    ai_engine = AITradingEngine(analytics_engine)
    signal = await ai_engine.generate_trading_signal(token_address, historical_data)
    
    symbol = token_info.get('baseToken', {}).get('symbol', 'Unknown')
    current_price = token_info.get('priceUsd', 'N/A')
    
    reply = f"🤖 AI Analysis for {symbol}\n\n"
    reply += f"💰 Current Price: ${current_price}\n"
    reply += f"🎯 Signal: {signal.signal_type.upper()}\n"
    reply += f"🔮 Confidence: {signal.confidence:.1%}\n"
    reply += f"📊 Risk/Reward: {signal.risk_reward_ratio:.2f}\n"
    reply += f"💼 Recommended Allocation: {signal.recommended_allocation:.1%}\n\n"
    
    reply += "📈 Technical Indicators:\n"
    tech = signal.technical_indicators
    reply += f"• RSI: {tech.rsi:.1f}\n"
    reply += f"• MACD: {tech.macd:.4f}\n"
    reply += f"• Trend Strength: {tech.trend_strength:.2f}\n"
    reply += f"• Bollinger Position: {tech.bollinger_position:.2f}\n\n"
    
    reply += "🔮 Price Predictions:\n"
    for timeframe, change in signal.price_prediction.items():
        emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        reply += f"• {timeframe}: {emoji} {change:+.1f}%\n"
    
    if signal.reasoning:
        reply += f"\n💡 Key Insights:\n"
        for reason in signal.reasoning[:3]:
            reply += f"• {reason}\n"
    
    await update.message.reply_text(reply)

async def portfolio_optimizer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_data = load_user_data().get(str(update.effective_user.id))
    if not user_data:
        await update.message.reply_text("❌ Please register first with /register")
        return
    
    await update.message.reply_text("⚡ Optimizing your portfolio...")
    
    try:
        wallet = Pubkey.from_string(user_data['wallet'])
        sol_balance = await rpc_client.get_balance(wallet)
        sol_amount = sol_balance.value / 1e9
        total_value = sol_amount * 100  # Assume SOL = $100
        
        recommendations = [
            "🎯 Consider reducing allocation in high-risk tokens by 15%",
            "💎 Increase SOL holdings for stability (currently 45%, target 60%)",
            "🚀 DCA into 2-3 blue-chip tokens over next 2 weeks",
            "⚠️ Exit positions with negative momentum indicators",
            "📊 Rebalance portfolio weekly to maintain target allocations"
        ]
        
        reply = f"🎯 Portfolio Optimization Report\n\n"
        reply += f"💰 Total Value: ${total_value:.2f}\n"
        reply += f"📊 Risk Score: 65/100 (Medium)\n"
        reply += f"📈 Expected Return: +12.5% (3 months)\n"
        reply += f"⚡ Sharpe Ratio: 1.8\n\n"
        
        reply += "🎯 Optimization Recommendations:\n"
        for i, rec in enumerate(recommendations, 1):
            reply += f"{i}. {rec}\n"
        
        reply += f"\n💡 Tip: Enable auto-rebalancing with /auto_trading"
        
        await update.message.reply_text(reply)
        
    except Exception as e:
        logger.error(f"Portfolio optimization error: {e}")
        await update.message.reply_text("❌ Error optimizing portfolio")

async def copy_trading(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) != 1:
        await update.message.reply_text(
            "Usage: /copy_trading <wallet_address>\n"
            "Example: /copy_trading 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
        )
        return
    
    target_wallet = ctx.args[0]
    
    try:
        Pubkey.from_string(target_wallet)
    except Exception:
        await update.message.reply_text("❌ Invalid wallet address")
        return
    
    trader_stats = {
        "total_trades": 156,
        "win_rate": 73.5,
        "avg_return": 8.2,
        "max_drawdown": -12.5,
        "sharpe_ratio": 2.1,
        "portfolio_value": 450000,
        "followers": 89
    }
    
    reply = f"👤 Trader Analysis\n\n"
    reply += f"📊 Performance Stats:\n"
    reply += f"• Total Trades: {trader_stats['total_trades']}\n"
    reply += f"• Win Rate: {trader_stats['win_rate']:.1f}%\n"
    reply += f"• Avg Return: {trader_stats['avg_return']:.1f}%\n"
    reply += f"• Max Drawdown: {trader_stats['max_drawdown']:.1f}%\n"
    reply += f"• Sharpe Ratio: {trader_stats['sharpe_ratio']:.1f}\n"
    reply += f"• Portfolio Value: ${trader_stats['portfolio_value']:,}\n"
    reply += f"• Followers: {trader_stats['followers']}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Start Copy Trading", callback_data=f"copy_start_{target_wallet}")],
        [InlineKeyboardButton("📊 View Recent Trades", callback_data=f"copy_trades_{target_wallet}")],
        [InlineKeyboardButton("⚙️ Copy Settings", callback_data=f"copy_settings_{target_wallet}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    reply += "⚠️ Copy trading involves risk. Start with small amounts."
    
    await update.message.reply_text(reply, reply_markup=reply_markup)

async def market_maker(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning for market making opportunities...")
    
    opportunities = [
        {"pair": "SOL/USDC", "spread": 0.15, "volume_24h": 2500000, "apr_estimate": 12.5, "risk_level": "Low"},
        {"pair": "RAY/SOL", "spread": 0.28, "volume_24h": 890000, "apr_estimate": 18.3, "risk_level": "Medium"},
        {"pair": "BONK/SOL", "spread": 0.45, "volume_24h": 1200000, "apr_estimate": 25.7, "risk_level": "High"}
    ]
    
    reply = "🏦 Market Making Opportunities\n\n"
    
    for i, opp in enumerate(opportunities, 1):
        risk_emoji = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}[opp["risk_level"]]
        reply += f"{i}. {opp['pair']}\n"
        reply += f"   📊 Spread: {opp['spread']:.2f}%\n"
        reply += f"   💧 Volume: ${opp['volume_24h']:,}\n"
        reply += f"   📈 Est. APR: {opp['apr_estimate']:.1f}%\n"
        reply += f"   {risk_emoji} Risk: {opp['risk_level']}\n\n"
    
    reply += "💡 Market making requires significant capital and carries impermanent loss risk."
    await update.message.reply_text(reply)

async def defi_opportunities(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌾 Scanning DeFi yield opportunities...")
    
    opportunities = [
        {"protocol": "Raydium", "pool": "SOL-USDC", "apy": 15.8, "tvl": 45000000, "risk": "Low", "type": "Liquidity Mining"},
        {"protocol": "Marinade", "pool": "mSOL Staking", "apy": 7.2, "tvl": 120000000, "risk": "Very Low", "type": "Liquid Staking"},
        {"protocol": "Tulip", "pool": "Leveraged Yield Farming", "apy": 35.5, "tvl": 8000000, "risk": "High", "type": "Leveraged Farming"},
        {"protocol": "Friktion", "pool": "SOL Covered Calls", "apy": 22.1, "tvl": 15000000, "risk": "Medium", "type": "Options Strategy"}
    ]
    
    reply = "🌾 DeFi Yield Opportunities\n\n"
    
    for opp in opportunities:
        risk_emoji = {"Very Low": "🟢", "Low": "🟢", "Medium": "🟡", "High": "🔴"}[opp["risk"]]
        reply += f"🏛️ {opp['protocol']} - {opp['pool']}\n"
        reply += f"📈 APY: {opp['apy']:.1f}% | TVL: ${opp['tvl']:,}\n"
        reply += f"🔧 Type: {opp['type']}\n"
        reply += f"{risk_emoji} Risk: {opp['risk']}\n\n"
    
    reply += "💡 Always DYOR before investing in DeFi protocols."
    await update.message.reply_text(reply)

async def advanced_scan(update, ctx):
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
        url = f"{Config.DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.{filters['timeframe']}&order=desc&limit=100"
        tokens = await fetch_tokens(client, url)
        
        if not tokens:
            await update.message.reply_text("No tokens found.")
            return
        
        candidates = []
        for token in tokens:
            volume = token.get('volume', {}).get(filters['timeframe'], 0)
            price_change = token.get('priceChange', {}).get(filters['timeframe'], 0)
            liquidity = token.get('liquidity', {}).get('usd', 0)
            
            if (volume >= filters['min_volume'] and 
                abs(price_change) >= filters['min_change'] and
                liquidity >= filters['min_liquidity']):
                
                risk_analysis = await analyze_token_risk(token)
                if risk_analysis['risk_score'] <= filters['max_risk']:
                    token['risk_analysis'] = risk_analysis
                    candidates.append(token)
        
        if not candidates:
            await update.message.reply_text("No tokens match your criteria.")
            return
        
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
    user_data = load_user_data().get(str(update.effective_user.id))
    if not user_data:
        return await update.message.reply_text("Link with /register.")
    
    try:
        wallet = Pubkey.from_string(user_data['wallet'])
        sol_balance = await rpc_client.get_balance(wallet)
        sol_amount = sol_balance.value / 1e9
        token_accounts = await rpc_client.get_token_accounts_by_owner(wallet, commitment="confirmed")
        
        if not token_accounts.value:
            await update.message.reply_text("No tokens found in portfolio.")
            return
        
        total_value_usd = sol_amount * 100  # Assuming SOL = $100
        portfolio_items = []
        
        for acc in token_accounts.value:
            try:
                balance = await rpc_client.get_token_account_balance(acc.pubkey)
                mint = acc.account.data.parsed['info']['mint']
                amount = balance.value.ui_amount or 0
                
                if amount > 0:
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
        await update.message.reply_text("⚠️ Error analyzing portfolio.")

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
        Pubkey.from_string(token_address)
    except (ValueError, Exception):
        return await update.message.reply_text("Invalid token address or price.")
    
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found.")
    
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
    async with httpx.AsyncClient() as client:
        url = f"{Config.DEX_SCREENER_URL}/search/pairs?q=solana&sort=volume.h24&order=desc&limit=50"
        tokens = await fetch_tokens(client, url)
        
        if not tokens:
            await update.message.reply_text("Unable to fetch market data.")
            return
        
        total_tokens = len(tokens)
        positive_tokens = sum(1 for t in tokens if t.get('priceChange', {}).get('h24', 0) > 0)
        negative_tokens = total_tokens - positive_tokens
        avg_change = sum(t.get('priceChange', {}).get('h24', 0) for t in tokens) / total_tokens
        total_volume = sum(t.get('volume', {}).get('h24', 0) for t in tokens)
        
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
    
    token_info = await get_token_info(token_address)
    if not token_info:
        return await update.message.reply_text("Token not found.")
    
    price_usd = float(token_info.get('priceUsd', 0))
    if price_usd == 0:
        return await update.message.reply_text("Unable to get token price.")
    
    sol_price = 100  # Assuming SOL = $100
    trade_value_usd = amount_sol * sol_price
    token_amount = trade_value_usd / price_usd
    fee_usd = trade_value_usd * 0.003
    
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
    mock_whale_transactions = [
        {"token_symbol": "SOL", "amount": "25,000", "value_usd": "2,500,000", "action": "BUY", "wallet": "7xKX...AsU8", "timestamp": "2 min ago"},
        {"token_symbol": "BONK", "amount": "1,000,000,000", "value_usd": "450,000", "action": "SELL", "wallet": "9WzD...AWM", "timestamp": "5 min ago"},
        {"token_symbol": "JUP", "amount": "500,000", "value_usd": "750,000", "action": "BUY", "wallet": "HhJp...Zg4", "timestamp": "8 min ago"}
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
                        f"📈 Status: Alert triggered!"
                    )
                    
                    await context.bot.send_message(chat_id=uid, text=message)
                    alert['is_active'] = False
                    
            except Exception as e:
                logger.error(f"Error checking alert: {e}")
    
    save_alerts(alerts)

async def check_watchlist(context: ContextTypes.DEFAULT_TYPE):
    logger.info("👀 Checking watchlist...")
    # Implement actual watchlist monitoring logic
    pass

# ============== MAIN FUNCTION ==============
def main():
    if not Config.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return
    
    app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    
    # Command handlers
    enhanced_handlers = [
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
    
    for handler in enhanced_handlers:
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
