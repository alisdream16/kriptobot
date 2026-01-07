"""
KriptoBot - Telegram Kontrol Botu
Telegram üzerinden bot'u kontrol et
"""
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from loguru import logger
from bybit_api import BybitTrader
from auto_trader import AutoTrader
import config

# Telegram Bot Token
BOT_TOKEN = "8513037447:AAFDrByRG2tv8FxcOf9JRDjMxDU2wzgUZXY"

# Sadece sen kullanabilsin (Telegram User ID)
ALLOWED_USERS = []  # Boş bırakırsan herkes kullanabilir, ID ekleyebilirsin

# Global trader instance
trader = BybitTrader()
auto_trader = AutoTrader()

logger.add("telegram_bot.log", rotation="1 day", retention="7 days")


async def is_authorized(update: Update) -> bool:
    """Kullanıcı yetkili mi kontrol et"""
    if not ALLOWED_USERS:
        return True
    return update.effective_user.id in ALLOWED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hoşgeldin mesajı"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    user_id = update.effective_user.id
    welcome = f"""
🤖 *KriptoBot'a Hoşgeldin!*

📊 *Komutlar:*
/analiz - Piyasa analizi yap ve işlem aç
/durum - Açık pozisyonları göster
/bakiye - Bakiye bilgisi
/kapat - Tüm pozisyonları kapat
/fiyat [COIN] - Coin fiyatı (örn: /fiyat BTC)

🔑 Senin Telegram ID: `{user_id}`
_(Güvenlik için ALLOWED_USERS'a ekleyebilirsin)_
"""
    await update.message.reply_text(welcome, parse_mode='Markdown')


async def analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Piyasa analizi yap ve işlem aç"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    await update.message.reply_text("🔍 Analiz başlatılıyor...")
    
    try:
        # Analiz yap
        auto_trader.run_analysis()
        
        # Sonuçları al
        positions = trader.get_all_positions()
        balance = trader.get_available_balance()
        
        if positions:
            pos_text = "\n".join([
                f"• {p['symbol']} {p['side']} | PnL: {float(p['unrealized_pnl']):+.2f} USDT"
                for p in positions
            ])
            result = f"""
✅ *Analiz Tamamlandı!*

💰 Bakiye: {balance:.2f} USDT
📊 Açık Pozisyonlar ({len(positions)}):
{pos_text}
"""
        else:
            result = f"""
✅ *Analiz Tamamlandı!*

💰 Bakiye: {balance:.2f} USDT
📭 Açık pozisyon yok

_(Sinyal bulunamadı veya güven skoru düşük)_
"""
        
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Analiz hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")


async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Açık pozisyonları göster"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    try:
        positions = trader.get_all_positions()
        balance = trader.get_available_balance()
        
        if positions:
            total_pnl = sum(float(p['unrealized_pnl']) for p in positions)
            pos_text = ""
            for p in positions:
                pnl = float(p['unrealized_pnl'])
                emoji = "🟢" if pnl >= 0 else "🔴"
                pos_text += f"{emoji} *{p['symbol']}* {p['side']}\n"
                pos_text += f"   Entry: ${p['entry_price']} | PnL: {pnl:+.2f} USDT\n\n"
            
            result = f"""
📊 *AÇIK POZİSYONLAR* ({len(positions)})

{pos_text}
💰 Bakiye: {balance:.2f} USDT
📈 Toplam PnL: {total_pnl:+.2f} USDT
"""
        else:
            result = f"""
📭 *Açık pozisyon yok*

💰 Bakiye: {balance:.2f} USDT
"""
        
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Durum hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")


async def bakiye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bakiye bilgisi"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    try:
        balance = trader.get_available_balance()
        positions = trader.get_all_positions()
        total_pnl = sum(float(p['unrealized_pnl']) for p in positions)
        
        result = f"""
💰 *BAKİYE BİLGİSİ*

💵 Kullanılabilir: {balance:.2f} USDT
📊 Açık Pozisyon: {len(positions)}
📈 Toplam PnL: {total_pnl:+.2f} USDT
"""
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Bakiye hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")


async def kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm pozisyonları kapat"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    await update.message.reply_text("🔄 Pozisyonlar kapatılıyor...")
    
    try:
        positions = trader.get_all_positions()
        
        if not positions:
            await update.message.reply_text("📭 Kapatılacak pozisyon yok!")
            return
        
        results = trader.close_all_positions()
        
        closed_count = len([r for r in results if r.get('result', {}).get('success')])
        
        result = f"""
✅ *POZİSYONLAR KAPATILDI*

📊 Kapatılan: {closed_count}/{len(positions)}
"""
        await update.message.reply_text(result, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Kapatma hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")


async def fiyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Coin fiyatı göster"""
    if not await is_authorized(update):
        await update.message.reply_text("⛔ Yetkisiz erişim!")
        return
    
    try:
        if not context.args:
            await update.message.reply_text("❓ Kullanım: /fiyat BTC")
            return
        
        coin = context.args[0].upper()
        symbol = f"{coin}USDT"
        
        price = trader.get_current_price(symbol)
        
        if price > 0:
            result = f"""
💲 *{symbol}*

Fiyat: ${price:,.4f}
"""
            await update.message.reply_text(result, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ {symbol} bulunamadı!")
            
    except Exception as e:
        logger.error(f"Fiyat hatası: {e}")
        await update.message.reply_text(f"❌ Hata: {e}")


def main():
    """Telegram bot'u başlat"""
    logger.info("🤖 Telegram Bot başlatılıyor...")
    
    # Application oluştur
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Komutları ekle
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analiz", analiz))
    app.add_handler(CommandHandler("durum", durum))
    app.add_handler(CommandHandler("bakiye", bakiye))
    app.add_handler(CommandHandler("kapat", kapat))
    app.add_handler(CommandHandler("fiyat", fiyat))
    
    logger.info("""
╔══════════════════════════════════════════════════════════╗
║          🤖 TELEGRAM BOT BAŞLADI                        ║
║                                                          ║
║  Komutlar:                                               ║
║  /analiz - Piyasa analizi ve işlem aç                   ║
║  /durum  - Açık pozisyonları göster                     ║
║  /bakiye - Bakiye bilgisi                               ║
║  /kapat  - Tüm pozisyonları kapat                       ║
║  /fiyat  - Coin fiyatı                                  ║
╚══════════════════════════════════════════════════════════╝
""")
    
    # Bot'u çalıştır
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

