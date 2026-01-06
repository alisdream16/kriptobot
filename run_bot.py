"""
KriptoBot - Ana Çalıştırıcı
Auto Trader + Position Manager birlikte çalışır
"""
import threading
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


def main():
    logger.info("""
╔══════════════════════════════════════════════════════════════╗
║                    🚀 KRİPTOBOT v1.0                        ║
║                                                              ║
║  📊 Gemini AI ile Her Saat Analiz                           ║
║  📈 Otomatik LONG/SHORT İşlem Açma                          ║
║  🎯 5 Kademeli TP (%1, %2, %3, %4, %5)                      ║
║  🛡️ Her TP'de %20 Pozisyon Kapatma                          ║
║  🔒 İlk TP Sonrası SL Entry'ye Çekilir                      ║
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
    
    logger.info("\n🟢 Bot aktif! Ctrl+C ile durdurun.\n")
    
    # Ana thread'i canlı tut
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n⏹️ Bot durduruluyor...")


if __name__ == "__main__":
    main()
