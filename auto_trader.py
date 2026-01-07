"""
KriptoBot - Otomatik Trading Sistemi
Her saat Gemini AI analizi yaparak işlem açar
Sinyaller Telegram'a gönderilir → n8n tetiklenir → Bybit'te işlem açılır
"""
import time
import json
import schedule
import requests
import google.generativeai as genai
from datetime import datetime
from loguru import logger
import config
import os

# Telegram Bot Token (n8n'e mesaj göndermek için)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8513037447:AAFDrByRG2tv8FxcOf9JRDjMxDU2wzgUZXY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1218598281")  # Ali Baran'ın chat ID'si

# Gemini AI kurulumu
genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel(config.GEMINI_MODEL)

# Logger ayarla
logger.add("auto_trader.log", rotation="1 day", retention="7 days")

class AutoTrader:
    """Gemini AI ile otomatik trading - Sinyaller Telegram'a gönderilir"""
    
    def __init__(self):
        self.trading_pairs = config.TRADING_PAIRS[:20]  # İlk 20 parite
        self.max_open_positions = 5  # Maksimum açık pozisyon
        self.last_analysis = {}
        self.open_signals = []  # Açık sinyaller (n8n'e gönderilen)
    
    def send_telegram_signal(self, symbol: str, side: str, entry: float, sl: float, tp: float, confidence: int, reason: str) -> bool:
        """n8n'e sinyal gönder (Telegram üzerinden)"""
        try:
            if not TELEGRAM_CHAT_ID:
                logger.warning("⚠️ TELEGRAM_CHAT_ID ayarlanmamış!")
                return False
            
            # n8n'in anlayacağı format
            message = f"""🤖 KRIPTOBOT SİNYAL

{side} {symbol}
Entry: {entry}
SL: {sl}
TP: {tp}
Leverage: {config.LEVERAGE}
Confidence: {confidence}/10
Reason: {reason}"""
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.success(f"✅ Telegram'a sinyal gönderildi: {side} {symbol}")
                return True
            else:
                logger.error(f"❌ Telegram hatası: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Telegram gönderim hatası: {e}")
            return False
    
    def get_market_data(self, symbol: str) -> dict:
        """Piyasa verilerini al (Public API - imza gerektirmez)"""
        try:
            # Ticker (Public endpoint)
            url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get('retCode') != 0 or not data.get('result', {}).get('list'):
                return None
            
            price_data = data['result']['list'][0]
            
            # Kline (Public endpoint)
            kline_url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=24"
            kline_response = requests.get(kline_url, timeout=10)
            kline_data_raw = kline_response.json()
            
            kline_data = []
            if kline_data_raw.get('retCode') == 0:
                for k in kline_data_raw.get('result', {}).get('list', [])[:24]:
                    kline_data.append({
                        'open': k[1],
                        'high': k[2],
                        'low': k[3],
                        'close': k[4],
                        'volume': k[5]
                    })
            
            return {
                'symbol': symbol,
                'price': float(price_data['lastPrice']),
                'price_24h_change': float(price_data.get('price24hPcnt', 0)) * 100,
                'high_24h': float(price_data.get('highPrice24h', 0)),
                'low_24h': float(price_data.get('lowPrice24h', 0)),
                'volume_24h': float(price_data.get('volume24h', 0)),
                'klines': kline_data[-12:]  # Son 12 saat
            }
        except Exception as e:
            logger.error(f"Market data error {symbol}: {e}")
            return None
    
    def analyze_with_gemini(self, market_data: list) -> list:
        """Gemini AI ile analiz yap"""
        
        prompt = f"""
Sen profesyonel bir kripto trader'sın. Aşağıdaki piyasa verilerini analiz et ve işlem önerileri ver.

KURALLAR:
1. Sadece en güçlü 1-3 sinyal ver
2. Her sinyal için: sembol, yön (LONG/SHORT), güven skoru (1-10), stop loss %, take profit %
3. Güven skoru 7'nin altındaysa işlem önerme
4. Risk/ödül oranı minimum 1:2 olmalı
5. JSON formatında yanıt ver

PİYASA VERİLERİ:
{json.dumps(market_data, indent=2)}

YANIT FORMATI (sadece JSON, başka bir şey yazma):
{{
    "signals": [
        {{
            "symbol": "BTCUSDT",
            "side": "LONG",
            "confidence": 8,
            "stop_loss_percent": 2,
            "take_profit_percent": 4,
            "reason": "Kısa açıklama"
        }}
    ],
    "market_sentiment": "bullish/bearish/neutral",
    "analysis_summary": "Kısa özet"
}}
"""
        
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # JSON parse
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text)
            return result
            
        except Exception as e:
            logger.error(f"Gemini analysis error: {e}")
            return {"signals": [], "market_sentiment": "neutral", "analysis_summary": "Analiz yapılamadı"}
    
    def execute_signals(self, analysis: dict):
        """Sinyalleri Telegram'a gönder → n8n tetiklenir → Bybit'te işlem açılır"""
        signals = analysis.get('signals', [])
        
        if not signals:
            logger.info("📭 Sinyal yok, işlem açılmadı")
            return
        
        # Açık sinyal kontrolü
        if len(self.open_signals) >= self.max_open_positions:
            logger.warning(f"⚠️ Maksimum sinyal sayısına ulaşıldı ({self.max_open_positions})")
            return
        
        for signal in signals:
            symbol = signal.get('symbol')
            side = signal.get('side')
            confidence = signal.get('confidence', 0)
            sl_percent = signal.get('stop_loss_percent', 2)
            tp_percent = signal.get('take_profit_percent', 4)
            reason = signal.get('reason', '')
            
            # Filtreler
            if confidence < 7:
                logger.info(f"⏭️ {symbol} atlandı - düşük güven: {confidence}")
                continue
            
            if symbol in self.open_signals:
                logger.info(f"⏭️ {symbol} atlandı - zaten sinyal gönderildi")
                continue
            
            # Fiyat al (Public API)
            price = self.get_current_price(symbol)
            if price == 0:
                continue
            
            # SL/TP hesapla - fiyata göre decimal belirle
            if price < 1:
                decimals = 5
            elif price < 10:
                decimals = 4
            elif price < 100:
                decimals = 3
            else:
                decimals = 2
            
            if side == 'LONG':
                stop_loss = round(price * (1 - sl_percent/100), decimals)
                take_profit = round(price * (1 + tp_percent/100), decimals)
            else:
                stop_loss = round(price * (1 + sl_percent/100), decimals)
                take_profit = round(price * (1 - tp_percent/100), decimals)
            
            logger.info(f"""
🎯 SİNYAL ALINDI:
   Parite: {symbol}
   Yön: {side}
   Güven: {confidence}/10
   Fiyat: ${price}
   SL: ${stop_loss} ({sl_percent}%)
   TP: ${take_profit} ({tp_percent}%)
   Sebep: {reason}
""")
            
            # Telegram'a sinyal gönder (n8n tetiklenecek)
            success = self.send_telegram_signal(
                symbol=symbol,
                side=side,
                entry=price,
                sl=stop_loss,
                tp=take_profit,
                confidence=confidence,
                reason=reason
            )
            
            if success:
                self.open_signals.append(symbol)
                logger.success(f"✅ {symbol} {side} SİNYALİ TELEGRAM'A GÖNDERİLDİ!")
            else:
                logger.error(f"❌ {symbol} sinyal gönderilemedi")
            
            # Çok hızlı mesaj göndermemek için bekle
            time.sleep(1)
    
    def get_current_price(self, symbol: str) -> float:
        """Güncel fiyatı al (Public API)"""
        try:
            url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                return float(data['result']['list'][0]['lastPrice'])
            return 0
        except:
            return 0
    
    def run_analysis(self):
        """Ana analiz döngüsü"""
        logger.info("=" * 50)
        logger.info(f"🔍 ANALİZ BAŞLADI - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logger.info("=" * 50)
        
        # Piyasa verilerini topla
        market_data = []
        for symbol in self.trading_pairs:
            data = self.get_market_data(symbol)
            if data:
                market_data.append(data)
        
        logger.info(f"📊 {len(market_data)} parite analiz ediliyor...")
        
        # Gemini analizi
        analysis = self.analyze_with_gemini(market_data)
        
        logger.info(f"📈 Piyasa Durumu: {analysis.get('market_sentiment', 'N/A')}")
        logger.info(f"📝 Özet: {analysis.get('analysis_summary', 'N/A')}")
        logger.info(f"🎯 Sinyal Sayısı: {len(analysis.get('signals', []))}")
        
        # Sinyalleri Telegram'a gönder (n8n tetiklenecek)
        self.execute_signals(analysis)
        
        # Gönderilen sinyalleri göster
        if self.open_signals:
            logger.info(f"\n📋 GÖNDERİLEN SİNYALLER ({len(self.open_signals)}):")
            for sig in self.open_signals:
                logger.info(f"   📤 {sig}")
        
        logger.info("=" * 50)
        logger.info(f"✅ ANALİZ TAMAMLANDI - Sonraki: 1 saat sonra")
        logger.info("=" * 50 + "\n")
    
    def has_open_signals(self) -> bool:
        """Açık sinyal var mı kontrol et"""
        return len(self.open_signals) > 0
    
    def clear_signals(self):
        """Sinyalleri temizle (manuel çağrılabilir)"""
        self.open_signals = []
        logger.info("🗑️ Sinyal listesi temizlendi")
    
    def start(self):
        """Botu başlat"""
        logger.info("""
╔══════════════════════════════════════════════════════════╗
║          🤖 KRİPTOBOT - TELEGRAM → N8N → BYBIT          ║
║          Gemini AI ile Akıllı Trading                    ║
║                                                          ║
║  📤 Sinyal → Telegram → n8n → Bybit işlem               ║
║  ⏰ Her 15 dakikada analiz                               ║
╚══════════════════════════════════════════════════════════╝
""")
        
        logger.info(f"📊 İzlenen Parite: {len(self.trading_pairs)}")
        logger.info(f"📤 Telegram Chat ID: {TELEGRAM_CHAT_ID or 'AYARLANMADI!'}")
        
        if not TELEGRAM_CHAT_ID:
            logger.error("⚠️ TELEGRAM_CHAT_ID ayarlanmamış! .env dosyasına ekle.")
        
        # İlk analizi hemen yap
        logger.info("\n🚀 İlk analiz başlatılıyor...\n")
        self.run_analysis()
        
        # Her saat başı analiz
        schedule.every().hour.at(":00").do(self.run_analysis)
        
        # Son analiz zamanı
        last_analysis_time = time.time()
        
        # Döngü
        logger.info("⏳ Zamanlayıcı aktif")
        while True:
            schedule.run_pending()
            
            # Açık sinyal yoksa her 15 dakikada analiz
            if not self.has_open_signals():
                if time.time() - last_analysis_time >= 900:  # 15 dakika
                    logger.info("\n⏰ 15 dakika geçti - Analiz başlatılıyor...")
                    self.run_analysis()
                    last_analysis_time = time.time()
            
            time.sleep(60)  # Her dakika kontrol


def main():
    trader = AutoTrader()
    trader.start()


if __name__ == "__main__":
    main()

