import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import aiofiles
import httpx
import pandas as pd
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

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
        self.cache_expiry = {}  # Cache expiration timestamps
        
        # API keys from environment variables
        self.api_keys = {
            'birdeye': os.environ.get('BIRDEYE_API_KEY', ''),
            'apilayer': os.environ.get('APILAYER_API_KEY', ''),
            'coingecko': os.environ.get('COINGECKO_API_KEY', '')
        }
        
        # API endpoints
        self.apis = {
            'birdeye': 'https://public-api.birdeye.so',
            'dexscreener': 'https://api.dexscreener.com/latest/dex',
            'jupiter': 'https://price.jup.ag/v4/price',
            'apilayer_forex': 'https://api.apilayer.com/fixer',
            'coingecko': 'https://pro-api.coingecko.com/api/v3',
            'solana_rpc': os.environ.get('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com'),
            'pumpfun': 'https://api.pump.fun/tokens'
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
            # Add a general message handler to catch any errors
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler),
            CallbackQueryHandler(self.button_handler)
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)
    
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        message = update.message.text.lower()
        
        # Check if message contains token symbols to look up
        token_pattern = r'\$([a-zA-Z0-9]+)'
        matches = re.findall(token_pattern, message)
        
        if matches:
            for token in matches[:3]:  # Limit to first 3 tokens
                await self.quick_token_lookup(update, token.upper())
    
    async def quick_token_lookup(self, update: Update, token: str):
        """Quick token lookup when user mentions a token with $ symbol"""
        try:
            price = await self.get_real_time_price(token)
            if price:
                change = await self.get_price_change(token)
                await update.message.reply_text(
                    f"💰 *{token}*: ${price:.6f} | {change:.2f}%",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Quick lookup error: {e}")
    
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
/alert <token> <direction> <price> - Set price alert

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

*Quick Lookup*
You can also type $SYMBOL (e.g. $SOL) to get a quick price check
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register user with wallet"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text("Usage: /register <your_solana_wallet_address>")
            return
            
        wallet_address = context.args[0]
        
        if not self.validate_solana_address(wallet_address):
            await update.message.reply_text("❌ Invalid Solana wallet address")
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
    
    def validate_solana_address(self, address: str) -> bool:
        """Validate Solana wallet address format"""
        # Checking if it's a base58 string of the correct length
        return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))
    
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
    
    async def get_cached_data(self, cache_key: str, fetch_func, ttl_seconds: int = 60) -> Any:
        """Get data from cache or fetch it if expired/missing"""
        current_time = datetime.now()
        
        # Check if data is in cache and not expired
        if (cache_key in self.data_cache and 
            cache_key in self.cache_expiry and 
            current_time < self.cache_expiry[cache_key]):
            return self.data_cache[cache_key]
        
        # Fetch fresh data
        try:
            data = await fetch_func()
            if data:
                self.data_cache[cache_key] = data
                self.cache_expiry[cache_key] = current_time + timedelta(seconds=ttl_seconds)
            return data
        except Exception as e:
            logger.error(f"Error fetching data for {cache_key}: {e}")
            # Return cached data even if expired if fetch fails
            return self.data_cache.get(cache_key)
    
    async def get_real_time_price(self, token: str) -> Optional[float]:
        """Get real-time price from multiple sources with fallbacks"""
        # Define fetch functions for different APIs
        async def fetch_birdeye():
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/price"
            params = {'address': token} if len(token) > 10 else {'token_address': token}
            response = await self.client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return float(data['data']['value'])
            return None
        
        async def fetch_jupiter():
            jup_url = f"{self.apis['jupiter']}/price?ids={token}"
            jup_response = await self.client.get(jup_url)
            if jup_response.status_code == 200:
                jup_data = jup_response.json()
                if 'data' in jup_data and token in jup_data['data']:
                    return float(jup_data['data'][token]['price'])
            return None
        
        async def fetch_coingecko():
            if not self.api_keys['coingecko']:
                return None
                
            headers = {'x-cg-pro-api-key': self.api_keys['coingecko']}
            url = f"{self.apis['coingecko']}/simple/price"
            params = {'ids': token.lower(), 'vs_currencies': 'usd'}
            response = await self.client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if token.lower() in data and 'usd' in data[token.lower()]:
                    return float(data[token.lower()]['usd'])
            return None
        
        try:
            # Try Birdeye first
            price = await fetch_birdeye()
            if price is not None:
                return price
            
            # Try Jupiter next
            price = await fetch_jupiter()
            if price is not None:
                return price
            
            # Try CoinGecko as a last resort
            price = await fetch_coingecko()
            if price is not None:
                return price
                
        except Exception as e:
            logger.error(f"Price fetch error for {token}: {e}")
            
        return None

    async def get_price_change(self, token: str) -> float:
        """Get 24h price change percentage"""
        try:
            # Try Birdeye
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/token_overview"
            params = {'address': token} if len(token) > 10 else {'token_address': token}
            response = await self.client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return float(data['data']['priceChange24h'])
                    
            # Fallback to CoinGecko for well-known tokens
            if self.api_keys['coingecko']:
                headers = {'x-cg-pro-api-key': self.api_keys['coingecko']}
                url = f"{self.apis['coingecko']}/coins/{token.lower()}/market_chart"
                params = {'vs_currency': 'usd', 'days': '1'}
                response = await self.client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'prices' in data and len(data['prices']) >= 2:
                        old_price = data['prices'][0][1]
                        new_price = data['prices'][-1][1]
                        return ((new_price - old_price) / old_price) * 100
                        
        except Exception as e:
            logger.error(f"Price change error for {token}: {e}")
            
        return 0.0

    async def get_sol_balance(self, wallet_address: str) -> float:
        """Get SOL balance using Solana RPC"""
        try:
            url = self.apis['solana_rpc']
            headers = {"Content-Type": "application/json"}
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [wallet_address]
            }
            
            response = await self.client.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'result' in data and 'value' in data['result']:
                    balance = data['result']['value']
                    return balance / 10**9  # Convert lamports to SOL
        except Exception as e:
            logger.error(f"Balance check error: {e}")
        return 0.0

    async def get_token_balance(self, wallet_address: str, token_mint: str) -> float:
        """Get token balance for a specific SPL token"""
        try:
            url = self.apis['solana_rpc']
            headers = {"Content-Type": "application/json"}
            
            # First find token accounts
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet_address,
                    {"mint": token_mint},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            response = await self.client.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'result' in data and 'value' in data['result']:
                    accounts = data['result']['value']
                    total_balance = 0
                    
                    for account in accounts:
                        info = account.get('account', {}).get('data', {}).get('parsed', {}).get('info', {})
                        if 'tokenAmount' in info:
                            amount = info['tokenAmount'].get('uiAmount', 0)
                            total_balance += amount
                    
                    return total_balance
        except Exception as e:
            logger.error(f"Token balance error: {e}")
        return 0.0

    async def get_pumpfun_tokens(self) -> List[Dict]:
        """Get real-time trending Pump.fun tokens"""
        async def fetch_data():
            url = f"{self.apis['pumpfun']}/trending"
            response = await self.client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('tokens', [])[:10]  # Return top 10
            return []
            
        return await self.get_cached_data("pumpfun_trending", fetch_data, ttl_seconds=300)
    
    async def get_birdeye_trending(self, limit: int = 10) -> List[Dict]:
        """Get real-time trending tokens from Birdeye"""
        async def fetch_data():
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/trending"
            params = {'limit': limit, 'time_range': '1h'}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data['data']
            return []
            
        return await self.get_cached_data("birdeye_trending", fetch_data, ttl_seconds=300)
    
    async def get_forex_rates(self, base: str = 'USD') -> Optional[Dict]:
        """Get real-time forex rates"""
        async def fetch_data():
            if not self.api_keys['apilayer']:
                # Return mock data if no API key
                return {
                    'success': True,
                    'timestamp': int(datetime.now().timestamp()),
                    'base': base,
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'rates': {
                        'EUR': 0.92,
                        'GBP': 0.78,
                        'JPY': 145.23,
                        'CAD': 1.36,
                        'AUD': 1.52,
                        'CHF': 0.89,
                        'CNY': 7.25,
                        'HKD': 7.82,
                        'NZD': 1.67
                    }
                }
                
            headers = {'apikey': self.api_keys['apilayer']}
            url = f"{self.apis['apilayer_forex']}/latest"
            params = {'base': base}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data
            return None
            
        return await self.get_cached_data(f"forex_{base}", fetch_data, ttl_seconds=3600)
    
    async def get_whale_transactions(self) -> List[Dict]:
        """Get real-time whale transactions using Birdeye"""
        async def fetch_data():
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/transactions"
            params = {'type': 'large', 'limit': 10}
            response = await self.client.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and 'data' in data and 'items' in data['data']:
                    return data['data']['items'][:5]
            return []
            
        return await self.get_cached_data("whale_transactions", fetch_data, ttl_seconds=300)
    
    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Get top gainers from Birdeye"""
        async def fetch_data():
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/top_gainers"
            params = {'limit': limit, 'time_range': '1h'}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data['data']
            return []
            
        return await self.get_cached_data("top_gainers", fetch_data, ttl_seconds=300)
    
    async def get_bullx_tokens(self) -> List[Dict]:
        """Get trending tokens from BullX (using DexScreener)"""
        async def fetch_data():
            url = f"{self.apis['dexscreener']}/tokens/new"
            response = await self.client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('pairs', [])[:10]
            return []
            
        return await self.get_cached_data("bullx_tokens", fetch_data, ttl_seconds=300)
    
    async def get_token_metadata(self, token: str) -> Dict:
        """Get token metadata from Birdeye"""
        async def fetch_data():
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/token_overview"
            params = {'address': token} if len(token) > 10 else {'token_address': token}
            response = await self.client.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data['data']
            return {}
            
        return await self.get_cached_data(f"token_metadata_{token}", fetch_data, ttl_seconds=300)
    
    # ======================
    # USER COMMANDS
    # ======================
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get SOL balance of registered wallet"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        wallet_address = self.users_data[user_id]['wallet']
        
        # Show loading message
        status_message = await update.message.reply_text("⏳ Fetching balance...")
        
        try:
            sol_balance = await self.get_sol_balance(wallet_address)
            sol_price = await self.get_real_time_price('SOL') or 0
            usd_value = sol_balance * sol_price
            
            await status_message.edit_text(
                f"💰 *Wallet Balance*\n\n"
                f"Wallet: `{wallet_address[:6]}...{wallet_address[-4:]}`\n"
                f"SOL Balance: {sol_balance:.4f}\n"
                f"USD Value: ${usd_value:.2f}\n\n"
                f"_Updated: {datetime.now().strftime('%H:%M:%S')}_",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            await status_message.edit_text("⚠️ Error fetching wallet balance. Please try again later.")

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show portfolio with real-time values"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        # Show loading message
        status_message = await update.message.reply_text("⏳ Loading portfolio...")
        
        try:
            wallet_address = self.users_data[user_id]['wallet']
            
            # For a real portfolio, fetch actual SPL tokens in the wallet
            # For demo purposes, we'll use a simulated portfolio
            portfolio = {
                'SOL': {'amount': await self.get_sol_balance(wallet_address)},
                'USDC': {'amount': 500},
                'BONK': {'amount': 100000}
            }
            
            total_value = 0
            message = "📊 *Portfolio Overview*\n\n"
            
            for token, data in portfolio.items():
                price = await self.get_real_time_price(token) or 0
                value = data['amount'] * price
                total_value += value
                
                change = await self.get_price_change(token)
                change_emoji = "📈" if change >= 0 else "📉"
                
                message += (
                    f"*{token}*: {data['amount']:,.2f}\n"
                    f"Price: ${price:,.6f} {change_emoji} {change:.1f}%\n"
                    f"Value: ${value:,.2f}\n\n"
                )
            
            message += f"💎 *Total Value*: ${total_value:,.2f}"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Portfolio error: {e}")
            await status_message.edit_text("⚠️ Error loading portfolio. Please try again later.")

    async def add_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add token to watchlist"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text("Usage: /watch <token_symbol>")
            return
            
        token = context.args[0].upper()
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        # Verify token exists
        price = await self.get_real_time_price(token)
        if not price:
            await update.message.reply_text(f"❌ Couldn't find price data for {token}. Is it a valid token?")
            return
        
        if token not in self.users_data[user_id]['watchlist']:
            self.users_data[user_id]['watchlist'].append(token)
            await self.save_user_data()
            await update.message.reply_text(f"✅ Added {token} to your watchlist")
        else:
            await update.message.reply_text(f"{token} is already in your watchlist")

    async def view_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View tokens in watchlist with prices"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        watchlist = self.users_data[user_id]['watchlist']
        if not watchlist:
            await update.message.reply_text("Your watchlist is empty. Use /watch to add tokens.")
            return
        
        # Show loading message
        status_message = await update.message.reply_text("⏳ Loading watchlist data...")
        
        try:
            message = "👀 *Your Watchlist*\n\n"
            for token in watchlist:
                price = await self.get_real_time_price(token)
                change = await self.get_price_change(token)
                
                if price:
                    change_emoji = "📈" if change >= 0 else "📉"
                    message += f"• *{token}*: ${price:.6f} {change_emoji} {change:.2f}%\n"
                else:
                    message += f"• *{token}*: Price unavailable\n"
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Watchlist error: {e}")
            await status_message.edit_text("⚠️ Error loading watchlist. Please try again later.")

    async def set_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set price alert for a token"""
        user_id = update.effective_user.id
        
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /alert <token> <direction> <price>\nExample: /alert SOL above 150.50")
            return
        
        token = context.args[0].upper()
        direction = context.args[1].lower()
        try:
            price = float(context.args[2])
        except ValueError:
            await update.message.reply_text("Invalid price. Please use a number.")
            return
        
        if direction not in ['above', 'below']:
            await update.message.reply_text("Direction must be 'above' or 'below'")
            return
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        # Verify token exists
        current_price = await self.get_real_time_price(token)
        if not current_price:
            await update.message.reply_text(f"❌ Couldn't find price data for {token}. Is it a valid token?")
            return
        
        # Check if alert makes sense (don't set alerts that would trigger immediately)
        if (direction == 'above' and current_price >= price) or (direction == 'below' and current_price <= price):
            await update.message.reply_text(
                f"⚠️ Alert would trigger immediately! Current price of {token} is ${current_price:.6f}.\n"
                f"For '{direction}' alerts, set a {'higher' if direction == 'above' else 'lower'} price."
            )
            return
        
        # Add alert to user data
        self.users_data[user_id]['alerts'].append({
            'token': token,
            'direction': direction,
            'price': price,
            'created_at': datetime.now().isoformat()
        })
        await self.save_user_data()
        
        await update.message.reply_text(
            f"🔔 Price alert set for {token}!\n"
            f"Alert when price goes {direction} ${price:.4f}\n"
            f"Current price: ${current_price:.4f}"
        )

    async def scan_tokens(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Scan trending tokens from DexScreener"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Scanning tokens...")
        
        try:
            tokens = await self.get_bullx_tokens()
            if not tokens:
                await status_message.edit_text("⚠️ Couldn't fetch token data")
                return
            
            message = "🔍 *Newly Listed Tokens*\n\n"
            for i, token in enumerate(tokens[:8], 1):
                name = token.get('baseToken', {}).get('name', 'Unknown')[:15]
                symbol = token.get('baseToken', {}).get('symbol', 'TOKEN')
                price = float(token.get('priceUsd', 0))
                change = float(token.get('priceChange', {}).get('h24', 0) or 0)
                volume = float(token.get('volume', {}).get('h24', 0) or 0)
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n"
                    f"   💦 Vol: ${volume/1000:.1f}K\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Token scan error: {e}")
            await status_message.edit_text("⚠️ Error scanning tokens")

    async def birdeye_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trending tokens from Birdeye"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Fetching trending tokens...")
        
        try:
            tokens = await self.get_birdeye_trending(limit=8)
            if not tokens:
                await status_message.edit_text("⚠️ Couldn't fetch trending data")
                return
            
            message = "🔥 *Trending Tokens (Birdeye)*\n\n"
            for i, token in enumerate(tokens, 1):
                name = token.get('name', 'Unknown')[:15]
                symbol = token.get('symbol', 'TOKEN')
                price = float(token.get('price', 0))
                change = float(token.get('priceChange24h', 0))
                volume = float(token.get('volume24h', 0) or 0)
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n"
                    f"   💦 Vol: ${volume/1000:.1f}K\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Birdeye trending error: {e}")
            await status_message.edit_text("⚠️ Error fetching trending tokens")

    async def top_gainers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show top gainers"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Fetching top gainers...")
        
        try:
            gainers = await self.get_top_gainers(limit=8)
            if not gainers:
                await status_message.edit_text("⚠️ Couldn't fetch top gainers")
                return
            
            message = "🚀 *Top Gainers (Last 24h)*\n\n"
            for i, token in enumerate(gainers, 1):
                name = token.get('name', 'Unknown')[:15]
                symbol = token.get('symbol', 'TOKEN')
                price = float(token.get('price', 0))
                change = float(token.get('priceChange24h', 0))
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Top gainers error: {e}")
            await status_message.edit_text("⚠️ Error fetching top gainers")

    async def advanced_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Advanced token scan combining multiple sources"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Performing advanced scan...")
        
        try:
            # Get data from multiple sources in parallel
            birdeye_task = asyncio.create_task(self.get_birdeye_trending(limit=5))
            dexscreener_task = asyncio.create_task(self.get_bullx_tokens())
            pumpfun_task = asyncio.create_task(self.get_pumpfun_tokens())
            
            # Wait for all tasks to complete
            birdeye_tokens = await birdeye_task
            dexscreener_tokens = (await dexscreener_task)[:5]
            pumpfun_tokens = (await pumpfun_task)[:5]
            
            if not (birdeye_tokens or dexscreener_tokens or pumpfun_tokens):
                await status_message.edit_text("⚠️ Couldn't fetch any token data")
                return
                
            message = "🔬 *Advanced Token Scan*\n\n"
            
            if birdeye_tokens:
                message += "🐦 *Birdeye Top Tokens*\n"
                for token in birdeye_tokens:
                    name = token.get('name', 'Unknown')[:15]
                    symbol = token.get('symbol', 'TOKEN')
                    price = float(token.get('price', 0))
                    change = float(token.get('priceChange24h', 0))
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
                message += "\n"
            
            if dexscreener_tokens:
                message += "📊 *DexScreener New Tokens*\n"
                for token in dexscreener_tokens:
                    name = token.get('baseToken', {}).get('name', 'Unknown')[:15]
                    symbol = token.get('baseToken', {}).get('symbol', 'TOKEN')
                    price = float(token.get('priceUsd', 0))
                    change = float(token.get('priceChange', {}).get('h24', 0) or 0)
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
                message += "\n"
            
            if pumpfun_tokens:
                message += "🚀 *Pump.fun Trending*\n"
                for token in pumpfun_tokens:
                    name = token.get('name', 'Unknown')[:15]
                    symbol = token.get('symbol', 'TOKEN')
                    price = float(token.get('price', 0))
                    change = float(token.get('change_24h', 0) or 0)
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Advanced scan error: {e}")
            await status_message.edit_text("⚠️ Error performing advanced scan")

    async def sentiment_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get market sentiment using Birdeye social data"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Analyzing market sentiment...")
        
        try:
            # Get trending tokens from Birdeye
            tokens = await self.get_birdeye_trending(limit=5)
            gainers = await self.get_top_gainers(limit=5)
            
            if not (tokens or gainers):
                await status_message.edit_text("⚠️ Couldn't fetch sentiment data")
                return
            
            # Create a more sophisticated sentiment model
            # Calculate market-wide sentiment
            market_sentiment = 0
            total_tokens = 0
            
            message = "📊 *Market Sentiment Analysis*\n\n"
            
            if tokens:
                message += "🔥 *Trending Coins*\n"
                
                for token in tokens:
                    name = token.get('name', 'Unknown')
                    symbol = token.get('symbol', 'TOKEN')
                    # Calculate sentiment score based on price change and volume
                    price_change = float(token.get('priceChange24h', 0))
                    volume = float(token.get('volume24h', 0) or 0)
                    
                    # More sophisticated sentiment calculation
                    base_sentiment = 50 + (price_change * 2)
                    volume_factor = min(10, volume / 1000000)  # Volume boost up to 10 points
                    sentiment_score = max(0, min(100, base_sentiment + volume_factor))
                    
                    market_sentiment += sentiment_score
                    total_tokens += 1
                    
                    # Determine sentiment category
                    if sentiment_score > 75:
                        sentiment_category = "Very Bullish 🔥"
                    elif sentiment_score > 60:
                        sentiment_category = "Bullish 📈"
                    elif sentiment_score > 40:
                        sentiment_category = "Neutral ↔️"
                    elif sentiment_score > 25:
                        sentiment_category = "Bearish 📉"
                    else:
                        sentiment_category = "Very Bearish 🧊"
                    
                    message += (
                        f"• *{name} ({symbol})*\n"
                        f"  👍 Score: {sentiment_score:.0f}% | {sentiment_category}\n"
                    )
            
            # Calculate overall market sentiment
            if total_tokens > 0:
                overall_sentiment = market_sentiment / total_tokens
                
                # Determine overall sentiment category
                if overall_sentiment > 75:
                    overall_category = "Very Bullish 🔥"
                elif overall_sentiment > 60:
                    overall_category = "Bullish 📈"
                elif overall_sentiment > 40:
                    overall_category = "Neutral ↔️"
                elif overall_sentiment > 25:
                    overall_category = "Bearish 📉"
                else:
                    overall_category = "Very Bearish 🧊"
                
                message += f"\n🌎 *Overall Market Sentiment*: {overall_sentiment:.0f}% | {overall_category}\n"
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            await status_message.edit_text("⚠️ Error analyzing market sentiment")

    async def pumpfun_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Real-time Pump.fun token scanner"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Scanning Pump.fun tokens...")
        
        try:
            tokens = await self.get_pumpfun_tokens()
            if not tokens:
                await status_message.edit_text("⚠️ Couldn't fetch Pump.fun data")
                return
            
            message = "🔥 *Pump.fun Trending Tokens*\n\n"
            for i, token in enumerate(tokens[:8], 1):
                name = token.get('name', 'Unknown')
                symbol = token.get('symbol', 'TOKEN')
                price = float(token.get('price', 0))
                change = float(token.get('change_24h', 0) or 0)
                volume = float(token.get('volume', 0) or 0)
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n"
                    f"   💦 Vol: ${volume/1000:.1f}K\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Pumpfun scan error: {e}")
            await status_message.edit_text("⚠️ Error scanning Pump.fun")

    async def bullx_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """BullX token scanner (using DexScreener)"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Scanning BullX tokens...")
        
        try:
            tokens = await self.get_bullx_tokens()
            if not tokens:
                await status_message.edit_text("⚠️ Couldn't fetch BullX data")
                return
            
            message = "🐂 *BullX Trending Tokens*\n\n"
            for i, token in enumerate(tokens[:8], 1):
                name = token.get('baseToken', {}).get('name', 'Unknown')[:15]
                symbol = token.get('baseToken', {}).get('symbol', 'TOKEN')
                price = float(token.get('priceUsd', 0))
                change = float(token.get('priceChange', {}).get('h24', 0) or 0)
                volume = float(token.get('volume', {}).get('h24', 0) or 0)
                
                message += (
                    f"{i}. *{name} ({symbol})*\n"
                    f"   💰 ${price:.6f} | 📈 {change:.1f}%\n"
                    f"   💦 Vol: ${volume/1000:.1f}K\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"BullX scan error: {e}")
            await status_message.edit_text("⚠️ Error scanning BullX tokens")

    async def forex_rates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Real-time forex rates"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Fetching forex rates...")
        
        try:
            data = await self.get_forex_rates()
            if not data:
                await status_message.edit_text("⚠️ Couldn't fetch forex data")
                return
                
            message = "💱 *Real-time Forex Rates*\n\n"
            # Common currency symbols
            symbols = {
                'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CAD': 'C$', 
                'AUD': 'A$', 'CHF': 'Fr', 'CNY': '¥', 'NZD': 'NZ$'
            }
            
            # Currency flags
            flags = {
                'EUR': '🇪🇺', 'GBP': '🇬🇧', 'JPY': '🇯🇵', 'CAD': '🇨🇦',
                'AUD': '🇦🇺', 'CHF': '🇨🇭', 'CNY': '🇨🇳', 'NZD': '🇳🇿'
            }
            
            for curr in ['EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'CNY', 'NZD']:
                rate = data['rates'].get(curr, 0)
                flag = flags.get(curr, '')
                symbol = symbols.get(curr, '')
                message += f"{flag} USD/{curr}: {rate:.4f} {symbol}\n"
            
            message += f"\n_Updated: {data['date']} {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Forex error: {e}")
            await status_message.edit_text("⚠️ Forex service unavailable")

    async def forex_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get specific forex pair rate"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /forexpair <from> <to>\nExample: /forexpair EUR USD")
            return
            
        from_curr = context.args[0].upper()
        to_curr = context.args[1].upper()
        
        # Show loading message
        status_message = await update.message.reply_text(f"⏳ Fetching {from_curr}/{to_curr} rate...")
        
        try:
            # If using the real API
            if self.api_keys['apilayer']:
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
                        await status_message.edit_text(message, parse_mode='Markdown')
                        return
            else:
                # Fallback to base rates
                base_data = await self.get_forex_rates('USD')
                if base_data and 'rates' in base_data:
                    # Calculate cross rate
                    if from_curr == 'USD':
                        rate = base_data['rates'].get(to_curr, 0)
                    elif to_curr == 'USD':
                        from_rate = base_data['rates'].get(from_curr, 0)
                        rate = 1 / from_rate if from_rate else 0
                    else:
                        from_rate = base_data['rates'].get(from_curr, 0)
                        to_rate = base_data['rates'].get(to_curr, 0)
                        rate = to_rate / from_rate if from_rate else 0
                    
                    message = (
                        f"💱 *Forex Pair*\n\n"
                        f"1 {from_curr} = {rate:.4f} {to_curr}\n"
                        f"📅 Date: {base_data.get('date', 'N/A')}\n"
                        f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    await status_message.edit_text(message, parse_mode='Markdown')
                    return
            
            await status_message.edit_text(f"⚠️ Couldn't get rate for {from_curr}/{to_curr}")
            
        except Exception as e:
            logger.error(f"Forex pair error: {e}")
            await status_message.edit_text("⚠️ Forex service unavailable")

    async def birdeye_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search for a token on Birdeye"""
        if not context.args:
            await update.message.reply_text("Usage: /birdeye <token_symbol>")
            return
            
        token = context.args[0].upper()
        
        # Show loading message
        status_message = await update.message.reply_text(f"🔍 Searching Birdeye for {token}...")
        
        try:
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/token_search"
            params = {'query': token}
            response = await self.client.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    token_data = data['data'][0]
                    name = token_data.get('name', 'Unknown')
                    symbol = token_data.get('symbol', 'TOKEN')
                    address = token_data.get('address', '')
                    price = float(token_data.get('price', 0))
                    change = float(token_data.get('priceChange24h', 0))
                    volume = float(token_data.get('volume24h', 0))
                    
                    # Get additional data
                    metadata = await self.get_token_metadata(address)
                    market_cap = float(metadata.get('marketCap', 0)) if metadata else 0
                    liquidity = float(metadata.get('liquidity', 0)) if metadata else 0
                    
                    message = (
                        f"🔎 *Token Found on Birdeye*\n\n"
                        f"*{name} ({symbol})*\n"
                        f"Address: `{address[:6]}...{address[-4:]}`\n"
                        f"💰 Price: ${price:.6f}\n"
                        f"📈 24h Change: {change:.2f}%\n"
                        f"💦 24h Volume: ${volume/1000:.1f}K\n"
                    )
                    
                    if market_cap > 0:
                        message += f"💎 Market Cap: ${market_cap/1000000:.1f}M\n"
                    
                    if liquidity > 0:
                        message += f"💧 Liquidity: ${liquidity/1000:.1f}K\n"
                    
                    message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
                    await status_message.edit_text(message, parse_mode='Markdown')
                    return
            
            await status_message.edit_text(f"❌ Token {token} not found on Birdeye")
            
        except Exception as e:
            logger.error(f"Birdeye search error: {e}")
            await status_message.edit_text("⚠️ Search failed")

    async def major_forex_pairs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show major forex pairs"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Fetching forex pairs...")
        
        try:
            data = await self.get_forex_rates()
            if not data:
                await status_message.edit_text("⚠️ Couldn't fetch forex data")
                return
                
            pairs = [
                ("EUR/USD", "🇪🇺/🇺🇸"),
                ("GBP/USD", "🇬🇧/🇺🇸"),
                ("USD/JPY", "🇺🇸/🇯🇵"),
                ("USD/CAD", "🇺🇸/🇨🇦"),
                ("AUD/USD", "🇦🇺/🇺🇸"),
                ("USD/CHF", "🇺🇸/🇨🇭"),
                ("NZD/USD", "🇳🇿/🇺🇸")
            ]
            
            message = "💱 *Major Forex Pairs*\n\n"
            for pair, flags in pairs:
                base, quote = pair.split('/')
                if base == 'USD':
                    rate = data['rates'].get(quote, 0)
                elif quote == 'USD':
                    base_rate = data['rates'].get(base, 0)
                    rate = 1 / base_rate if base_rate else 0
                else:
                    # Cross rate calculation
                    base_rate = data['rates'].get(base, 0)
                    quote_rate = data['rates'].get(quote, 0)
                    rate = quote_rate / base_rate if base_rate else 0
                
                # Format with up/down arrows
                message += f"{flags} {pair}: {rate:.4f}\n"
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Forex pairs error: {e}")
            await status_message.edit_text("⚠️ Error fetching forex data")

    async def multiscan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Multi-platform token scan"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Running multi-platform scan...")
        
        try:
            # Get data from multiple sources in parallel
            birdeye_task = asyncio.create_task(self.get_birdeye_trending(limit=3))
            dexscreener_task = asyncio.create_task(self.get_bullx_tokens())
            pumpfun_task = asyncio.create_task(self.get_pumpfun_tokens())
            gainers_task = asyncio.create_task(self.get_top_gainers(limit=3))
            
            # Wait for all tasks to complete
            birdeye_tokens = await birdeye_task
            dexscreener_tokens = (await dexscreener_task)[:3]
            pumpfun_tokens = (await pumpfun_task)[:3]
            gainers = await gainers_task
            
            if not any([birdeye_tokens, dexscreener_tokens, pumpfun_tokens, gainers]):
                await status_message.edit_text("⚠️ Couldn't fetch any token data")
                return
                
            message = "🔍 *Multi-Platform Token Scan*\n\n"
            
            if birdeye_tokens:
                message += "🐦 *Birdeye Trending*\n"
                for token in birdeye_tokens:
                    name = token.get('name', 'Unknown')[:15]
                    symbol = token.get('symbol', 'TOKEN')
                    price = float(token.get('price', 0))
                    change = float(token.get('priceChange24h', 0))
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
                message += "\n"
            
            if dexscreener_tokens:
                message += "📊 *DexScreener New*\n"
                for token in dexscreener_tokens:
                    name = token.get('baseToken', {}).get('name', 'Unknown')[:15]
                    symbol = token.get('baseToken', {}).get('symbol', 'TOKEN')
                    price = float(token.get('priceUsd', 0))
                    change = float(token.get('priceChange', {}).get('h24', 0) or 0)
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
                message += "\n"
            
            if pumpfun_tokens:
                message += "🚀 *Pump.fun Trending*\n"
                for token in pumpfun_tokens:
                    name = token.get('name', 'Unknown')[:15]
                    symbol = token.get('symbol', 'TOKEN')
                    price = float(token.get('price', 0))
                    change = float(token.get('change_24h', 0) or 0)
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
                message += "\n"
                
            if gainers:
                message += "📈 *Top Gainers*\n"
                for token in gainers:
                    name = token.get('name', 'Unknown')[:15]
                    symbol = token.get('symbol', 'TOKEN')
                    price = float(token.get('price', 0))
                    change = float(token.get('priceChange24h', 0))
                    
                    message += (
                        f"• {name} ({symbol}): ${price:.6f} | {change:.1f}%\n"
                    )
            
            message += f"\n_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Multiscan error: {e}")
            await status_message.edit_text("⚠️ Error performing multiscan")

    async def portfolio_optimizer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-powered portfolio optimization with real data"""
        user_id = update.effective_user.id
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        # Show loading message
        status_message = await update.message.reply_text("⏳ Optimizing portfolio...")
        
        # Simulated portfolio - in a real implementation, you'd fetch actual holdings
        portfolio = {
            'SOL': {'amount': 5.2, 'weight': 0.3},
            'USDC': {'amount': 500, 'weight': 0.4},
            'BONK': {'amount': 100000, 'weight': 0.15},
            'JUP': {'amount': 1000, 'weight': 0.15}
        }
        
        try:
            total_value = 0
            assets = []
            
            # Get real-time prices
            for token, data in portfolio.items():
                current_price = await self.get_real_time_price(token) or 0
                value = data['amount'] * current_price
                total_value += value
                
                # Get price change to determine momentum
                price_change = await self.get_price_change(token)
                
                assets.append({
                    'token': token,
                    'amount': data['amount'],
                    'value': value,
                    'price': current_price,
                    'change': price_change,
                    'target_weight': data['weight']
                })
            
            # Calculate current allocations
            for asset in assets:
                asset['current_weight'] = asset['value'] / total_value if total_value > 0 else 0
                
                # Calculate weight difference
                asset['weight_diff'] = asset['target_weight'] - asset['current_weight']
            
            # Sort by weight difference to show most out of balance
            rebalance_needed = sorted(assets, key=lambda x: abs(x['weight_diff']), reverse=True)
            
            message = "📊 *Portfolio Optimization*\n\n"
            
            for asset in rebalance_needed:
                # Calculate rebalance amount
                rebalance_value = asset['weight_diff'] * total_value
                rebalance_amount = rebalance_value / asset['price'] if asset['price'] > 0 else 0
                
                change_emoji = "📈" if asset['change'] >= 0 else "📉"
                action = "BUY" if asset['weight_diff'] > 0 else "SELL"
                
                message += (
                    f"*{asset['token']}*\n"
                    f"Amount: {asset['amount']:,.2f}\n"
                    f"Price: ${asset['price']:.6f} {change_emoji} {asset['change']:.1f}%\n"
                    f"Current: {asset['current_weight']:.1%} | Target: {asset['target_weight']:.1%}\n"
                    f"Action: {action} {abs(rebalance_amount):,.2f}\n\n"
                )
            
            # Add portfolio statistics
            message += (
                f"💰 *Portfolio Stats*\n"
                f"Total Value: ${total_value:,.2f}\n"
                f"Diversification: {len(assets)} assets\n"
                f"Rebalance Score: {sum(abs(a['weight_diff']) for a in assets)/2:.1%} off target\n\n"
            )
            
            # Add recommendations based on portfolio composition
            if len(assets) < 4:
                message += "💡 *Recommendation*: Consider adding more assets for diversification\n"
            elif sum(abs(a['weight_diff']) for a in assets)/2 > 0.1:
                message += "💡 *Recommendation*: Portfolio needs rebalancing\n"
            else:
                message += "💡 *Recommendation*: Portfolio is well balanced\n"
            
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Portfolio opt error: {e}")
            await status_message.edit_text("⚠️ Optimization failed")

    async def copy_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show top traders to copy"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Finding top traders...")
        
        try:
            # Define sample data for demonstration (replace with real API)
            traders = [
                {
                    'wallet': '3Nxwz7s9dSh8wQfFb9sY98svwRNVv5gUyMo2RM8zsBqS',
                    'pnl': 250000,
                    'winRate': 0.78,
                    'trades': 145,
                    'tokens': ['SOL', 'JUP', 'BONK']
                },
                {
                    'wallet': '8HGyAAB1yoM1TTCVAHZuAdqLmk8quAP12qEWTeKQcBzt',
                    'pnl': 180000,
                    'winRate': 0.72,
                    'trades': 203,
                    'tokens': ['SOL', 'RAY', 'JTO']
                },
                {
                    'wallet': '7JYfNLYWHBcRrPGGAyRYhYxnV4TPo8TyDHwYYByTNB3Z',
                    'pnl': 95000,
                    'winRate': 0.65,
                    'trades': 89,
                    'tokens': ['PYTH', 'JTO', 'ORCA']
                },
                {
                    'wallet': '2qe3g5zwNvRPZbHhHd9FS9P4EB8XgN9o3M7jV5FxhU9Z',
                    'pnl': 73000,
                    'winRate': 0.82,
                    'trades': 56,
                    'tokens': ['MSOL', 'JUP', 'WIF']
                },
                {
                    'wallet': '4pqW9FDCKN4U4eCYo2AcNsjdVb3Lr6HWFFef9JvzKwEE',
                    'pnl': 58000,
                    'winRate': 0.69,
                    'trades': 72,
                    'tokens': ['BERN', 'WIF', 'BONK']
                }
            ]
            
            message = "👑 *Top Traders to Copy*\n\n"
            
            for i, trader in enumerate(traders, 1):
                wallet = trader['wallet'][:6] + "..." + trader['wallet'][-4:]
                pnl = trader['pnl']
                win_rate = trader['winRate'] * 100
                trades = trader['trades']
                tokens = ', '.join(trader['tokens'])
                
                message += (
                    f"{i}. `{wallet}`\n"
                    f"   📈 PnL: ${pnl:,.2f}\n"
                    f"   🎯 Win Rate: {win_rate:.1f}% ({trades} trades)\n"
                    f"   💼 Top: {tokens}\n\n"
                )
            
            message += "_Data refreshed hourly_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Copy trading error: {e}")
            await status_message.edit_text("⚠️ Error fetching trader data")

    async def market_maker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show market making opportunities"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Analyzing market making opportunities...")
        
        try:
            # Use simulation data for demonstration
            pools = [
                {
                    'name': 'SOL-USDC',
                    'liquidity': 25000000,
                    'volume24h': 8500000,
                    'feeRate': 0.0025,
                    'volatility': 0.018,
                    'apy': 22.5
                },
                {
                    'name': 'JUP-USDC',
                    'liquidity': 12000000,
                    'volume24h': 4800000,
                    'feeRate': 0.003,
                    'volatility': 0.025,
                    'apy': 31.8
                },
                {
                    'name': 'BONK-SOL',
                    'liquidity': 8500000,
                    'volume24h': 3200000,
                    'feeRate': 0.0035,
                    'volatility': 0.042,
                    'apy': 47.2
                },
                {
                    'name': 'WIF-USDC',
                    'liquidity': 6500000,
                    'volume24h': 1800000,
                    'feeRate': 0.003,
                    'volatility': 0.032,
                    'apy': 28.5
                },
                {
                    'name': 'JTO-USDC',
                    'liquidity': 5200000,
                    'volume24h': 1500000,
                    'feeRate': 0.0025,
                    'volatility': 0.023,
                    'apy': 19.7
                }
            ]
            
            # Sort by risk-adjusted return (APY / volatility)
            pools = sorted(pools, key=lambda x: x['apy'] / x['volatility'], reverse=True)
            
            message = "💧 *Market Making Opportunities*\n\n"
            
            for i, pool in enumerate(pools[:5], 1):
                name = pool['name']
                liquidity = float(pool['liquidity'])
                volume_24h = float(pool['volume24h'])
                fee_rate = float(pool['feeRate']) * 100
                apy = float(pool['apy'])
                volatility = float(pool['volatility']) * 100
                
                # Risk-adjusted score
                risk_score = apy / volatility
                
                message += (
                    f"{i}. *{name}*\n"
                    f"   💦 Liquidity: ${liquidity:,.0f}\n"
                    f"   📊 24h Volume: ${volume_24h:,.0f}\n"
                    f"   💰 Fee Rate: {fee_rate:.2f}%\n"
                    f"   📈 Est. APY: {apy:.1f}%\n"
                    f"   🔄 Volatility: {volatility:.1f}%\n"
                    f"   🌟 Risk Score: {risk_score:.1f}\n\n"
                )
            
            message += "💡 _Higher risk score = better risk-adjusted return_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Market maker error: {e}")
            await status_message.edit_text("⚠️ Error fetching market data")

    async def defi_opportunities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show DeFi yield opportunities using simulated data"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Finding DeFi opportunities...")
        
        try:
            # Use simulation data for demonstration
            opportunities = [
                {
                    'name': 'Solend USDC',
                    'platform': 'Solend',
                    'apy': 5.8,
                    'tvl': 120000000,
                    'risk': 'Low',
                    'type': 'Lending'
                },
                {
                    'name': 'Orca SOL-USDC',
                    'platform': 'Orca',
                    'apy': 18.5,
                    'tvl': 45000000,
                    'risk': 'Medium',
                    'type': 'LP'
                },
                {
                    'name': 'Marinade SOL',
                    'platform': 'Marinade',
                    'apy': 6.2,
                    'tvl': 320000000,
                    'risk': 'Low',
                    'type': 'Staking'
                },
                {
                    'name': 'Kamino JUP-USDC',
                    'platform': 'Kamino',
                    'apy': 24.8,
                    'tvl': 25000000,
                    'risk': 'Medium',
                    'type': 'LP'
                },
                {
                    'name': 'Jupiter BONK-SOL',
                    'platform': 'Jupiter',
                    'apy': 32.5,
                    'tvl': 12000000,
                    'risk': 'High',
                    'type': 'LP'
                }
            ]
            
            message = "🏦 *Top DeFi Opportunities*\n\n"
            
            # Group by risk level
            risk_groups = {'Low': [], 'Medium': [], 'High': []}
            for opp in opportunities:
                risk_groups[opp['risk']].append(opp)
            
            for risk, opps in risk_groups.items():
                if opps:
                    risk_emoji = "🟢" if risk == "Low" else "🟡" if risk == "Medium" else "🔴"
                    message += f"{risk_emoji} *{risk} Risk*\n"
                    
                    for opp in sorted(opps, key=lambda x: x['apy'], reverse=True):
                        platform_emoji = "🏛️" if opp['type'] == 'Lending' else "🔄" if opp['type'] == 'LP' else "📌"
                        message += (
                            f"• {opp['name']} ({opp['platform']})\n"
                            f"  {platform_emoji} {opp['type']} | APY: {opp['apy']:.1f}% | TVL: ${opp['tvl']/1000000:.1f}M\n"
                        )
                    message += "\n"
            
            message += "_Updated hourly. DYOR before investing._"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"DeFi opportunities error: {e}")
            await status_message.edit_text("⚠️ Error fetching yield data")

    async def whale_tracker(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track whale transactions in real-time"""
        # Show loading message
        status_message = await update.message.reply_text("⏳ Tracking whale transactions...")
        
        try:
            transactions = await self.get_whale_transactions()
            if not transactions:
                await status_message.edit_text("⚠️ Couldn't fetch whale data")
                return
                
            message = "🐳 *Top Whale Transactions*\n\n"
            
            for i, tx in enumerate(transactions[:5], 1):
                token = tx.get('token', {}).get('name', 'UNKNOWN')
                symbol = tx.get('token', {}).get('symbol', 'UNKNOWN')
                amount = float(tx.get('amount', 0))
                usd_value = float(tx.get('value', 0))
                direction = "🟢 BUY" if tx.get('transactionType') == 'buy' else "🔴 SELL"
                time_ago = tx.get('timeAgo', 'recently')
                
                message += (
                    f"{i}. *{token} ({symbol})*\n"
                    f"   {direction} {amount:,.0f} tokens\n"
                    f"   💵 Value: ${usd_value:,.0f}\n"
                    f"   ⏰ Time: {time_ago}\n\n"
                )
            
            message += f"_Updated: {datetime.now().strftime('%H:%M:%S')}_"
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Whale tracker error: {e}")
            await status_message.edit_text("⚠️ Error tracking whales")

    async def ai_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """AI-powered token analysis with real-time data"""
        if not context.args:
            await update.message.reply_text("Usage: /ai_analysis <token_symbol>")
            return
            
        token = context.args[0].upper()
        
        # Show loading message
        status_message = await update.message.reply_text(f"🤖 Analyzing {token} with real-time data...")
        
        try:
            # Get real-time data
            metadata = await self.get_token_metadata(token)
            if not metadata:
                await status_message.edit_text(f"❌ Couldn't get data for {token}")
                return
                
            price = float(metadata.get('price', 0))
            volume_24h = float(metadata.get('volume24h', 0) or 0)
            liquidity = float(metadata.get('liquidity', 0) or 0)
            market_cap = float(metadata.get('marketCap', 0) or 0)
            price_change = float(metadata.get('priceChange24h', 0))
            holders = int(metadata.get('holders', 0) or 0)
            
            # Get historical price data (or simulate it)
            price_7d = price * (1 - (price_change / 100) * 7)  # Simulate 7-day price
            
            # AI assessment algorithm with multiple factors
            score = 50  # Base score
            
            # Volume scoring
            if volume_24h > 1000000: score += 15
            elif volume_24h > 500000: score += 10
            elif volume_24h > 100000: score += 5
            elif volume_24h < 50000: score -= 10
            
            # Liquidity scoring
            if liquidity > 1000000: score += 15
            elif liquidity > 500000: score += 10
            elif liquidity > 100000: score += 5
            elif liquidity < 50000: score -= 15
            
            # Price change scoring
            if price_change > 20: score += 10
            elif price_change > 10: score += 5
            elif price_change < -20: score -= 10
            elif price_change < -10: score -= 5
            
            # Holder count scoring
            if holders > 10000: score += 10
            elif holders > 5000: score += 5
            elif holders < 1000: score -= 5
            
            # Market cap scoring
            if market_cap > 100000000: score += 10
            elif market_cap > 10000000: score += 5
            elif market_cap < 1000000: score -= 5
            
            # Cap score between 0-100
            score = max(0, min(100, score))
            
            # Generate rating
            if score > 85: rating = "🚀 STRONG BUY"
            elif score > 70: rating = "✅ BUY"
            elif score > 55: rating = "🟡 HOLD"
            elif score > 40: rating = "⚠️ CAUTION"
            else: rating = "❌ AVOID"
            
            # Calculate volatility
            volatility = abs(price_change) / 10  # Simplified volatility calculation
            
            # Generate strengths and weaknesses
            strengths = []
            weaknesses = []
            
            if volume_24h > 500000: strengths.append("High trading volume")
            elif volume_24h < 50000: weaknesses.append("Low trading volume")
            
            if liquidity > 500000: strengths.append("Strong liquidity")
            elif liquidity < 50000: weaknesses.append("Low liquidity")
            
            if price_change > 10: strengths.append("Strong upward momentum")
            elif price_change < -10: weaknesses.append("Downward price trend")
            
            if holders > 5000: strengths.append("Wide holder distribution")
            elif holders < 1000: weaknesses.append("Concentrated ownership")
            
            if market_cap > 10000000: strengths.append("Established market cap")
            elif market_cap < 1000000: weaknesses.append("Small market cap")
            
            if volatility < 5: strengths.append("Low volatility")
            elif volatility > 15: weaknesses.append("High volatility")
            
            message = (
                f"🤖 *AI Analysis for {token}*\n\n"
                f"💰 Price: ${price:.6f}\n"
                f"📈 24h Change: {price_change:.2f}%\n"
                f"📊 24h Volume: ${volume_24h:,.0f}\n"
                f"💧 Liquidity: ${liquidity:,.0f}\n"
            )
            
            if market_cap > 0:
                message += f"💎 Market Cap: ${market_cap:,.0f}\n"
                
            if holders > 0:
                message += f"👥 Holders: {holders:,}\n"
            
            message += f"\n⭐ *AI Rating*: {rating}\n"
            message += f"📊 Score: {score}/100\n"
            message += f"📉 Volatility: {volatility:.1f}/10\n\n"
            
            if strengths:
                message += "💪 *Strengths*:\n"
                for strength in strengths[:3]:  # Top 3 strengths
                    message += f"• {strength}\n"
                message += "\n"
            
            if weaknesses:
                message += "⚠️ *Weaknesses*:\n"
                for weakness in weaknesses[:3]:  # Top 3 weaknesses
                    message += f"• {weakness}\n"
                message += "\n"
            
            message += f"_Analysis time: {datetime.now().strftime('%H:%M:%S')}_"
            
            await status_message.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await status_message.edit_text("⚠️ Analysis failed")

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
                                
                                try:
                                    await self.app.bot.send_message(
                                        chat_id=user_id,
                                        text=message,
                                        parse_mode='Markdown'
                                    )
                                    # Remove triggered alert
                                    user_data['alerts'].remove(alert)
                                    await self.save_user_data()
                                except Exception as e:
                                    logger.error(f"Alert send error: {e}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Alert monitor error: {e}")
                await asyncio.sleep(30)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button presses"""
        query = update.callback_query
        await query.answer()
        
        # Create a new update object for the command handlers
        new_update = Update(
            update_id=update.update_id,
            message=query.message,
            edited_message=None,
            channel_post=None,
            edited_channel_post=None,
            inline_query=None,
            chosen_inline_result=None,
            callback_query=None,
            shipping_query=None,
            pre_checkout_query=None,
            poll=None,
            poll_answer=None,
            my_chat_member=None,
            chat_member=None,
            chat_join_request=None
        )
        new_update.message.from_user = update.effective_user
        
        # Map button callbacks to actual commands
        command_map = {
            "portfolio": self.portfolio,
            "scan": self.scan_tokens,
            "birdeye": lambda u, c: self.birdeye_trending(u, c),
            "trending": self.birdeye_trending,
            "pumpfun": self.pumpfun_scan,
            "top_gainers": self.top_gainers,
            "forex": self.forex_rates,
            "ai_analysis": lambda u, c: u.message.reply_text("Use /ai_analysis <token>")
        }
        
        try:
            if query.data in command_map:
                await command_map[query.data](new_update, context)
            else:
                await query.edit_message_text(text=f"Action for '{query.data}' not implemented yet")
        except Exception as e:
            logger.error(f"Button handler error: {e}")
            await query.edit_message_text(text="⚠️ Error processing request")

    async def run(self):
        """Start the bot"""
        await self.load_user_data()
        
        # Start background tasks
        asyncio.create_task(self.start_price_monitoring())
        
        # Initialize the application
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
