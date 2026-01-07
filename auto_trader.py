"""
KriptoBot - Otomatik Trading Sistemi
Gemini AI ile analiz, Bybit API ile işlem
"""
import time
import json
import schedule
import requests
import google.generativeai as genai
from datetime import datetime
from loguru import logger
from bybit_api import BybitAPI, BybitTrader
import config
import os

# Gemini AI kurulumu
genai.configure(api_key=config.GEMINI_API_KEY)
gemini_model = genai.GenerativeModel(config.GEMINI_MODEL)

# Logger ayarla
logger.add("auto_trader.log", rotation="1 day", retention="7 days")

class AutoTrader:
    """Gemini AI ile otomatik trading - Doğrudan Bybit API"""
    
    def __init__(self):
        self.api = BybitAPI()
        self.trader = BybitTrader()
        self.trading_pairs = config.TRADING_PAIRS[:20]  # İlk 20 parite
        self.max_open_positions = 5  # Maksimum açık pozisyon
        self.last_analysis = {}
    
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
            response = gemini_model.generate_content(prompt)
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
        """Sinyalleri Bybit'te işleme al"""
        signals = analysis.get('signals', [])
        
        if not signals:
            logger.info("📭 Sinyal yok, işlem açılmadı")
            return
        
        # Mevcut pozisyonları kontrol et
        current_positions = self.trader.get_all_positions()
        open_symbols = [p['symbol'] for p in current_positions]
        
        if len(current_positions) >= self.max_open_positions:
            logger.warning(f"⚠️ Maksimum pozisyon sayısına ulaşıldı ({self.max_open_positions})")
            return
        
        # Bakiye kontrol
        balance = self.trader.get_available_balance()
        if balance < 5:
            logger.warning(f"⚠️ Yetersiz bakiye: {balance} USDT")
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
            
            if symbol in open_symbols:
                logger.info(f"⏭️ {symbol} atlandı - zaten açık pozisyon var")
                continue
            
            # Fiyat al
            price = self.trader.get_current_price(symbol)
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
            
            # Pozisyon büyüklüğü - config'den (%4)
            position_size = balance * (config.RISK_PERCENTAGE / 100)
            
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
            
            # İşlem aç
            try:
                result = self.trader.open_trade(
                    symbol=symbol,
                    side=side,
                    usdt_amount=position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                if result.get('success'):
                    logger.success(f"✅ {symbol} {side} POZİSYON AÇILDI!")
                else:
                    logger.error(f"❌ {symbol} işlem hatası: {result.get('error')}")
                    
            except Exception as e:
                logger.error(f"❌ İşlem hatası {symbol}: {e}")
            
            # Çok hızlı işlem açmamak için bekle
            time.sleep(1)
    
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
        
        # Sinyalleri işle
        self.execute_signals(analysis)
        
        # Mevcut pozisyonları göster
        positions = self.trader.get_all_positions()
        if positions:
            logger.info(f"\n📋 AÇIK POZİSYONLAR ({len(positions)}):")
            for pos in positions:
                pnl = float(pos['unrealized_pnl'])
                pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
                logger.info(f"   {pos['symbol']} | {pos['side']} | PnL: {pnl_str} USDT")
        
        logger.info("=" * 50)
        logger.info(f"✅ ANALİZ TAMAMLANDI - Sonraki: 1 saat sonra")
        logger.info("=" * 50 + "\n")
    
    def has_open_positions(self) -> bool:
        """Açık pozisyon var mı kontrol et"""
        positions = self.trader.get_all_positions()
        return len(positions) > 0
    
    def start(self):
        """Botu başlat"""
        logger.info("""
╔══════════════════════════════════════════════════════════╗
║          🤖 KRİPTOBOT - OTOMATİK TRADER                 ║
║          Gemini AI ile Akıllı Trading                    ║
║                                                          ║
║  📭 Pozisyon yoksa: Her 15 dakikada analiz              ║
║  📊 Pozisyon varsa: Her saat analiz                     ║
╚══════════════════════════════════════════════════════════╝
""")
        
        # Bakiye kontrol
        balance = self.trader.get_available_balance()
        logger.info(f"💰 Başlangıç Bakiyesi: {balance} USDT")
        logger.info(f"📊 İzlenen Parite: {len(self.trading_pairs)}")
        
        # İlk analizi hemen yap
        logger.info("\n🚀 İlk analiz başlatılıyor...\n")
        self.run_analysis()
        
        # Her saat başı analiz
        schedule.every().hour.at(":00").do(self.run_analysis)
        
        # Son analiz zamanı
        last_analysis_time = time.time()
        had_position = False
        
        # Döngü
        logger.info("⏳ Zamanlayıcı aktif")
        while True:
            schedule.run_pending()
            
            has_position_now = self.has_open_positions()
            
            # Açık pozisyon yoksa her 15 dakikada analiz
            if not has_position_now:
                # Pozisyon yeni kapandıysa hemen analiz yap
                if had_position:
                    logger.info("\n🔄 Pozisyon kapandı - Hemen yeni analiz başlatılıyor...")
                    self.run_analysis()
                    last_analysis_time = time.time()
                # Normal 15 dakika kontrolü
                elif time.time() - last_analysis_time >= 900:
                    logger.info("\n⏰ 15 dakika geçti - Analiz başlatılıyor...")
                    self.run_analysis()
                    last_analysis_time = time.time()
            
            had_position = has_position_now
            time.sleep(60)


def main():
    trader = AutoTrader()
    trader.start()


if __name__ == "__main__":
    main()

