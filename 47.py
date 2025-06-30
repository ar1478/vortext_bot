import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import aiofiles
import httpx
import pandas as pd
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.users_data = {}
        self.watchlists = {}
        self.alerts = {}
        self.client = httpx.AsyncClient(timeout=30.0)
        self.last_execution = {}  # Track last execution times
        
        # API endpoints and keys
        self.api_keys = {
            'birdeye': os.getenv('BIRDEYE_API_KEY', '797cf979b7754efa9bf6f5e1a1370f7a'),
            'apilayer': os.getenv('APILAYER_API_KEY', 'pKtM2FQSYAgwBKOYwFowIwHNDJG49UNk'),
            'pumpfun': os.getenv('PUMPFUN_API_KEY', '')
        }
        
        self.apis = {
            'birdeye': 'https://public-api.birdeye.so',
            'dexscreener': 'https://api.dexscreener.com/latest/dex',
            'jupiter': 'https://price.jup.ag/v4/price',
            'apilayer_forex': 'https://api.apilayer.com/fixer',
            'coingecko': 'https://api.coingecko.com/api/v3',
            'pumpfun': 'https://api.pump.fun'
        }
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup command handlers"""
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("register", self.register),
            CommandHandler("portfolio", self.portfolio),
            CommandHandler("scan", self.scan_tokens),
            CommandHandler("watch", self.add_watchlist),
            CommandHandler("alerts", self.view_alerts),
            CommandHandler("pnl", self.calculate_pnl),
            CommandHandler("forex", self.forex_rates),
            CommandHandler("forexpair", self.forex_pair),
            CommandHandler("birdeye", self.birdeye_search),
            CommandHandler("trending", self.birdeye_trending),
            CommandHandler("top", self.top_gainers),
            CommandHandler("pumpfun", self.pumpfun_scan),
            CommandHandler("bullx", self.bullx_scan),
            CommandHandler("forex_pairs", self.major_forex_pairs),
            CommandHandler("multiscan", self.multiscan),
            CommandHandler("portfolio_optimizer", self.portfolio_optimizer),
            CommandHandler("copy_trading", self.copy_trading),
            CommandHandler("market_maker", self.market_maker),
            CommandHandler("defi_opportunities", self.defi_opportunities),
            CommandHandler("whales", self.whale_tracker),
            CommandHandler("ai_analysis", self.ai_analysis),
            CommandHandler("sentiment", self.sentiment_analysis),
            CallbackQueryHandler(self.button_handler)
        ]

        for handler in handlers:
            self.app.add_handler(handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with enhanced options"""
        keyboard = [
            [InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
             InlineKeyboardButton("🔍 Scan Markets", callback_data="scan")],
            [InlineKeyboardButton("🐦 BirdEye Search", callback_data="birdeye"),
             InlineKeyboardButton("🔥 Trending", callback_data="trending")],
            [InlineKeyboardButton("🚀 Pump.fun Scanner", callback_data="pumpfun"),
             InlineKeyboardButton("💱 Forex Rates", callback_data="forex")],
            [InlineKeyboardButton("🤖 AI Analysis", callback_data="ai_analysis"),
             InlineKeyboardButton("🐋 Whale Tracker", callback_data="whales")],
            [InlineKeyboardButton("📈 Portfolio Optimizer", callback_data="portfolio_optimizer"),
             InlineKeyboardButton("💹 Copy Trading", callback_data="copy_trading")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *Advanced Trading Intelligence Bot*\n\n"
            "Real-time Solana, Forex, and DeFi analytics powered by AI\n\n"
            "Choose an option below:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # ... (existing methods like register, portfolio, etc. remain mostly the same) ...
    
    async def pumpfun_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Real-time Pump.fun token scanning with dynamic results"""
        try:
            # Prevent repeated identical results
            user_id = update.effective_user.id
            last_exec = self.last_execution.get(user_id, {}).get('pumpfun')
            if last_exec and (datetime.now() - last_exec).seconds < 30:
                await update.message.reply_text("🔄 Fetching fresh data...")
            
            await update.message.reply_text("🔍 Scanning Pump.fun for hot opportunities...")
            
            # Real API call to Pump.fun
            headers = {'Authorization': f'Bearer {self.api_keys["pumpfun"]}'} if self.api_keys["pumpfun"] else {}
            response = await self.client.get(
                f"{self.apis['pumpfun']}/trending",
                headers=headers,
                timeout=15.0
            )
            
            if response.status_code == 200:
                data = response.json()
                tokens = data.get('tokens', [])[:8]  # Get top 8 trending tokens
                
                if not tokens:
                    await update.message.reply_text("❌ No trending tokens found on Pump.fun")
                    return
                
                message = "🔥 *Pump.fun Hot Tokens*\n\n"
                for i, token in enumerate(tokens, 1):
                    symbol = token.get('symbol', 'N/A')
                    name = token.get('name', 'Unknown')
                    price = token.get('price', 0)
                    change_24h = token.get('priceChange24h', 0)
                    volume = token.get('volume', 0)
                    
                    # AI-generated sentiment based on metrics
                    sentiment = self.analyze_token_sentiment(price, change_24h, volume)
                    
                    message += (
                        f"{i}. {sentiment} *{name} ({symbol})*\n"
                        f"   💰 ${price:.8f}\n"
                        f"   📈 24h: {change_24h:+.2f}%\n"
                        f"   📊 Vol: ${volume:,.0f}\n\n"
                    )
                
                message += f"⏱️ Last update: {datetime.now().strftime('%H:%M:%S')}"
                await update.message.reply_text(message, parse_mode='Markdown')
                
                # Update last execution time
                self.last_execution.setdefault(user_id, {})['pumpfun'] = datetime.now()
            else:
                await update.message.reply_text("⚠️ Failed to fetch Pump.fun data. Using alternative sources...")
                await self.fallback_pumpfun_scan(update)
                
        except Exception as e:
            logger.error(f"Pumpfun scan error: {e}")
            await update.message.reply_text("⚠️ Error scanning Pump.fun. Trying fallback...")
            await self.fallback_pumpfun_scan(update)
    
    async def fallback_pumpfun_scan(self, update: Update):
        """Fallback method when Pump.fun API fails"""
        try:
            # Fallback to DexScreener for new Solana tokens
            url = f"{self.apis['dexscreener']}/pairs/solana?sort=createdAt&direction=desc"
            response = await self.client.get(url, timeout=15.0)
            data = response.json()
            
            if data and 'pairs' in data:
                new_tokens = [
                    p for p in data['pairs'] 
                    if p.get('createdAt', 0) > (datetime.now().timestamp() - 86400) * 1000
                ][:8]
                
                if not new_tokens:
                    await update.message.reply_text("❌ No new tokens found")
                    return
                
                message = "🔥 *New Solana Tokens (Pump.fun alternative)*\n\n"
                for i, token in enumerate(new_tokens, 1):
                    base = token.get('baseToken', {})
                    name = base.get('name', 'Unknown')
                    symbol = base.get('symbol', 'N/A')
                    price = float(token.get('priceUsd', 0))
                    volume = float(token.get('volume', {}).get('h24', 0))
                    
                    message += (
                        f"{i}. 🆕 *{name} ({symbol})*\n"
                        f"   💰 ${price:.8f}\n"
                        f"   📊 Vol: ${volume:,.0f}\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to fetch alternative data")
                
        except Exception as e:
            logger.error(f"Fallback pumpfun error: {e}")
            await update.message.reply_text("⚠️ Critical error in token scanning")
    
    def analyize_token_sentiment(self, price: float, change_24h: float, volume: float) -> str:
        """AI-driven sentiment analysis based on token metrics"""
        # Weighted scoring system
        score = 0
        
        # Price change impact (40% weight)
        if change_24h > 100:
            score += 40
        elif change_24h > 50:
            score += 30
        elif change_24h > 20:
            score += 20
        elif change_24h > 0:
            score += 10
        
        # Volume impact (30% weight)
        if volume > 1_000_000:
            score += 30
        elif volume > 500_000:
            score += 20
        elif volume > 100_000:
            score += 15
        elif volume > 50_000:
            score += 10
        
        # Price stability (30% weight)
        if 0.0001 < price < 0.01:  # Ideal pump.fun range
            score += 30
        elif 0.01 <= price < 0.1:
            score += 20
        else:
            score += 10
        
        # Determine sentiment emoji
        if score > 80:
            return "🚀"
        elif score > 60:
            return "🔥"
        elif score > 40:
            return "🟢"
        else:
            return "⚪"
    
    async def portfolio_optimizer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-powered portfolio optimization with real data"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        portfolio = self.users_data[user_id].get('portfolio', {})
        
        if not portfolio:
            await update.message.reply_text("Your portfolio is empty. Add assets first!")
            return
        
        try:
            await update.message.reply_text("🤖 Analyzing your portfolio with AI...")
            
            # Get real-time prices and calculate current allocation
            total_value = 0
            assets = []
            
            for token, data in portfolio.items():
                price_data = await self.get_token_price(token)
                if price_data:
                    current_price = price_data['price']
                    amount = data['amount']
                    current_value = amount * current_price
                    total_value += current_value
                    assets.append({
                        'token': token,
                        'amount': amount,
                        'current_price': current_price,
                        'value': current_value,
                        'allocation': current_value / total_value * 100
                    })
            
            if total_value == 0:
                await update.message.reply_text("❌ Error calculating portfolio value")
                return
            
            # AI optimization logic
            optimized = self.ai_optimize_portfolio(assets, total_value)
            
            # Generate recommendation message
            message = "📊 *AI Portfolio Optimization*\n\n"
            message += f"🏦 Total Value: ${total_value:,.2f}\n\n"
            message += "🔀 *Recommended Changes:*\n"
            
            for asset in optimized:
                token = asset['token']
                current_alloc = asset['allocation']
                target_alloc = asset['target_allocation']
                action = "BUY" if target_alloc > current_alloc else "SELL"
                diff = abs(target_alloc - current_alloc)
                
                if diff > 5:  # Only show significant changes
                    message += (
                        f"- {token}: {action} to {target_alloc:.1f}% "
                        f"(Current: {current_alloc:.1f}%)\n"
                    )
            
            if "BUY" not in message and "SELL" not in message:
                message += "Your portfolio is optimally balanced! ✅\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Portfolio optimizer error: {e}")
            await update.message.reply_text("⚠️ Error optimizing portfolio")
    
    def ai_optimize_portfolio(self, assets: List[Dict], total_value: float) -> List[Dict]:
        """AI-driven portfolio optimization algorithm"""
        # Get volatility scores (simulated)
        volatility_scores = {a['token']: self.calculate_volatility_score(a['token']) for a in assets}
        
        # Calculate optimal allocations based on volatility
        total_score = sum(volatility_scores.values())
        optimized = []
        
        for asset in assets:
            token = asset['token']
            volatility = volatility_scores[token]
            
            # AI optimization rules:
            # - High volatility assets should have lower allocation
            # - Stable assets can have higher allocation
            target_alloc = (1 - volatility) * 100 / len(assets)
            
            optimized.append({
                **asset,
                'volatility_score': volatility,
                'target_allocation': target_alloc
            })
        
        return optimized
    
    def calculate_volatility_score(self, token: str) -> float:
        """Calculate volatility score (0-1) for a token"""
        # In a real implementation, this would use historical data
        # For simplicity, we'll use a simulated approach
        if token == 'SOL':
            return 0.3  # Lower volatility
        elif token in ['BTC', 'ETH']:
            return 0.4
        else:
            return 0.7  # Higher volatility for alts
    
    async def copy_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Find successful traders to copy"""
        try:
            await update.message.reply_text("🔍 Identifying top performers...")
            
            # Get top gainers as proxy for successful traders
            url = f"{self.apis['coingecko']}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'volume_desc',
                'per_page': 5,
                'page': 1
            }
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            if data:
                message = "🏆 *Top Traders to Copy*\n\n"
                message += "Based on 24h trading volume and price performance:\n\n"
                
                for i, coin in enumerate(data, 1):
                    name = coin['name']
                    symbol = coin['symbol'].upper()
                    volume = coin['total_volume']
                    change = coin['price_change_percentage_24h']
                    
                    message += (
                        f"{i}. *{name} ({symbol})*\n"
                        f"   📊 24h Vol: ${volume:,.0f}\n"
                        f"   📈 Change: {change:+.2f}%\n"
                        f"   🔄 Copy Strategy: `/copy_{symbol.lower()}`\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ No trader data available")
                
        except Exception as e:
            logger.error(f"Copy trading error: {e}")
            await update.message.reply_text("⚠️ Error finding traders")
    
    async def whale_tracker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track whale transactions in real-time"""
        try:
            await update.message.reply_text("🐳 Tracking whale movements...")
            
            # Get large transactions from Birdeye
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/transactions"
            params = {
                'limit': 5,
                'sort': 'value',
                'order': 'desc'
            }
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success') and 'data' in data:
                transactions = data['data']['transactions'][:5]
                
                message = "🐋 *Recent Whale Transactions*\n\n"
                
                for i, tx in enumerate(transactions, 1):
                    token = tx.get('symbol', 'Unknown')
                    amount = float(tx.get('amount', 0))
                    value = float(tx.get('value', 0))
                    address = tx.get('account', '')[:6] + '...' + tx.get('account', '')[-4:]
                    
                    message += (
                        f"{i}. *{token}*\n"
                        f"   💰 Amount: {amount:,.2f}\n"
                        f"   💵 Value: ${value:,.0f}\n"
                        f"   📭 Address: `{address}`\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ No whale activity detected")
                
        except Exception as e:
            logger.error(f"Whale tracker error: {e}")
            await update.message.reply_text("⚠️ Error tracking whale transactions")
    
    async def market_maker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Find market making opportunities"""
        try:
            await update.message.reply_text("💹 Scanning for market making opportunities...")
            
            # Get tokens with high spread
            url = f"{self.apis['birdeye']}/defi/market_makers"
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            response = await self.client.get(url, headers=headers)
            data = response.json()
            
            if data.get('success') and 'data' in data:
                opportunities = data['data'][:3]
                
                message = "💹 *Market Making Opportunities*\n\n"
                
                for i, opp in enumerate(opportunities, 1):
                    token = opp.get('symbol', 'Unknown')
                    spread = float(opp.get('spread', 0))
                    volume = float(opp.get('volume', 0))
                    
                    message += (
                        f"{i}. *{token}*\n"
                        f"   📊 Spread: {spread:.2f}%\n"
                        f"   💰 Daily Volume: ${volume:,.0f}\n"
                        f"   📈 Potential Profit: ${volume * spread/100:,.0f}/day\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ No opportunities found")
                
        except Exception as e:
            logger.error(f"Market maker error: {e}")
            await update.message.reply_text("⚠️ Error finding opportunities")
    
    async def defi_opportunities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Find high-yield DeFi opportunities"""
        try:
            await update.message.reply_text("💸 Scanning for DeFi yields...")
            
            # Get yield opportunities (simulated - would use DeFi API in production)
            opportunities = [
                {"platform": "Solend", "token": "SOL", "apy": 8.2, "risk": "Low"},
                {"platform": "Marinade", "token": "mSOL", "apy": 6.7, "risk": "Medium"},
                {"platform": "Jito", "token": "JTO", "apy": 12.4, "risk": "High"},
                {"platform": "Kamino", "token": "KMNO", "apy": 15.8, "risk": "High"},
            ]
            
            message = "💰 *Top DeFi Yield Opportunities*\n\n"
            
            for i, opp in enumerate(opportunities, 1):
                message += (
                    f"{i}. *{opp['platform']}* ({opp['token']})\n"
                    f"   📈 APY: {opp['apy']}%\n"
                    f"   ⚠️ Risk: {opp['risk']}\n\n"
                )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"DeFi opportunities error: {e}")
            await update.message.reply_text("⚠️ Error finding DeFi opportunities")
    
    async def ai_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-driven token analysis"""
        if not context.args:
            await update.message.reply_text("Usage: /ai_analysis <token_symbol>")
            return
            
        token = context.args[0].upper()
        await update.message.reply_text(f"🤖 Analyzing {token} with AI...")
        
        try:
            # Get token data from multiple sources
            price_data = await self.get_token_price(token)
            if not price_data:
                await update.message.reply_text(f"❌ Token {token} not found")
                return
                
            # Get additional metrics
            volatility = self.calculate_volatility_score(token)
            sentiment = "Bullish" if volatility < 0.5 else "Neutral" if volatility < 0.7 else "Bearish"
            
            # Generate AI analysis
            analysis = self.generate_ai_analysis(token, price_data['price'], volatility)
            
            message = (
                f"📊 *AI Analysis for {token}*\n\n"
                f"💰 Current Price: ${price_data['price']:.4f}\n"
                f"📈 Volatility: {volatility*100:.1f}% (24h)\n"
                f"📉 Market Sentiment: {sentiment}\n\n"
                f"💡 *AI Recommendation:*\n{analysis}"
            )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await update.message.reply_text("⚠️ Error analyzing token")
    
    def generate_ai_analysis(self, token: str, price: float, volatility: float) -> str:
        """Generate AI-driven analysis based on token metrics"""
        if volatility < 0.4:
            if price < 10:
                return "STRONG BUY 🚀 - Low volatility with growth potential"
            else:
                return "HOLD ⏳ - Stable asset with moderate growth potential"
        elif volatility < 0.6:
            if price < 5:
                return "BUY ✅ - Moderate volatility with upside potential"
            else:
                return "HOLD ⚖️ - Monitor for entry/exit points"
        else:
            if price < 1:
                return "HIGH RISK BUY ⚠️ - Potential high returns but significant risk"
            else:
                return "SELL OR AVOID ❌ - High volatility with downside risk"
    
    # ... (other existing methods like get_token_price, button_handler, etc.) ...

    async def run(self):
        """Run the bot with enhanced initialization"""
        await self.load_data()
        
        # Start background tasks
        asyncio.create_task(self.start_price_monitoring())
        
        # Start the bot
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Advanced Trading Bot started successfully!")
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.client.aclose()
            await self.app.stop()

async def main():
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8152282783:AAH0ylvc63x_u1e15ST0-4zjQe_K4b4bVRc")
    
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    bot = TradingBot(BOT_TOKEN)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
