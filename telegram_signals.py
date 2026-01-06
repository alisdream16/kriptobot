"""
Telegram Sinyal Okuyucu
Silver Trade ve diğer kanallardan sinyalleri okur, Gemini ile analiz eder
"""
import asyncio
import json
import base64
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import google.generativeai as genai
from loguru import logger
from bybit_api import BybitTrader
import config

# Logger
logger.add("telegram_signals.log", rotation="1 day", retention="7 days")

# Gemini AI
genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-lite')

# Telegram Client
client = TelegramClient(
    'signal_session',
    int(config.TELEGRAM_API_ID),
    config.TELEGRAM_API_HASH
)


class TelegramSignalReader:
    """Telegram kanallarından sinyal okuyucu"""
    
    def __init__(self):
        self.trader = BybitTrader()
        self.channels = config.TELEGRAM_CHANNELS
        self.processed_messages = set()  # Tekrar işlememek için
        
    async def analyze_with_gemini(self, text: str, image_data: bytes = None) -> dict:
        """Mesajı Gemini ile analiz et"""
        
        prompt = f"""
Sen profesyonel bir kripto sinyal analistisin. Aşağıdaki Telegram mesajını/görselini analiz et ve işlem sinyali çıkar.

MESAJ:
{text}

KURALLAR:
1. Eğer bu bir trading sinyali ise (LONG/SHORT, alım/satım, entry/giriş) bilgilerini çıkar
2. Coin/parite adını bul (örn: BTC, ETH, SOL)
3. Yön: LONG mu SHORT mu?
4. Entry (giriş) fiyatları
5. Take Profit (TP) seviyeleri
6. Stop Loss (SL) seviyesi
7. Eğer sinyal DEĞİLSE, "is_signal": false döndür

JSON FORMATI (sadece JSON, başka bir şey yazma):
{{
    "is_signal": true/false,
    "symbol": "BTCUSDT",
    "side": "LONG" veya "SHORT",
    "entry_prices": [95000, 94500],
    "take_profits": [96000, 97000, 98000],
    "stop_loss": 93000,
    "leverage": 20,
    "confidence": 8,
    "reason": "Kısa açıklama"
}}

Eğer sinyal değilse:
{{
    "is_signal": false,
    "reason": "Neden sinyal değil"
}}
"""
        
        try:
            if image_data:
                # Görsel ile analiz
                import PIL.Image
                import io
                image = PIL.Image.open(io.BytesIO(image_data))
                response = model.generate_content([prompt, image])
            else:
                # Sadece metin
                response = model.generate_content(prompt)
            
            text_response = response.text.strip()
            
            # JSON parse
            if "```json" in text_response:
                text_response = text_response.split("```json")[1].split("```")[0]
            elif "```" in text_response:
                text_response = text_response.split("```")[1].split("```")[0]
            
            return json.loads(text_response)
            
        except Exception as e:
            logger.error(f"Gemini analiz hatası: {e}")
            return {"is_signal": False, "reason": str(e)}
    
    def format_symbol(self, symbol: str) -> str:
        """Sembolü Bybit formatına çevir"""
        symbol = symbol.upper().strip()
        
        # Yaygın formatları düzelt
        symbol = symbol.replace("/", "").replace("-", "")
        
        # USDT ekle eğer yoksa
        if not symbol.endswith("USDT") and not symbol.endswith("USD"):
            symbol = symbol + "USDT"
        
        # USD -> USDT
        if symbol.endswith("USD") and not symbol.endswith("USDT"):
            symbol = symbol + "T"
        
        return symbol
    
    async def execute_signal(self, signal: dict):
        """Sinyali işleme al"""
        try:
            symbol = self.format_symbol(signal.get('symbol', ''))
            side = signal.get('side', '').upper()
            entry_prices = signal.get('entry_prices', [])
            take_profits = signal.get('take_profits', [])
            stop_loss = signal.get('stop_loss')
            confidence = signal.get('confidence', 0)
            
            # Validasyon
            if not symbol or not side:
                logger.warning("Geçersiz sinyal: symbol veya side eksik")
                return
            
            if confidence < 6:
                logger.info(f"Düşük güven sinyali atlandı: {symbol} ({confidence}/10)")
                return
            
            # Mevcut pozisyon kontrolü
            positions = self.trader.get_all_positions()
            open_symbols = [p['symbol'] for p in positions]
            
            if symbol in open_symbols:
                logger.info(f"{symbol} zaten açık pozisyon var, atlanıyor")
                return
            
            # Bakiye kontrolü
            balance = self.trader.get_available_balance()
            if balance < 5:
                logger.warning(f"Yetersiz bakiye: {balance} USDT")
                return
            
            # İlk entry ve SL/TP al
            entry = entry_prices[0] if entry_prices else None
            tp = take_profits[0] if take_profits else None
            sl = stop_loss
            
            logger.info(f"""
📡 TELEGRAM SİNYALİ ALINDI!
   Kanal: Silver Trade
   Parite: {symbol}
   Yön: {side}
   Entry: {entry}
   TP: {take_profits}
   SL: {sl}
   Güven: {confidence}/10
""")
            
            # İşlem aç
            result = self.trader.open_trade(
                symbol=symbol,
                side=side,
                stop_loss=sl,
                take_profit=tp
            )
            
            if result.get('success'):
                logger.success(f"✅ {symbol} {side} POZİSYON AÇILDI!")
            else:
                logger.error(f"❌ İşlem hatası: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Sinyal işleme hatası: {e}")
    
    async def handle_message(self, event):
        """Yeni mesajı işle"""
        try:
            message = event.message
            
            # Tekrar kontrol
            if message.id in self.processed_messages:
                return
            self.processed_messages.add(message.id)
            
            # Son 1000 mesajı tut
            if len(self.processed_messages) > 1000:
                self.processed_messages = set(list(self.processed_messages)[-500:])
            
            text = message.text or message.message or ""
            image_data = None
            
            # Görsel varsa indir
            if message.media:
                if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                    try:
                        image_data = await client.download_media(message, bytes)
                    except:
                        pass
            
            # Çok kısa mesajları atla
            if len(text) < 10 and not image_data:
                return
            
            logger.info(f"📩 Yeni mesaj: {text[:100]}...")
            
            # Gemini ile analiz
            signal = await self.analyze_with_gemini(text, image_data)
            
            if signal.get('is_signal'):
                await self.execute_signal(signal)
            else:
                logger.debug(f"Sinyal değil: {signal.get('reason', 'N/A')}")
                
        except Exception as e:
            logger.error(f"Mesaj işleme hatası: {e}")
    
    async def start(self):
        """Telegram dinleyiciyi başlat"""
        logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║          📡 TELEGRAM SİNYAL OKUYUCU BAŞLADI                 ║
║                                                              ║
║  Dinlenen Kanallar:                                          ║
║  {', '.join(self.channels):<52} ║
╚══════════════════════════════════════════════════════════════╝
""")
        
        await client.start(
            phone=config.TELEGRAM_PHONE,
            password=config.TELEGRAM_PASSWORD if hasattr(config, 'TELEGRAM_PASSWORD') and config.TELEGRAM_PASSWORD else None
        )
        logger.info("✅ Telegram'a bağlandı")
        
        # Kanalları bul ve dinle
        for channel_name in self.channels:
            try:
                # Kanal entity'sini al
                entity = await client.get_entity(channel_name)
                logger.info(f"✅ Kanal bulundu: {channel_name}")
                
                # Event handler ekle
                @client.on(events.NewMessage(chats=entity))
                async def handler(event):
                    await self.handle_message(event)
                    
            except Exception as e:
                logger.error(f"❌ Kanal bulunamadı: {channel_name} - {e}")
        
        logger.info("🎧 Mesajlar dinleniyor...")
        await client.run_until_disconnected()


async def main():
    reader = TelegramSignalReader()
    await reader.start()


if __name__ == "__main__":
    asyncio.run(main())
