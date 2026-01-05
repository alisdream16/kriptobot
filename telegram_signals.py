"""
Telegram Sinyal Okuyucu Modülü
Silver Trader VIP ve Balina Sinyalleri kanallarından sinyal okur
"""
import re
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Message
from loguru import logger
import config


@dataclass
class TradingSignal:
    """Trading sinyali veri yapısı"""
    coin: str                          # Coin sembolü (örn: BTC, ETH)
    side: str                          # LONG veya SHORT
    entries: List[float]               # Giriş fiyatları
    take_profits: List[float]          # TP fiyatları
    stop_loss: float                   # Stop loss fiyatı
    leverage: int = 20                 # Kaldıraç
    source: str = ""                   # Sinyal kaynağı
    timestamp: datetime = None         # Sinyal zamanı
    raw_message: str = ""              # Orijinal mesaj
    confidence: float = 0.0            # Güven skoru (0-1)
    

class SignalParser:
    """Telegram mesajlarından sinyal ayrıştırıcı"""
    
    # Coin pattern - USDT veya BTC çiftleri
    COIN_PATTERNS = [
        r'(?:🪙|💰|📊|🔥|⚡)?\s*#?([A-Z]{2,10})(?:/|_)?(?:USDT|USD|BTC)',
        r'(?:Coin|Symbol|Çift|Pair)[:\s]*#?([A-Z]{2,10})',
        r'\$([A-Z]{2,10})',
    ]
    
    # Long/Short pattern
    SIDE_PATTERNS = [
        r'(LONG|SHORT|Long|Short|ALIŞ|SATIŞ|BUY|SELL)',
        r'(?:Yön|Direction|Side)[:\s]*(LONG|SHORT|Long|Short)',
        r'(🟢|🔴|📈|📉)',  # Emoji bazlı
    ]
    
    # Fiyat pattern
    PRICE_PATTERN = r'[\d]+[.,]?[\d]*'
    
    # Entry pattern
    ENTRY_PATTERNS = [
        r'(?:Entry|Giriş|Entry\s*Zone|Giriş\s*Bölgesi)[:\s]*(' + PRICE_PATTERN + r'(?:\s*[-–]\s*' + PRICE_PATTERN + r')?)',
        r'(?:Giriş|Entry)\s*(?:1|2)?[:\s]*(' + PRICE_PATTERN + r')',
    ]
    
    # TP pattern
    TP_PATTERNS = [
        r'(?:TP|Take\s*Profit|Hedef)\s*(?:1|2|3|4|5)?[:\s]*(' + PRICE_PATTERN + r')',
        r'(?:Target|Hedef)\s*(?:1|2|3|4|5)?[:\s]*(' + PRICE_PATTERN + r')',
    ]
    
    # SL pattern
    SL_PATTERNS = [
        r'(?:SL|Stop\s*Loss|Stop)[:\s]*(' + PRICE_PATTERN + r')',
        r'(?:Zarar\s*Durdur|Stoploss)[:\s]*(' + PRICE_PATTERN + r')',
    ]
    
    # Leverage pattern
    LEVERAGE_PATTERN = r'(?:Leverage|Kaldıraç|x)[:\s]*(\d+)'
    
    @classmethod
    def parse_signal(cls, message: str, source: str = "") -> Optional[TradingSignal]:
        """
        Telegram mesajından sinyal ayrıştır
        
        Args:
            message: Telegram mesaj metni
            source: Mesaj kaynağı (kanal adı)
            
        Returns:
            TradingSignal veya None
        """
        if not message or len(message) < 20:
            return None
        
        message_upper = message.upper()
        
        # Coin bul
        coin = None
        for pattern in cls.COIN_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                coin = match.group(1).upper()
                break
        
        if not coin:
            return None
        
        # Side bul (LONG/SHORT)
        side = None
        for pattern in cls.SIDE_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                result = match.group(1).upper()
                if result in ['LONG', 'ALIŞ', 'BUY', '🟢', '📈']:
                    side = 'LONG'
                elif result in ['SHORT', 'SATIŞ', 'SELL', '🔴', '📉']:
                    side = 'SHORT'
                break
        
        if not side:
            # Varsayılan olarak LONG
            if 'LONG' in message_upper or 'ALIŞ' in message_upper or 'BUY' in message_upper:
                side = 'LONG'
            elif 'SHORT' in message_upper or 'SATIŞ' in message_upper or 'SELL' in message_upper:
                side = 'SHORT'
            else:
                return None
        
        # Entry fiyatları bul
        entries = []
        for pattern in cls.ENTRY_PATTERNS:
            matches = re.findall(pattern, message, re.IGNORECASE)
            for match in matches:
                # Range kontrolü (örn: 0.5 - 0.6)
                if '-' in match or '–' in match:
                    parts = re.split(r'[-–]', match)
                    for part in parts:
                        price = cls._parse_price(part.strip())
                        if price:
                            entries.append(price)
                else:
                    price = cls._parse_price(match)
                    if price:
                        entries.append(price)
        
        # Entry bulunamadıysa, tüm fiyatları kontrol et
        if not entries:
            all_prices = re.findall(cls.PRICE_PATTERN, message)
            if all_prices:
                entries = [cls._parse_price(all_prices[0])]
        
        if not entries:
            return None
        
        # TP fiyatları bul
        take_profits = []
        for pattern in cls.TP_PATTERNS:
            matches = re.findall(pattern, message, re.IGNORECASE)
            for match in matches:
                price = cls._parse_price(match)
                if price:
                    take_profits.append(price)
        
        # Sırala (LONG için artan, SHORT için azalan)
        if take_profits:
            take_profits = sorted(take_profits, reverse=(side == 'SHORT'))
        
        # SL bul
        stop_loss = None
        for pattern in cls.SL_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                stop_loss = cls._parse_price(match.group(1))
                break
        
        # Leverage bul
        leverage = config.LEVERAGE  # Varsayılan
        lev_match = re.search(cls.LEVERAGE_PATTERN, message, re.IGNORECASE)
        if lev_match:
            leverage = int(lev_match.group(1))
        
        # Güven skoru hesapla
        confidence = cls._calculate_confidence(coin, side, entries, take_profits, stop_loss)
        
        return TradingSignal(
            coin=coin,
            side=side,
            entries=entries,
            take_profits=take_profits,
            stop_loss=stop_loss,
            leverage=leverage,
            source=source,
            timestamp=datetime.now(),
            raw_message=message,
            confidence=confidence
        )
    
    @staticmethod
    def _parse_price(price_str: str) -> Optional[float]:
        """Fiyat stringini float'a çevir"""
        try:
            # Virgülü noktaya çevir
            price_str = price_str.replace(',', '.').strip()
            return float(price_str)
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def _calculate_confidence(coin: str, side: str, entries: List[float],
                              take_profits: List[float], stop_loss: float) -> float:
        """Sinyal güven skorunu hesapla"""
        score = 0.0
        
        # Temel bilgiler mevcut
        if coin:
            score += 0.2
        if side:
            score += 0.2
        if entries:
            score += 0.2
        
        # TP varsa bonus
        if take_profits:
            score += 0.1 * min(len(take_profits), 3)
        
        # SL varsa bonus
        if stop_loss:
            score += 0.2
        
        return min(score, 1.0)


class TelegramSignalReader:
    """Telegram'dan sinyal okuyucu"""
    
    def __init__(self):
        self.api_id = config.TELEGRAM_API_ID
        self.api_hash = config.TELEGRAM_API_HASH
        self.phone = config.TELEGRAM_PHONE
        self.channels = config.TELEGRAM_CHANNELS
        self.client = None
        self.signals: List[TradingSignal] = []
        self.parser = SignalParser()
    
    async def connect(self):
        """Telegram'a bağlan"""
        if not self.api_id or not self.api_hash:
            logger.warning("Telegram API bilgileri eksik!")
            return False
        
        try:
            self.client = TelegramClient('kripto_bot_session', 
                                         int(self.api_id), 
                                         self.api_hash)
            await self.client.start(phone=self.phone)
            logger.info("Telegram bağlantısı başarılı!")
            return True
        except Exception as e:
            logger.error(f"Telegram bağlantı hatası: {e}")
            return False
    
    async def disconnect(self):
        """Telegram bağlantısını kapat"""
        if self.client:
            await self.client.disconnect()
    
    async def get_channel_messages(self, channel_username: str, 
                                   limit: int = 50,
                                   hours_back: int = 24) -> List[Message]:
        """Kanal mesajlarını al"""
        if not self.client:
            return []
        
        try:
            entity = await self.client.get_entity(channel_username)
            
            # Son X saat içindeki mesajlar
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            messages = []
            async for message in self.client.iter_messages(entity, limit=limit):
                if message.date.replace(tzinfo=None) > cutoff_time:
                    messages.append(message)
            
            return messages
        except Exception as e:
            logger.error(f"Kanal mesajları alınamadı ({channel_username}): {e}")
            return []
    
    async def scan_channels(self, hours_back: int = 1) -> List[TradingSignal]:
        """
        Tüm kanalları tara ve sinyalleri topla
        
        Args:
            hours_back: Kaç saat geriye bakılacak
            
        Returns:
            Bulunan sinyaller listesi
        """
        all_signals = []
        
        for channel in self.channels:
            logger.info(f"Kanal taranıyor: {channel}")
            messages = await self.get_channel_messages(
                channel, 
                limit=100, 
                hours_back=hours_back
            )
            
            for msg in messages:
                if msg.text:
                    signal = SignalParser.parse_signal(msg.text, source=channel)
                    if signal and signal.confidence >= 0.5:
                        all_signals.append(signal)
                        logger.info(f"Sinyal bulundu: {signal.coin} {signal.side} (Güven: {signal.confidence})")
        
        # Güven skoruna göre sırala
        all_signals.sort(key=lambda x: x.confidence, reverse=True)
        self.signals = all_signals
        
        return all_signals
    
    def register_handler(self, callback):
        """Yeni mesaj handler'ı kaydet"""
        if not self.client:
            return
        
        @self.client.on(events.NewMessage(chats=self.channels))
        async def handler(event):
            if event.message.text:
                signal = SignalParser.parse_signal(
                    event.message.text,
                    source=getattr(event.chat, 'username', 'unknown')
                )
                if signal and signal.confidence >= 0.5:
                    await callback(signal)
    
    async def run_listener(self, callback):
        """Sürekli dinleyici başlat"""
        self.register_handler(callback)
        logger.info("Telegram dinleyici başlatıldı...")
        await self.client.run_until_disconnected()


# Manuel sinyal girişi (Telegram bağlantısı yokken)
class ManualSignalInput:
    """Manuel sinyal girişi için yardımcı sınıf"""
    
    @staticmethod
    def create_signal(coin: str, side: str, entries: List[float],
                      take_profits: List[float], stop_loss: float,
                      leverage: int = 20) -> TradingSignal:
        """Manuel sinyal oluştur"""
        return TradingSignal(
            coin=coin.upper(),
            side=side.upper(),
            entries=entries,
            take_profits=take_profits,
            stop_loss=stop_loss,
            leverage=leverage,
            source='manual',
            timestamp=datetime.now(),
            confidence=1.0
        )
    
    @staticmethod
    def parse_quick_signal(text: str) -> Optional[TradingSignal]:
        """
        Hızlı sinyal formatı:
        COIN SIDE ENTRY TP1 TP2 TP3 SL
        Örnek: BTC LONG 42000 43000 44000 45000 41000
        """
        parts = text.strip().split()
        if len(parts) < 5:
            return None
        
        coin = parts[0].upper()
        side = parts[1].upper()
        
        try:
            entry = float(parts[2])
            stop_loss = float(parts[-1])
            take_profits = [float(p) for p in parts[3:-1]]
            
            return TradingSignal(
                coin=coin,
                side=side,
                entries=[entry],
                take_profits=take_profits,
                stop_loss=stop_loss,
                leverage=config.LEVERAGE,
                source='quick_input',
                timestamp=datetime.now(),
                confidence=1.0
            )
        except ValueError:
            return None


# Test
async def test_signal_parser():
    """Sinyal ayrıştırıcıyı test et"""
    test_messages = [
        """
        🔥 #BTCUSDT LONG
        
        Entry: 42000 - 42500
        
        TP1: 43000
        TP2: 44000
        TP3: 45000
        TP4: 46000
        TP5: 48000
        
        SL: 40500
        
        Leverage: 20x
        """,
        """
        💰 ETH/USDT SHORT
        
        Giriş: 2250
        
        Hedef 1: 2200
        Hedef 2: 2150
        
        Stop Loss: 2300
        """,
        """
        🪙 $SOL
        LONG 📈
        
        Entry Zone: 95.5 - 98
        
        TP: 105
        TP: 110
        TP: 120
        
        SL: 90
        """
    ]
    
    print("=" * 60)
    print("Sinyal Ayrıştırma Testi")
    print("=" * 60)
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n--- Test {i} ---")
        signal = SignalParser.parse_signal(msg, "test_channel")
        if signal:
            print(f"Coin: {signal.coin}")
            print(f"Side: {signal.side}")
            print(f"Entries: {signal.entries}")
            print(f"TPs: {signal.take_profits}")
            print(f"SL: {signal.stop_loss}")
            print(f"Leverage: {signal.leverage}x")
            print(f"Güven: {signal.confidence:.0%}")
        else:
            print("Sinyal ayrıştırılamadı!")


if __name__ == "__main__":
    asyncio.run(test_signal_parser())


