"""
KriptoBot - Ana Çalıştırıcı
Auto Trader + Position Manager + Telegram Signals birlikte çalışır
"""
import threading
import asyncio
import time
from loguru import logger

logger.add("kriptobot.log", rotation="1 day", retention="7 days")


def run_auto_trader():
    """Auto trader'ı çalıştır"""
    from auto_trader import AutoTrader
    trader = AutoTrader()
    trader.start()


def run_position_manager():
    """Position manager'ı çalıştır"""
    from position_manager import PositionManager
    manager = PositionManager()
    manager.run(interval_seconds=10)


def run_telegram_signals():
    """Telegram sinyal okuyucuyu çalıştır"""
    try:
        from telegram_signals import TelegramSignalReader
        import asyncio
        
        async def start_reader():
            reader = TelegramSignalReader()
            await reader.start()
        
        # Yeni event loop oluştur ve çalıştır
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_reader())
    except Exception as e:
        logger.error(f"❌ Telegram sinyal okuyucu hatası: {e}")


def main():
    logger.info("""
╔══════════════════════════════════════════════════════════════╗
║                    🚀 KRİPTOBOT v2.0                        ║
║                                                              ║
║  📊 Gemini AI ile Her Saat Analiz                           ║
║  📡 Telegram Kanallarından Sinyal Okuma                     ║
║  📈 Otomatik LONG/SHORT İşlem Açma                          ║
║  🎯 Trailing Stop (%20 adımlarla)                           ║
║  🛡️ %20 Kârda SL Entry'ye Çekilir                           ║
║  🔒 Her %20 Artışta SL Yukarı Taşınır                       ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Thread'leri başlat
    logger.info("🔄 Servisler başlatılıyor...")
    
    # Position Manager - sürekli pozisyon takibi
    pm_thread = threading.Thread(target=run_position_manager, daemon=True)
    pm_thread.start()
    logger.info("✅ Position Manager başlatıldı (her 10 saniye)")
    
    # Auto Trader - saatlik analiz
    at_thread = threading.Thread(target=run_auto_trader, daemon=True)
    at_thread.start()
    logger.info("✅ Auto Trader başlatıldı (her saat)")
    
    # Telegram Sinyal Okuyucu
    tg_thread = threading.Thread(target=run_telegram_signals, daemon=True)
    tg_thread.start()
    logger.info("✅ Telegram Sinyal Okuyucu başlatıldı (Silver Trade)")
    
    logger.info("\n🟢 Bot aktif! Ctrl+C ile durdurun.\n")
    
    # Ana thread'i canlı tut
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n⏹️ Bot durduruluyor...")


if __name__ == "__main__":
    main()
