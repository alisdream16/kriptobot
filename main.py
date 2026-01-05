"""
Kripto Trading Bot - Ana Program
Telegram sinyalleri + Gemini AI + LBank Futures
"""
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
import config
from lbank_api import LBankAPI, LBankTrader
from telegram_signals import TelegramSignalReader, TradingSignal, SignalParser, ManualSignalInput
from gemini_analyzer import GeminiAnalyzer, MarketAnalysis
from database import Database
from trading_strategy import TradingStrategy, TPManager


# Loglama yapılandırması
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=config.LOG_LEVEL
)
logger.add(
    config.LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG"
)


class KriptoBot:
    """Ana Trading Bot"""
    
    def __init__(self):
        logger.info("=" * 60)
        logger.info("KriptoBot başlatılıyor...")
        logger.info("=" * 60)
        
        # Bileşenler
        self.db = Database()
        self.lbank_api = LBankAPI()
        self.lbank_trader = LBankTrader()
        self.gemini = GeminiAnalyzer()
        self.strategy = TradingStrategy()
        self.tp_manager = TPManager(self.db, self.lbank_trader)
        self.telegram = TelegramSignalReader()
        
        # Scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Durum
        self.running = False
        self.daily_starting_balance = 0
        
        # İzlenecek coinler (scalper için)
        self.watch_list = [
            'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'AVAX', 'DOGE',
            'MATIC', 'DOT', 'LINK', 'UNI', 'ATOM', 'LTC', 'FIL'
        ]
    
    async def start(self):
        """Botu başlat"""
        self.running = True
        
        # Başlangıç bakiyesini kaydet
        self.daily_starting_balance = self.lbank_trader.get_available_balance()
        logger.info(f"Başlangıç bakiyesi: {self.daily_starting_balance} USDT")
        
        # Bot durumunu kaydet
        self.db.set_bot_status('started_at', datetime.now().isoformat())
        self.db.set_bot_status('starting_balance', str(self.daily_starting_balance))
        
        # Scheduler görevlerini ayarla
        self._setup_scheduler()
        
        # Telegram bağlantısı (varsa)
        telegram_connected = await self._setup_telegram()
        
        # Scheduler'ı başlat
        self.scheduler.start()
        
        logger.info("=" * 60)
        logger.info("KriptoBot aktif!")
        logger.info(f"- Sinyal kontrolü: Her {config.SIGNAL_CHECK_INTERVAL} dakika")
        logger.info(f"- Gemini analizi: Her {config.GEMINI_ANALYSIS_INTERVAL} dakika")
        logger.info(f"- Scalper modu: Her {config.SCALPER_INTERVAL} dakika")
        logger.info(f"- Telegram: {'Bağlı' if telegram_connected else 'Bağlı değil'}")
        logger.info("=" * 60)
        
        # Ana döngü
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await self.stop()
    
    async def stop(self):
        """Botu durdur"""
        logger.info("Bot durduruluyor...")
        self.running = False
        
        # Günlük performansı kaydet
        await self._save_daily_performance()
        
        # Scheduler'ı durdur
        self.scheduler.shutdown(wait=False)
        
        # Telegram bağlantısını kapat
        await self.telegram.disconnect()
        
        # Bot durumunu güncelle
        self.db.set_bot_status('stopped_at', datetime.now().isoformat())
        
        logger.info("Bot durduruldu.")
    
    def _setup_scheduler(self):
        """Zamanlayıcı görevlerini ayarla"""
        
        # 30 dakikada bir sinyal kontrolü
        self.scheduler.add_job(
            self._check_signals_job,
            IntervalTrigger(minutes=config.SIGNAL_CHECK_INTERVAL),
            id='signal_check',
            name='Sinyal Kontrolü',
            max_instances=1
        )
        
        # 1 saatte bir Gemini analizi
        self.scheduler.add_job(
            self._gemini_analysis_job,
            IntervalTrigger(minutes=config.GEMINI_ANALYSIS_INTERVAL),
            id='gemini_analysis',
            name='Gemini Analizi',
            max_instances=1
        )
        
        # 1 saatte bir scalper modu
        self.scheduler.add_job(
            self._scalper_job,
            IntervalTrigger(minutes=config.SCALPER_INTERVAL),
            id='scalper',
            name='Scalper Modu',
            max_instances=1
        )
        
        # Her 5 dakikada açık işlemleri kontrol et
        self.scheduler.add_job(
            self._manage_trades_job,
            IntervalTrigger(minutes=5),
            id='trade_management',
            name='İşlem Yönetimi',
            max_instances=1
        )
        
        # Her gün gece yarısı günlük rapor
        self.scheduler.add_job(
            self._daily_report_job,
            CronTrigger(hour=0, minute=0),
            id='daily_report',
            name='Günlük Rapor',
            max_instances=1
        )
        
        # Her 1 dakikada sağlık kontrolü
        self.scheduler.add_job(
            self._health_check_job,
            IntervalTrigger(minutes=1),
            id='health_check',
            name='Sağlık Kontrolü',
            max_instances=1
        )
    
    async def _setup_telegram(self) -> bool:
        """Telegram bağlantısını kur"""
        if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
            logger.warning("Telegram API bilgileri eksik - sinyal dinleyici devre dışı")
            return False
        
        connected = await self.telegram.connect()
        
        if connected:
            # Yeni sinyal handler'ı kaydet
            self.telegram.register_handler(self._on_new_signal)
        
        return connected
    
    async def _on_new_signal(self, signal: TradingSignal):
        """Yeni sinyal geldiğinde çağrılır"""
        logger.info(f"🔔 Yeni sinyal: {signal.coin} {signal.side} (Kaynak: {signal.source})")
        
        # Strateji ile işle
        decision = self.strategy.process_telegram_signal(signal)
        
        if decision.should_trade:
            result = self.strategy.execute_trade(decision)
            logger.info(f"İşlem sonucu: {result}")
        else:
            logger.info(f"İşlem atlandı: {decision.reason}")
    
    async def _check_signals_job(self):
        """Sinyal kontrol görevi"""
        logger.info("📡 Sinyal kontrolü başlıyor...")
        
        try:
            # Telegram kanallarını tara
            if self.telegram.client:
                signals = await self.telegram.scan_channels(hours_back=0.5)  # Son 30 dk
                
                for signal in signals:
                    if signal.confidence >= 0.6:
                        decision = self.strategy.process_telegram_signal(signal)
                        
                        if decision.should_trade:
                            result = self.strategy.execute_trade(decision)
                            logger.info(f"Sinyal işlendi: {signal.coin} -> {result}")
                            await asyncio.sleep(2)  # Rate limit koruması
            
            logger.info("✅ Sinyal kontrolü tamamlandı")
            
        except Exception as e:
            logger.error(f"Sinyal kontrolü hatası: {e}")
    
    async def _gemini_analysis_job(self):
        """Gemini analiz görevi (saatlik)"""
        logger.info("🤖 Gemini analizi başlıyor...")
        
        try:
            for coin in self.watch_list[:5]:  # İlk 5 coin
                symbol = f"{coin}_USDT"
                
                # Fiyat verisi al
                price_data = self.lbank_api.futures_get_kline(symbol, '1h', 100)
                
                if not price_data['success']:
                    continue
                
                prices = []
                volumes = []
                
                for candle in price_data.get('data', []):
                    if isinstance(candle, list) and len(candle) >= 6:
                        prices.append(float(candle[4]))  # Close
                        volumes.append(float(candle[5]))  # Volume
                
                if len(prices) < 50:
                    continue
                
                # Gemini analizi
                analysis = self.gemini.analyze_coin(coin, prices, volumes)
                
                logger.info(f"Gemini {coin}: {analysis.recommendation} ({analysis.confidence:.0%})")
                
                # İşlem kararı
                decision = self.strategy.process_gemini_analysis(analysis)
                
                if decision.should_trade and decision.confidence >= 0.7:
                    result = self.strategy.execute_trade(decision)
                    logger.info(f"Gemini işlemi: {coin} -> {result}")
                
                await asyncio.sleep(3)  # Rate limit
            
            logger.info("✅ Gemini analizi tamamlandı")
            
        except Exception as e:
            logger.error(f"Gemini analizi hatası: {e}")
    
    async def _scalper_job(self):
        """Scalper modu görevi"""
        logger.info("⚡ Scalper modu başlıyor...")
        
        try:
            # En iyi fırsatları ara
            opportunities = []
            
            for coin in self.watch_list[:10]:
                symbol = f"{coin}_USDT"
                
                # Kısa vadeli fiyat verisi
                price_data = self.lbank_api.futures_get_kline(symbol, '5m', 100)
                
                if not price_data['success']:
                    continue
                
                prices = []
                volumes = []
                
                for candle in price_data.get('data', []):
                    if isinstance(candle, list) and len(candle) >= 6:
                        prices.append(float(candle[4]))
                        volumes.append(float(candle[5]))
                
                if len(prices) < 30:
                    continue
                
                # Scalper analizi
                analysis = self.gemini.scalper_analysis(coin, prices, volumes)
                
                if analysis.recommendation != 'HOLD' and analysis.confidence >= 0.7:
                    opportunities.append({
                        'coin': coin,
                        'analysis': analysis
                    })
                
                await asyncio.sleep(2)
            
            # En iyi fırsatı işle
            if opportunities:
                # Güvene göre sırala
                opportunities.sort(key=lambda x: x['analysis'].confidence, reverse=True)
                best = opportunities[0]
                
                logger.info(f"Scalp fırsatı: {best['coin']} ({best['analysis'].confidence:.0%})")
                
                decision = self.strategy.process_gemini_analysis(best['analysis'])
                
                if decision.should_trade:
                    result = self.strategy.execute_trade(decision)
                    logger.info(f"Scalp işlemi: {result}")
            else:
                logger.info("Scalp fırsatı bulunamadı")
            
            logger.info("✅ Scalper modu tamamlandı")
            
        except Exception as e:
            logger.error(f"Scalper hatası: {e}")
    
    async def _manage_trades_job(self):
        """Açık işlemleri yönet"""
        try:
            open_trades = self.db.get_open_trades()
            
            if not open_trades:
                return
            
            logger.debug(f"Açık işlem sayısı: {len(open_trades)}")
            
            for trade in open_trades:
                symbol = f"{trade['coin']}_USDT"
                
                # Güncel fiyat al
                price_result = self.lbank_api.futures_get_market_price(symbol)
                
                if not price_result['success']:
                    continue
                
                current_price = float(price_result.get('data', {}).get('price', 0))
                
                if current_price == 0:
                    continue
                
                # TP kontrolü
                tp_result = self.tp_manager.check_and_execute_tp(trade, current_price)
                
                if tp_result:
                    logger.info(f"TP{tp_result['tp_level']}: {trade['coin']} @ {current_price}")
            
            # Genel işlem yönetimi
            self.strategy.manage_open_trades()
            
        except Exception as e:
            logger.error(f"İşlem yönetimi hatası: {e}")
    
    async def _daily_report_job(self):
        """Günlük rapor oluştur"""
        logger.info("📊 Günlük rapor hazırlanıyor...")
        
        try:
            # Güncel bakiye
            current_balance = self.lbank_trader.get_available_balance()
            
            # Performans hesapla
            pnl = current_balance - self.daily_starting_balance
            pnl_pct = (pnl / self.daily_starting_balance * 100) if self.daily_starting_balance > 0 else 0
            
            # İstatistikler
            stats = self.db.get_trade_statistics(days=1)
            
            # Kaydet
            self.db.save_daily_performance(datetime.now().date(), {
                'starting_balance': self.daily_starting_balance,
                'ending_balance': current_balance,
                'total_pnl': pnl,
                'pnl_percentage': pnl_pct,
                'total_trades': stats.get('total_trades', 0),
                'winning_trades': stats.get('winning_trades', 0),
                'losing_trades': stats.get('losing_trades', 0),
                'win_rate': stats.get('win_rate', 0),
                'best_trade_pnl': stats.get('best_trade'),
                'worst_trade_pnl': stats.get('worst_trade')
            })
            
            # Rapor logla
            logger.info("=" * 60)
            logger.info("📊 GÜNLÜK RAPOR")
            logger.info("=" * 60)
            logger.info(f"Başlangıç Bakiye: {self.daily_starting_balance:.2f} USDT")
            logger.info(f"Bitiş Bakiye: {current_balance:.2f} USDT")
            logger.info(f"PNL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)")
            logger.info(f"Toplam İşlem: {stats.get('total_trades', 0)}")
            logger.info(f"Kazanan: {stats.get('winning_trades', 0)} | Kaybeden: {stats.get('losing_trades', 0)}")
            logger.info(f"Win Rate: {stats.get('win_rate', 0):.1f}%")
            logger.info("=" * 60)
            
            # Yeni gün için başlangıç bakiyesini güncelle
            self.daily_starting_balance = current_balance
            
        except Exception as e:
            logger.error(f"Günlük rapor hatası: {e}")
    
    async def _health_check_job(self):
        """Sağlık kontrolü"""
        try:
            # API bağlantısı kontrol
            ticker = self.lbank_api.get_ticker('btc_usdt')
            
            if ticker['success']:
                self.db.set_bot_status('last_health_check', datetime.now().isoformat())
                self.db.set_bot_status('api_status', 'OK')
            else:
                self.db.set_bot_status('api_status', 'ERROR')
                logger.warning("LBank API bağlantı sorunu!")
                
        except Exception as e:
            logger.error(f"Sağlık kontrolü hatası: {e}")
    
    async def _save_daily_performance(self):
        """Günlük performansı kaydet"""
        try:
            current_balance = self.lbank_trader.get_available_balance()
            pnl = current_balance - self.daily_starting_balance
            pnl_pct = (pnl / self.daily_starting_balance * 100) if self.daily_starting_balance > 0 else 0
            
            self.db.save_daily_performance(datetime.now().date(), {
                'starting_balance': self.daily_starting_balance,
                'ending_balance': current_balance,
                'total_pnl': pnl,
                'pnl_percentage': pnl_pct
            })
        except Exception as e:
            logger.error(f"Performans kaydetme hatası: {e}")
    
    # Manuel işlem metodları
    def manual_signal(self, coin: str, side: str, entry: float, 
                     take_profits: List[float], stop_loss: float):
        """Manuel sinyal girişi"""
        signal = ManualSignalInput.create_signal(
            coin=coin,
            side=side,
            entries=[entry],
            take_profits=take_profits,
            stop_loss=stop_loss
        )
        
        decision = self.strategy.process_telegram_signal(signal)
        
        if decision.should_trade:
            return self.strategy.execute_trade(decision)
        
        return {'success': False, 'reason': decision.reason}
    
    def get_status(self) -> dict:
        """Bot durumunu al"""
        balance = self.lbank_trader.get_available_balance()
        open_trades = self.db.get_open_trades()
        daily_perf = self.db.get_daily_performance()
        
        return {
            'running': self.running,
            'balance': balance,
            'starting_balance': self.daily_starting_balance,
            'current_pnl': balance - self.daily_starting_balance,
            'open_trades': len(open_trades),
            'daily_pnl_pct': daily_perf.get('pnl_percentage', 0) if daily_perf else 0,
            'last_health_check': self.db.get_bot_status('last_health_check')
        }


async def main():
    """Ana fonksiyon"""
    bot = KriptoBot()
    
    # Graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Kapatma sinyali alındı...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await bot.start()


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                     KRİPTO TRADİNG BOT                    ║
    ║                                                           ║
    ║  🔹 LBank Futures Trading                                 ║
    ║  🔹 Telegram Sinyal Takibi                                ║
    ║  🔹 Gemini AI Analiz                                      ║
    ║  🔹 Otomatik Risk Yönetimi                                ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())


