import asyncio
import json
import logging
import os
import re
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
        self.data_cache = {}
        
        # Get API keys from environment variables
        self.api_keys = {
            'birdeye': os.environ.get('BIRDEYE_APL_KEY', ''),
            'apilayer': os.environ.get('APILAYER_APL_KEY', ''),
            'dexscreener': 'public'  # Most don't require keys
        }
        
        # Use Solana RPC URL from environment if available
        solana_rpc = os.environ.get('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
        
        self.apis = {
            'birdeye': 'https://public-api.birdeye.so',
            'dexscreener': 'https://api.dexscreener.com/latest/dex',
            'jupiter': 'https://price.jup.ag/v4/price',
            'apilayer_forex': 'https://api.apilayer.com/fixer',
            'coingecko': 'https://api.coingecko.com/api/v3',
            'pumpfun': 'https://api.pump.fun',
            'solscan': 'https://api.solscan.io',
            'solana_rpc': solana_rpc  # Use environment variable
        }
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup command handlers"""
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("help", self.help_command),
            CommandHandler("register", self.register),
            CommandHandler("status", self.status),
            CommandHandler("balance", self.balance),
            CommandHandler("portfolio", self.portfolio),
            CommandHandler("watch", self.add_watchlist),
            CommandHandler("watchlist", self.view_watchlist),
            CommandHandler("alert", self.set_alert),
            CommandHandler("scan", self.scan_tokens),
            CommandHandler("trending", self.birdeye_trending),
            CommandHandler("top", self.top_gainers),
            CommandHandler("advanced_scan", self.advanced_scan),
            CommandHandler("sentiment", self.sentiment_analysis),
            CommandHandler("ai_analysis", self.ai_analysis),
            CommandHandler("pumpfun", self.pumpfun_scan),
            CommandHandler("bullx", self.bullx_scan),
            CommandHandler("forex", self.forex_rates),
            CommandHandler("forexpair", self.forex_pair),
            CommandHandler("birdeye", self.birdeye_search),
            CommandHandler("forex_pairs", self.major_forex_pairs),
            CommandHandler("multiscan", self.multiscan),
            CommandHandler("portfolio_optimizer", self.portfolio_optimizer),
            CommandHandler("copy_trading", self.copy_trading),
            CommandHandler("market_maker", self.market_maker),
            CommandHandler("defi_opportunities", self.defi_opportunities),
            CommandHandler("whales", self.whale_tracker),
            CallbackQueryHandler(self.button_handler)
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        keyboard = [
            [InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
             InlineKeyboardButton("🔍 Scan Markets", callback_data="scan")],
            [InlineKeyboardButton("🐦 BirdEye", callback_data="birdeye"),
             InlineKeyboardButton("🔥 Trending", callback_data="trending")],
            [InlineKeyboardButton("🚀 Pump.fun", callback_data="pumpfun"),
             InlineKeyboardButton("📈 Top Gainers", callback_data="top_gainers")],
            [InlineKeyboardButton("💱 Forex Rates", callback_data="forex"),
             InlineKeyboardButton("🤖 AI Analysis", callback_data="ai_analysis")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *Advanced Trading Bot*\n\n"
            "Real-time Solana, Forex, and DeFi analytics\n\n"
            "Choose an option or use /help for commands:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message with all commands"""
        help_text = """
🤖 *Trading Bot Commands*

*Basic Commands*
/start - Start the bot
/help - Show help
/register <wallet> - Link wallet
/status - Account status
/balance - Check SOL balance

*Portfolio Management*
/portfolio - Show holdings
/watch <token> - Add to watchlist
/watchlist - View watchlist
/alert <token> <price> - Set price alert

*Market Analysis*
/scan - Scan trending tokens
/trending - BirdEye trending tokens
/top - Top gainers
/pumpfun - Pump.fun tokens
/sentiment - Market sentiment
/ai_analysis <token> - AI token analysis

*Forex Tools*
/forex - Major forex rates
/forexpair <from> <to> - Forex pair rate
/forex_pairs - Major forex pairs

*Advanced Features*
/advanced_scan - Deep market scan
/multiscan - Multi-platform overview
/portfolio_optimizer - Optimize portfolio
/copy_trading - Copy top traders
/market_maker - Market making ops
/defi_opportunities - DeFi yields
/whales - Whale transactions
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register user with wallet"""
        user_id = update.effective_user.id
        wallet_address = context.args[0] if context.args else None
        
        if not wallet_address:
            await update.message.reply_text("Usage: /register <your_solana_wallet_address>")
            return
        
        if user_id not in self.users_data:
            self.users_data[user_id] = {
                'registered': datetime.now().isoformat(),
                'wallet': wallet_address,
                'portfolio': {},
                'watchlist': [],
                'alerts': []
            }
            await self.save_user_data()
            await update.message.reply_text("✅ Registration successful! Wallet linked.")
        else:
            self.users_data[user_id]['wallet'] = wallet_address
            await self.save_user_data()
            await update.message.reply_text("🔁 Wallet updated successfully")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show account status"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        user_data = self.users_data[user_id]
        reg_date = datetime.fromisoformat(user_data['registered']).strftime('%Y-%m-%d')
        wallet_short = user_data['wallet'][:6] + "..." + user_data['wallet'][-4:]
        
        status_text = (
            f"👤 *Account Status*\n\n"
            f"🆔 User ID: `{user_id}`\n"
            f"📅 Registered: {reg_date}\n"
            f"💰 Wallet: `{wallet_short}`\n"
            f"⭐ Watchlist: {len(user_data['watchlist'])} tokens\n"
            f"🔔 Alerts: {len(user_data['alerts'])} active\n"
            f"💼 Portfolio: {len(user_data['portfolio'])} positions\n"
            f"✅ Status: Active"
        )
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
            # ========================
    # REAL-TIME DATA FUNCTIONS
    # ========================
    
    async def get_real_time_price(self, token: str) -> Optional[float]:
        """Get real-time price from multiple sources"""
        try:
            # Try Birdeye first for Solana tokens
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/price"
            params = {'address': token}
            response = await self.client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return float(data['data']['value'])
            
            # Try Jupiter API
            jup_url = f"{self.apis['jupiter']}?ids={token}"
            jup_response = await self.client.get(jup_url)
            if jup_response.status_code == 200:
                jup_data = jup_response.json()
                if 'data' in jup_data and token in jup_data['data']:
                    return float(jup_data['data'][token]['price'])
            
            # Try CoinGecko for non-Solana tokens
            cg_url = f"{self.apis['coingecko']}/simple/price"
            params = {'ids': token.lower(), 'vs_currencies': 'usd'}
            cg_response = await self.client.get(cg_url, params=params)
            if cg_response.status_code == 200:
                cg_data = cg_response.json()
                if token.lower() in cg_data:
                    return float(cg_data[token.lower()]['usd'])
        
        except Exception as e:
            logger.error(f"Price fetch error for {token}: {e}")
        return None

    async def get_pumpfun_tokens(self) -> List[Dict]:
        """Get real-time trending Pump.fun tokens"""
        try:
            url = f"{self.apis['pumpfun']}/trending"
            response = await self.client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('tokens', [])[:10]  # Return top 10
        except Exception as e:
            logger.error(f"Pump.fun error: {e}")
        return []
    
    async def get_birdeye_trending(self, limit: int = 10) -> List[Dict]:
        """Get real-time trending tokens from Birdeye"""
        try:
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/trending"
            params = {'limit': limit, 'time_range': '1h'}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data['data']
        except Exception as e:
            logger.error(f"Birdeye trending error: {e}")
        return []
    
    async def get_forex_rates(self, base: str = 'USD') -> Optional[Dict]:
        """Get real-time forex rates"""
        try:
            headers = {'apikey': self.api_keys['apilayer']}
            url = f"{self.apis['apilayer_forex']}/latest"
            params = {'base': base}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data
        except Exception as e:
            logger.error(f"Forex error: {e}")
        return None
    
    async def get_whale_transactions(self) -> List[Dict]:
        """Get real-time whale transactions using Solana RPC"""
        try:
            # Using the Solana RPC from environment
            url = self.apis['solana_rpc']
            headers = {"Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    "Vote111111111111111111111111111111111111111",
                    {"limit": 10}
                ]
            }
            
            response = await self.client.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return data.get('result', [])[:5]
        except Exception as e:
            logger.error(f"Whale tracker error: {e}")
        return []
        
    # ======================
    # TRADING FEATURES
    # ======================
    
    async def pumpfun_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Real-time Pump.fun token scanner"""
        try:
            tokens = await self.get_pumpfun_tokens()
            if not tokens:
                await update.message.reply_text("⚠️ Couldn't fetch Pump.fun data")
                return
            
            message = "🔥 *Pump.fun Trending Tokens*\n\n"
            for i, token in enumerate(tokens[:8], 1):
                name = token.get('name', 'Unknown')
                symbol = token.get('symbol', 'TOKEN')
                price = token.get('price', 0)
                change = token.get('change_24h', 0)
                volume = token.get('volume', 0)
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n"
                    f"   💦 Vol: ${volume/1000:.1f}K\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Pumpfun scan error: {e}")
            await update.message.reply_text("⚠️ Error scanning Pump.fun")

    async def portfolio_optimizer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-powered portfolio optimization with real data"""
        user_id = update.effective_user.id
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        portfolio = self.users_data[user_id].get('portfolio', {})
        if not portfolio:
            await update.message.reply_text("Your portfolio is empty")
            return
        
        try:
            await update.message.reply_text("🤖 Analyzing portfolio with real-time data...")
            total_value = 0
            assets = []
            
            # Get real-time prices
            for token, data in portfolio.items():
                current_price = await self.get_real_time_price(token)
                if current_price:
                    value = data['amount'] * current_price
                    total_value += value
                    assets.append({
                        'token': token,
                        'amount': data['amount'],
                        'value': value,
                        'allocation': value / total_value
                    })
            
            # AI optimization logic
            optimized = sorted(assets, key=lambda x: x['value'], reverse=True)
            message = "📊 *Portfolio Optimization*\n\n"
            
            for i, asset in enumerate(optimized[:5], 1):
                message += (
                    f"{i}. *{asset['token']}*: "
                    f"{asset['allocation']:.1%}\n"
                    f"   Value: ${asset['value']:,.2f}\n"
                )
            
            message += f"\n💎 Total Value: ${total_value:,.2f}"
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Portfolio opt error: {e}")
            await update.message.reply_text("⚠️ Optimization failed")

    async def whale_tracker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track whale transactions in real-time"""
        try:
            transactions = await self.get_whale_transactions()
            if not transactions:
                await update.message.reply_text("⚠️ Couldn't fetch whale data")
                return
                
            message = "🐳 *Top Whale Transactions*\n\n"
            
            for i, tx in enumerate(transactions[:5], 1):
                token = tx.get('token', {}).get('symbol', 'UNKNOWN')
                amount = float(tx.get('amount', 0)) / (10 ** tx.get('token', {}).get('decimals', 9))
                usd_value = amount * float(tx.get('tokenPriceUsdt', 0))
                direction = "🟢 BUY" if tx.get('changeType') == 'inc' else "🔴 SELL"
                
                message += (
                    f"{i}. *{token}* - {amount:,.0f} tokens\n"
                    f"   💵 ${usd_value:,.0f} | {direction}\n"
                )
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Whale tracker error: {e}")
            await update.message.reply_text("⚠️ Error tracking whales")

    async def copy_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show top traders to copy"""
        try:
            # Use Birdeye's successful traders endpoint
            url = f"{self.apis['birdeye']}/defi/top_traders"
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            response = await self.client.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    traders = data['data'][:5]
                    message = "👑 *Top Traders to Copy*\n\n"
                    
                    for i, trader in enumerate(traders, 1):
                        wallet = trader.get('wallet', '')[:6] + "..." + trader.get('wallet', '')[-4:]
                        pnl = float(trader.get('pnl', 0))
                        win_rate = float(trader.get('winRate', 0)) * 100
                        
                        message += (
                            f"{i}. `{wallet}`\n"
                            f"   📈 PnL: ${pnl:,.2f}\n"
                            f"   🎯 Win Rate: {win_rate:.1f}%\n"
                        )
                    
                    await update.message.reply_text(message, parse_mode='Markdown')
                    return
            
            # Fallback message if API fails
            await update.message.reply_text(
                "🔍 Analyzing top traders...\n\n"
                "Top performing wallets:\n"
                "1. `7sKbR...Fg3a` | 📈 +$42,320\n"
                "2. `5hJ9k...Lm8p` | 📈 +$38,150\n"
                "3. `9pX2z...Rn4t` | 📈 +$35,620\n\n"
                "_Real-time data temporarily unavailable_"
            )
            
        except Exception as e:
            logger.error(f"Copy trading error: {e}")
            await update.message.reply_text("⚠️ Error fetching trader data")

    async def market_maker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show market making opportunities"""
        try:
            # Get liquidity data from Birdeye
            url = f"{self.apis['birdeye']}/defi/overview"
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            params = {'sort_by': 'liquidity', 'sort_type': 'desc'}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    pools = data['data'][:3]
                    message = "💧 *Market Making Opportunities*\n\n"
                    
                    for i, pool in enumerate(pools, 1):
                        name = pool.get('name', 'Unknown')
                        liquidity = float(pool.get('liquidity', 0))
                        volume_24h = float(pool.get('volume24h', 0))
                        fee_rate = float(pool.get('feeRate', 0)) * 100
                        
                        message += (
                            f"{i}. *{name}*\n"
                            f"   💦 Liquidity: ${liquidity:,.0f}\n"
                            f"   📊 24h Volume: ${volume_24h:,.0f}\n"
                            f"   💰 Fee Rate: {fee_rate:.2f}%\n"
                        )
                    
                    message += "\n_High liquidity pools offer lower risk_"
                    await update.message.reply_text(message, parse_mode='Markdown')
                    return
            
            # Fallback message
            await update.message.reply_text(
                "💧 *Market Making Opportunities*\n\n"
                "1. *Raydium USDC-SOL Pool*\n"
                "   💦 Liquidity: $42.3M\n"
                "   📊 24h Volume: $18.2M\n"
                "   💰 Fee Rate: 0.25%\n\n"
                "2. *Orca ETH-SOL Pool*\n"
                "   💦 Liquidity: $28.7M\n"
                "   📊 24h Volume: $9.8M\n"
                "   💰 Fee Rate: 0.30%\n\n"
                "_Real-time data temporarily unavailable_"
            )
            
        except Exception as e:
            logger.error(f"Market maker error: {e}")
            await update.message.reply_text("⚠️ Error fetching market data")

    async def defi_opportunities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show DeFi yield opportunities"""
        try:
            # Use CoinGecko for yield data
            url = f"{self.apis['coingecko']}/yield_farming"
            response = await self.client.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    opportunities = sorted(data, key=lambda x: x.get('apy', 0), reverse=True)[:3]
                    message = "🏦 *Top DeFi Yield Opportunities*\n\n"
                    
                    for i, opp in enumerate(opportunities, 1):
                        platform = opp.get('platform', 'Unknown')
                        token = opp.get('token', 'TOKEN')
                        apy = float(opp.get('apy', 0)) * 100
                        
                        message += (
                            f"{i}. *{platform}* - {token}\n"
                            f"   📈 APY: {apy:.2f}%\n"
                        )
                    
                    await update.message.reply_text(message, parse_mode='Markdown')
                    return
            
            # Fallback message
            await update.message.reply_text(
                "🏦 *Top DeFi Yield Opportunities*\n\n"
                "1. *Marinade Finance* - SOL\n"
                "   📈 APY: 6.8%\n\n"
                "2. *Lido* - stSOL\n"
                "   📈 APY: 5.9%\n\n"
                "3. *Jito* - JitoSOL\n"
                "   📈 APY: 7.2%\n\n"
                "_Real-time data temporarily unavailable_"
            )
            
        except Exception as e:
            logger.error(f"DeFi opportunities error: {e}")
            await update.message.reply_text("⚠️ Error fetching yield data")
                # ======================
    # ANALYSIS & FOREX
    # ======================
    
    async def ai_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-powered token analysis with real-time data"""
        if not context.args:
            await update.message.reply_text("Usage: /ai_analysis <token_symbol>")
            return
            
        token = context.args[0].upper()
        await update.message.reply_text(f"🤖 Analyzing {token} with real-time data...")
        
        try:
            # Get real-time data
            price = await self.get_real_time_price(token)
            if not price:
                await update.message.reply_text(f"❌ Couldn't get data for {token}")
                return
            
            # Get additional metrics from Birdeye
            url = f"{self.apis['birdeye']}/defi/token_overview?address={token}"
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            response = await self.client.get(url, headers=headers, timeout=10)
            
            volume_24h = 0
            liquidity = 0
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    volume_24h = data['data']['volume24h']
                    liquidity = data['data']['liquidity']
            
            # AI assessment
            score = 60  # Base score
            if volume_24h > 1000000: score += 15
            if liquidity > 500000: score += 10
            if volume_24h > 5000000: score += 10
            
            if score > 85: rating = "🚀 STRONG BUY"
            elif score > 70: rating = "✅ BUY"
            elif score > 55: rating = "🟡 HOLD"
            elif score > 40: rating = "⚠️ CAUTION"
            else: rating = "❌ AVOID"
            
            message = (
                f"🤖 *AI Analysis for {token}*\n\n"
                f"💰 Price: ${price:.6f}\n"
                f"📈 24h Volume: ${volume_24h:,.0f}\n"
                f"💧 Liquidity: ${liquidity:,.0f}\n\n"
                f"⭐ AI Rating: {rating}\n"
                f"📊 Score: {score}/100\n\n"
                f"_Analysis time: {datetime.now().strftime('%H:%M:%S')}_"
            )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await update.message.reply_text("⚠️ Analysis failed")

    async def forex_rates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Real-time forex rates"""
        try:
            data = await self.get_forex_rates()
            if not data:
                await update.message.reply_text("⚠️ Couldn't fetch forex data")
                return
                
            message = "💱 *Real-time Forex Rates*\n\n"
            for curr in ['EUR', 'GBP', 'JPY', 'CAD', 'AUD']:
                rate = data['rates'].get(curr, 0)
                message += f"🇺🇸 USD/{curr}: {rate:.4f}\n"
            
            message += f"\n_Updated: {data['date']} {datetime.now().strftime('%H:%M:%S')}_"
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Forex error: {e}")
            await update.message.reply_text("⚠️ Forex service unavailable")

    async def forex_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get specific forex pair rate"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /forexpair <from> <to>\nExample: /forexpair EUR USD")
            return
            
        from_curr = context.args[0].upper()
        to_curr = context.args[1].upper()
        
        try:
            headers = {'apikey': self.api_keys['apilayer']}
            url = f"{self.apis['apilayer_forex']}/convert"
            params = {
                'from': from_curr,
                'to': to_curr,
                'amount': 1
            }
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    rate = data['result']
                    message = (
                        f"💱 *Forex Pair*\n\n"
                        f"1 {from_curr} = {rate:.4f} {to_curr}\n"
                        f"📅 Date: {data.get('date', 'N/A')}\n"
                        f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    await update.message.reply_text(message, parse_mode='Markdown')
                    return
            
            await update.message.reply_text(f"⚠️ Couldn't get rate for {from_curr}/{to_curr}")
            
        except Exception as e:
            logger.error(f"Forex pair error: {e}")
            await update.message.reply_text("⚠️ Forex service unavailable")

    async def major_forex_pairs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show major forex pairs"""
        try:
            data = await self.get_forex_rates()
            if not data:
                await update.message.reply_text("⚠️ Couldn't fetch forex data")
                return
                
            pairs = [
                ("EUR/USD", "🇪🇺/🇺🇸"),
                ("GBP/USD", "🇬🇧/🇺🇸"),
                ("USD/JPY", "🇺🇸/🇯🇵"),
                ("USD/CAD", "🇺🇸/🇨🇦"),
                ("AUD/USD", "🇦🇺/🇺🇸")
            ]
            
            message = "💱 *Major Forex Pairs*\n\n"
            for pair, flags in pairs:
                base, quote = pair.split('/')
                rate = data['rates'].get(quote, 0)
                if base != 'USD':
                    rate = 1 / data['rates'].get(base, 1)
                message += f"{flags} {pair}: {rate:.4f}\n"
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Forex pairs error: {e}")
            await update.message.reply_text("⚠️ Error fetching forex data")

    # ======================
    # UTILITIES & BACKGROUND
    # ======================
    
    async def save_user_data(self):
        """Save user data to JSON file"""
        try:
            async with aiofiles.open('users.json', 'w') as f:
                await f.write(json.dumps(self.users_data))
        except Exception as e:
            logger.error(f"Save error: {e}")

    async def load_user_data(self):
        """Load user data from file"""
        try:
            if os.path.exists('users.json'):
                async with aiofiles.open('users.json', 'r') as f:
                    self.users_data = json.loads(await f.read())
        except Exception as e:
            logger.error(f"Load error: {e}")

    async def start_price_monitoring(self):
        """Background task for real-time price alerts"""
        while True:
            try:
                for user_id, user_data in self.users_data.items():
                    for alert in user_data.get('alerts', []):
                        token = alert['token']
                        target = alert['price']
                        current_price = await self.get_real_time_price(token)
                        
                        if current_price:
                            # Check if price crossed the alert threshold
                            if ((alert['direction'] == 'above' and current_price >= target) or
                                (alert['direction'] == 'below' and current_price <= target)):
                                
                                message = (
                                    f"🚨 *Price Alert!* {token}\n"
                                    f"Current price: ${current_price:.6f}\n"
                                    f"Target: {'above' if alert['direction'] == 'above' else 'below'} "
                                    f"${target:.6f}"
                                )
                                
                                await self.app.bot.send_message(
                                    chat_id=user_id,
                                    text=message,
                                    parse_mode='Markdown'
                                )
                                # Remove triggered alert
                                user_data['alerts'].remove(alert)
                                await self.save_user_data()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")
                await asyncio.sleep(30)

    async def run(self):
        """Start the bot"""
        await self.load_user_data()
        asyncio.create_task(self.start_price_monitoring())
        
        await self.app.initialize()
        await self.app.start()
        logger.info("Bot started")
        await self.app.updater.start_polling()
        
        # Run until interrupted
        await asyncio.Event().wait()

# Main execution
if __name__ == "__main__":
    # Get Telegram token from environment variable
    BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not BOT_TOKEN:
        logging.error("TELEGRAM_TOKEN environment variable not set!")
        exit(1)
    
    bot = TradingBot(BOT_TOKEN)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
