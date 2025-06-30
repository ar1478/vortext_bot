import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiofiles
import httpx
import pandas as pd
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.users_data = {}
        self.watchlists = {}
        self.alerts = {}
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # API endpoints
        self.apis = {
            'dexscreener': 'https://api.dexscreener.com/latest/dex',
            'jupiter': 'https://price.jup.ag/v4/price',
            'forex': 'https://api.exchangerate-api.com/v4/latest/USD',
            'coingecko': 'https://api.coingecko.com/api/v3'
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
            CommandHandler("top", self.top_gainers),
            CallbackQueryHandler(self.button_handler)
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        keyboard = [
            [InlineKeyboardButton("📊 Portfolio", callback_data="portfolio")],
            [InlineKeyboardButton("🔍 Scan Markets", callback_data="scan"),
             InlineKeyboardButton("⭐ Watchlist", callback_data="watchlist")],
            [InlineKeyboardButton("📈 Top Gainers", callback_data="top_gainers"),
             InlineKeyboardButton("💱 Forex", callback_data="forex")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *Multi-Platform Trading Bot*\n\n"
            "Track Solana, Pump.fun, and Forex markets in real-time!\n\n"
            "Choose an option below:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register user"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            self.users_data[user_id] = {
                'registered': datetime.now().isoformat(),
                'portfolio': {},
                'watchlist': [],
                'total_pnl': 0.0
            }
            await self.save_user_data()
            
            await update.message.reply_text(
                "✅ Registration successful!\n"
                "You can now use all bot features."
            )
        else:
            await update.message.reply_text("📝 You're already registered!")
    
    async def scan_tokens(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Scan trending Solana tokens"""
        try:
            # Get trending tokens from DexScreener
            url = f"{self.apis['dexscreener']}/pairs/solana"
            response = await self.client.get(url)
            data = response.json()
            
            if data and 'pairs' in data:
                pairs = data['pairs'][:10]  # Top 10
                
                message = "🔥 *Trending Solana Tokens*\n\n"
                
                for i, pair in enumerate(pairs, 1):
                    if pair and 'baseToken' in pair:
                        token = pair['baseToken']
                        price = float(pair.get('priceUsd', 0))
                        change_24h = float(pair.get('priceChange', {}).get('h24', 0))
                        volume = float(pair.get('volume', {}).get('h24', 0))
                        
                        emoji = "🟢" if change_24h > 0 else "🔴"
                        
                        message += (
                            f"{i}. {emoji} *{token.get('name', 'Unknown')}*\n"
                            f"   💰 ${price:.6f}\n"
                            f"   📊 {change_24h:+.2f}% (24h)\n"
                            f"   📈 Vol: ${volume:,.0f}\n\n"
                        )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Unable to fetch token data")
                
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await update.message.reply_text("⚠️ Error scanning tokens")
    
    async def add_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add token to watchlist"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "Usage: /watch <token_symbol>\n"
                "Example: /watch SOL"
            )
            return
        
        token = context.args[0].upper()
        
        # Get token price
        price_data = await self.get_token_price(token)
        
        if price_data:
            if user_id not in self.watchlists:
                self.watchlists[user_id] = []
            
            watch_item = {
                'token': token,
                'price': price_data['price'],
                'added_at': datetime.now().isoformat()
            }
            
            # Check if already in watchlist
            if not any(item['token'] == token for item in self.watchlists[user_id]):
                self.watchlists[user_id].append(watch_item)
                await self.save_watchlist_data()
                
                await update.message.reply_text(
                    f"✅ Added {token} to watchlist\n"
                    f"Current price: ${price_data['price']:.6f}"
                )
            else:
                await update.message.reply_text(f"📝 {token} already in watchlist")
        else:
            await update.message.reply_text(f"❌ Token {token} not found")
    
    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show portfolio"""
        user_id = update.effective_user.id
        
        if user_id not in self.users_data:
            await update.message.reply_text("Please /register first")
            return
        
        portfolio = self.users_data[user_id].get('portfolio', {})
        
        if not portfolio:
            await update.message.reply_text(
                "📊 *Your Portfolio is Empty*\n\n"
                "Add tokens with: /add_position <token> <amount> <entry_price>",
                parse_mode='Markdown'
            )
            return
        
        message = "📊 *Your Portfolio*\n\n"
        total_value = 0
        total_pnl = 0
        
        for token, data in portfolio.items():
            current_price_data = await self.get_token_price(token)
            
            if current_price_data:
                current_price = current_price_data['price']
                amount = data['amount']
                entry_price = data['entry_price']
                
                current_value = amount * current_price
                entry_value = amount * entry_price
                pnl = current_value - entry_value
                pnl_percent = (pnl / entry_value) * 100
                
                total_value += current_value
                total_pnl += pnl
                
                emoji = "🟢" if pnl > 0 else "🔴"
                
                message += (
                    f"{emoji} *{token}*\n"
                    f"   Amount: {amount:,.2f}\n"
                    f"   Entry: ${entry_price:.6f}\n"
                    f"   Current: ${current_price:.6f}\n"
                    f"   Value: ${current_value:,.2f}\n"
                    f"   PnL: ${pnl:+.2f} ({pnl_percent:+.1f}%)\n\n"
                )
        
        pnl_emoji = "🟢" if total_pnl > 0 else "🔴"
        message += f"{pnl_emoji} *Total PnL: ${total_pnl:+.2f}*"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def forex_rates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show forex rates"""
        try:
            response = await self.client.get(self.apis['forex'])
            data = response.json()
            
            if 'rates' in data:
                rates = data['rates']
                major_pairs = ['EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF']
                
                message = "💱 *Major Forex Rates (USD Base)*\n\n"
                
                for currency in major_pairs:
                    if currency in rates:
                        rate = rates[currency]
                        message += f"🌍 USD/{currency}: {rate:.4f}\n"
                
                message += f"\n📅 Updated: {data.get('date', 'Unknown')}"
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Unable to fetch forex data")
                
        except Exception as e:
            logger.error(f"Forex error: {e}")
            await update.message.reply_text("⚠️ Error fetching forex rates")
    
    async def top_gainers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show top gaining tokens"""
        try:
            url = f"{self.apis['coingecko']}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'price_change_percentage_24h_desc',
                'per_page': 10,
                'page': 1
            }
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            if data:
                message = "🚀 *Top 10 Gainers (24h)*\n\n"
                
                for i, coin in enumerate(data, 1):
                    name = coin['name']
                    symbol = coin['symbol'].upper()
                    price = coin['current_price']
                    change = coin['price_change_percentage_24h']
                    
                    message += (
                        f"{i}. 🟢 *{name} ({symbol})*\n"
                        f"   💰 ${price:.6f}\n"
                        f"   📈 +{change:.2f}%\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Unable to fetch gainers data")
                
        except Exception as e:
            logger.error(f"Top gainers error: {e}")
            await update.message.reply_text("⚠️ Error fetching top gainers")
    
    async def get_token_price(self, token: str) -> Optional[Dict]:
        """Get token price from multiple sources"""
        try:
            # Try Jupiter API first (for Solana tokens)
            response = await self.client.get(f"{self.apis['jupiter']}?ids={token}")
            data = response.json()
            
            if 'data' in data and token in data['data']:
                return {'price': float(data['data'][token]['price'])}
            
            # Fallback to CoinGecko
            url = f"{self.apis['coingecko']}/simple/price"
            params = {'ids': token.lower(), 'vs_currencies': 'usd'}
            
            response = await self.client.get(url, params=params)
            data = response.json()
            
            if token.lower() in data:
                return {'price': float(data[token.lower()]['usd'])}
                
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
        
        return None
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "portfolio":
            await self.portfolio(update, context)
        elif query.data == "scan":
            await self.scan_tokens(update, context)
        elif query.data == "forex":
            await self.forex_rates(update, context)
        elif query.data == "top_gainers":
            await self.top_gainers(update, context)
    
    async def save_user_data(self):
        """Save user data to file"""
        try:
            async with aiofiles.open('users_data.json', 'w') as f:
                await f.write(json.dumps(self.users_data, indent=2))
        except Exception as e:
            logger.error(f"Save user data error: {e}")
    
    async def save_watchlist_data(self):
        """Save watchlist data to file"""
        try:
            async with aiofiles.open('watchlists.json', 'w') as f:
                await f.write(json.dumps(self.watchlists, indent=2))
        except Exception as e:
            logger.error(f"Save watchlist error: {e}")
    
    async def load_data(self):
        """Load saved data"""
        try:
            if os.path.exists('users_data.json'):
                async with aiofiles.open('users_data.json', 'r') as f:
                    content = await f.read()
                    self.users_data = json.loads(content)
            
            if os.path.exists('watchlists.json'):
                async with aiofiles.open('watchlists.json', 'r') as f:
                    content = await f.read()
                    self.watchlists = json.loads(content)
                    
        except Exception as e:
            logger.error(f"Load data error: {e}")
    
    async def start_price_monitoring(self):
        """Background task for price monitoring"""
        while True:
            try:
                # Check watchlists for significant price changes
                for user_id, watchlist in self.watchlists.items():
                    for item in watchlist:
                        current_data = await self.get_token_price(item['token'])
                        if current_data:
                            old_price = item['price']
                            new_price = current_data['price']
                            change_percent = ((new_price - old_price) / old_price) * 100
                            
                            # Alert on 5%+ change
                            if abs(change_percent) >= 5:
                                emoji = "🚀" if change_percent > 0 else "📉"
                                message = (
                                    f"{emoji} *Price Alert*\n\n"
                                    f"Token: {item['token']}\n"
                                    f"Price: ${new_price:.6f}\n"
                                    f"Change: {change_percent:+.2f}%"
                                )
                                
                                # Send alert to user
                                await self.app.bot.send_message(
                                    chat_id=user_id,
                                    text=message,
                                    parse_mode='Markdown'
                                )
                                
                                # Update stored price
                                item['price'] = new_price
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Price monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def run(self):
        """Run the bot"""
        await self.load_data()
        
        # Start background tasks
        asyncio.create_task(self.start_price_monitoring())
        
        # Start the bot
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Trading bot started successfully!")
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await self.client.aclose()
            await self.app.stop()

# Usage example
async def main():
    BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Get from @BotFather
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Please set your Telegram bot token!")
        return
    
    bot = TradingBot(BOT_TOKEN)
    await bot.run()

if __name__ == "__main__":
    # Install required packages:
    # pip install python-telegram-bot httpx pandas numpy aiofiles
    
    asyncio.run(main())
