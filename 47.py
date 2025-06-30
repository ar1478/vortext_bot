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
        
        # API endpoints and keys
        self.api_keys = {
            'birdeye': '797cf979b7754efa9bf6f5e1a1370f7a',
            'apilayer': 'pKtM2FQSYAgwBKOYwFowIwHNDJG49UNk'
        }
        
        self.apis = {
            'birdeye': 'https://public-api.birdeye.so',
            'dexscreener': 'https://api.dexscreener.com/latest/dex',
            'jupiter': 'https://price.jup.ag/v4/price',
            'apilayer_forex': 'https://api.apilayer.com/fixer',
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
            CommandHandler("forexpair", self.forex_pair),
            CommandHandler("birdeye", self.birdeye_search),
            CommandHandler("trending", self.birdeye_trending),
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
             InlineKeyboardButton("🐦 BirdEye Search", callback_data="birdeye")],
            [InlineKeyboardButton("⭐ Watchlist", callback_data="watchlist"),
             InlineKeyboardButton("🔥 Trending", callback_data="trending")],
            [InlineKeyboardButton("📈 Top Gainers", callback_data="top_gainers"),
             InlineKeyboardButton("💱 Forex Rates", callback_data="forex")],
            [InlineKeyboardButton("💰 Forex Pairs", callback_data="forex_pairs")]
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
        """Scan trending tokens using BirdEye and DexScreener"""
        try:
            # First try BirdEye API
            birdeye_data = await self.get_birdeye_trending()
            
            if birdeye_data:
                message = "🐦 *BirdEye Trending Tokens*\n\n"
                
                for i, token in enumerate(birdeye_data[:8], 1):
                    price = token.get('price', 0)
                    change_24h = token.get('priceChange24hPercent', 0)
                    volume = token.get('volume24h', 0)
                    name = token.get('name', 'Unknown')
                    symbol = token.get('symbol', 'N/A')
                    
                    emoji = "🟢" if change_24h > 0 else "🔴"
                    
                    message += (
                        f"{i}. {emoji} *{name} ({symbol})*\n"
                        f"   💰 ${price:.6f}\n"
                        f"   📊 {change_24h:+.2f}% (24h)\n"
                        f"   📈 Vol: ${volume:,.0f}\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
                return
            
            # Fallback to DexScreener
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
        """Show forex rates using API Layer"""
        try:
            headers = {'apikey': self.api_keys['apilayer']}
            url = f"{self.apis['apilayer_forex']}/latest"
            params = {'base': 'USD'}
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success') and 'rates' in data:
                rates = data['rates']
                major_pairs = ['EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'CNY', 'INR']
                
                message = "💱 *Major Forex Rates (USD Base)*\n\n"
                
                for currency in major_pairs:
                    if currency in rates:
                        rate = rates[currency]
                        message += f"🌍 USD/{currency}: {rate:.4f}\n"
                
                message += f"\n📅 Updated: {data.get('date', 'Unknown')}"
                
                keyboard = [[InlineKeyboardButton("💰 Check Specific Pairs", callback_data="forex_pairs")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    message, 
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("❌ Unable to fetch forex data")
                
        except Exception as e:
            logger.error(f"Forex error: {e}")
            await update.message.reply_text("⚠️ Error fetching forex rates")
    
    async def forex_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get specific forex pair rates"""
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /forexpair <from> <to>\n"
                "Example: /forexpair EUR USD"
            )
            return
        
        from_currency = context.args[0].upper()
        to_currency = context.args[1].upper()
        
        try:
            headers = {'apikey': self.api_keys['apilayer']}
            url = f"{self.apis['apilayer_forex']}/convert"
            params = {
                'from': from_currency,
                'to': to_currency,
                'amount': 1
            }
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success'):
                rate = data['result']
                
                message = (
                    f"💱 *Forex Conversion*\n\n"
                    f"1 {from_currency} = {rate:.4f} {to_currency}\n"
                    f"📅 Date: {data.get('date', 'Unknown')}\n"
                    f"⏰ Updated: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    f"❌ Invalid currency pair: {from_currency}/{to_currency}"
                )
                
        except Exception as e:
            logger.error(f"Forex pair error: {e}")
            await update.message.reply_text("⚠️ Error fetching forex pair data")
    
    async def birdeye_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search tokens using BirdEye"""
        if not context.args:
            await update.message.reply_text(
                "Usage: /birdeye <token_name_or_symbol>\n"
                "Example: /birdeye BONK"
            )
            return
        
        query = " ".join(context.args)
        
        try:
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/search"
            params = {'keyword': query, 'limit': 10}
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success') and data.get('data', {}).get('tokens'):
                tokens = data['data']['tokens'][:5]  # Top 5 results
                
                message = f"🐦 *BirdEye Search Results for '{query}'*\n\n"
                
                for i, token in enumerate(tokens, 1):
                    name = token.get('name', 'Unknown')
                    symbol = token.get('symbol', 'N/A')
                    price = token.get('price', 0)
                    change_24h = token.get('priceChange24hPercent', 0)
                    mc = token.get('mc', 0)
                    
                    emoji = "🟢" if change_24h > 0 else "🔴"
                    
                    message += (
                        f"{i}. {emoji} *{name} ({symbol})*\n"
                        f"   💰 ${price:.6f}\n"
                        f"   📊 {change_24h:+.2f}% (24h)\n"
                        f"   💎 MC: ${mc:,.0f}\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ No tokens found for '{query}'")
                
        except Exception as e:
            logger.error(f"BirdEye search error: {e}")
            await update.message.reply_text("⚠️ Error searching tokens")
    
    async def birdeye_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get trending tokens from BirdEye"""
        try:
            trending_data = await self.get_birdeye_trending()
            
            if trending_data:
                message = "🔥 *BirdEye Trending Tokens*\n\n"
                
                for i, token in enumerate(trending_data[:10], 1):
                    name = token.get('name', 'Unknown')
                    symbol = token.get('symbol', 'N/A')
                    price = token.get('price', 0)
                    change_24h = token.get('priceChange24hPercent', 0)
                    volume = token.get('volume24h', 0)
                    
                    emoji = "🟢" if change_24h > 0 else "🔴"
                    
                    message += (
                        f"{i}. {emoji} *{name} ({symbol})*\n"
                        f"   💰 ${price:.6f}\n"
                        f"   📊 {change_24h:+.2f}% (24h)\n"
                        f"   📈 Vol: ${volume:,.0f}\n\n"
                    )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Unable to fetch trending data")
                
        except Exception as e:
            logger.error(f"BirdEye trending error: {e}")
            await update.message.reply_text("⚠️ Error fetching trending tokens")
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
            # Try BirdEye first
            birdeye_price = await self.get_birdeye_price(token)
            if birdeye_price:
                return birdeye_price
            
            # Try Jupiter API (for Solana tokens)
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
    
    async def get_birdeye_price(self, token: str) -> Optional[Dict]:
        """Get token price from BirdEye"""
        try:
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/price"
            params = {'address': token}
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success') and 'data' in data:
                return {'price': float(data['data']['value'])}
                
        except Exception as e:
            logger.error(f"BirdEye price error: {e}")
        
        return None
    
    async def get_birdeye_trending(self) -> Optional[List[Dict]]:
        """Get trending tokens from BirdEye"""
        try:
            headers = {'X-API-KEY': self.api_keys['birdeye']}
            url = f"{self.apis['birdeye']}/defi/trending"
            params = {'limit': 20}
            
            response = await self.client.get(url, headers=headers, params=params)
            data = response.json()
            
            if data.get('success') and 'data' in data:
                return data['data']
                
        except Exception as e:
            logger.error(f"BirdEye trending error: {e}")
        
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
        elif query.data == "forex_pairs":
            await query.edit_message_text(
                "💰 *Forex Pair Converter*\n\n"
                "Use: `/forexpair <from> <to>`\n"
                "Example: `/forexpair EUR USD`\n\n"
                "Popular pairs:\n"
                "• EUR/USD, GBP/USD, USD/JPY\n"
                "• USD/CAD, AUD/USD, USD/CHF",
                parse_mode='Markdown'
            )
        elif query.data == "birdeye":
            await query.edit_message_text(
                "🐦 *BirdEye Search*\n\n"
                "Use: `/birdeye <token_name>`\n"
                "Example: `/birdeye BONK`\n\n"
                "Or use `/trending` for trending tokens",
                parse_mode='Markdown'
            )
        elif query.data == "trending":
            await self.birdeye_trending(update, context)
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
    BOT_TOKEN = "8152282783:AAH0ylvc63x_u1e15ST0-4zjQe_K4b4bVRc"  # Get from @BotFather
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Please set your Telegram bot token!")
        return
    
    bot = TradingBot(BOT_TOKEN)
    await bot.run()

if __name__ == "__main__":
    # Install required packages:
    # pip install python-telegram-bot httpx pandas numpy aiofiles
    
    asyncio.run(main())
