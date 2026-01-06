"""
Position Manager - Trailing Stop Sistemi
%20 kârda SL entry'ye, her %20 artışta SL yukarı taşınır
"""
import time
from datetime import datetime
from loguru import logger
from bybit_api import BybitAPI, BybitTrader
import config

logger.add("position_manager.log", rotation="1 day", retention="7 days")


class PositionManager:
    """Pozisyon yönetimi - Trailing Stop"""
    
    def __init__(self):
        self.api = BybitAPI()
        self.trader = BybitTrader()
        self.trailing_step = 20  # Her %20'de SL güncelle
        self.positions_state = {}  # Pozisyon durumları
    
    def get_position_key(self, pos):
        """Pozisyon için unique key"""
        return f"{pos['symbol']}_{pos['side']}"
    
    def initialize_position_state(self, pos):
        """Yeni pozisyon için state oluştur"""
        key = self.get_position_key(pos)
        if key not in self.positions_state:
            entry_price = float(pos.get('avgPrice') or pos.get('entry_price', 0))
            self.positions_state[key] = {
                'symbol': pos['symbol'],
                'side': pos['side'],
                'entry_price': entry_price,
                'original_size': float(pos['size']),
                'current_sl_level': 0,  # Mevcut SL seviyesi (0, 20, 40, 60...)
                'highest_pnl_percent': 0,  # En yüksek PnL
                'created_at': datetime.now()
            }
            logger.info(f"📌 Yeni pozisyon takibe alındı: {pos['symbol']} {pos['side']} @ {entry_price}")
        return self.positions_state[key]
    
    def calculate_pnl_percent(self, entry_price: float, current_price: float, side: str) -> float:
        """PnL yüzdesini hesapla"""
        if entry_price == 0:
            return 0
        
        if side == 'Buy':  # Long
            return ((current_price - entry_price) / entry_price) * 100
        else:  # Short
            return ((entry_price - current_price) / entry_price) * 100
    
    def calculate_sl_price(self, entry_price: float, sl_level: float, side: str) -> float:
        """SL fiyatını hesapla"""
        if side == 'Buy':  # Long
            # SL seviyesi 0 ise entry, 20 ise %20 kârda, vs.
            return entry_price * (1 + sl_level / 100)
        else:  # Short
            return entry_price * (1 - sl_level / 100)
    
    def update_stop_loss(self, symbol: str, new_sl_price: float) -> bool:
        """Stop loss güncelle"""
        try:
            result = self.api.set_trading_stop(
                symbol=symbol,
                stop_loss=str(round(new_sl_price, 4))
            )
            return result.get('success', False)
        except Exception as e:
            logger.error(f"❌ SL güncelleme hatası: {e}")
            return False
    
    def check_positions(self):
        """Tüm pozisyonları kontrol et ve trailing stop uygula"""
        try:
            positions = self.trader.get_all_positions()
            
            if not positions:
                return
            
            for pos in positions:
                symbol = pos['symbol']
                side = pos['side']
                current_price = float(pos.get('markPrice') or pos.get('mark_price', 0))
                size = float(pos['size'])
                
                if size == 0 or current_price == 0:
                    continue
                
                # State'i al veya oluştur
                state = self.initialize_position_state(pos)
                entry_price = state['entry_price']
                
                if entry_price == 0:
                    continue
                
                # PnL hesapla
                pnl_percent = self.calculate_pnl_percent(entry_price, current_price, side)
                
                # En yüksek PnL'i güncelle
                if pnl_percent > state['highest_pnl_percent']:
                    state['highest_pnl_percent'] = pnl_percent
                
                # Hangi SL seviyesinde olmalı? (0, 20, 40, 60...)
                target_sl_level = (int(pnl_percent // self.trailing_step)) * self.trailing_step
                
                # Minimum 0 (entry) - negatif olamaz
                target_sl_level = max(0, target_sl_level)
                
                # SL seviyesi yükselmeli mi?
                if target_sl_level > state['current_sl_level'] and pnl_percent >= self.trailing_step:
                    old_sl_level = state['current_sl_level']
                    new_sl_level = target_sl_level
                    
                    # Yeni SL fiyatını hesapla
                    new_sl_price = self.calculate_sl_price(entry_price, new_sl_level, side)
                    
                    # Eğer %20'ye ulaştıysa ve SL henüz entry'de değilse
                    if old_sl_level == 0 and new_sl_level >= self.trailing_step:
                        # İlk olarak SL'yi entry'ye çek
                        sl_entry = self.calculate_sl_price(entry_price, 0, side)
                        logger.info(f"""
🔒 {symbol} - SL ENTRY'YE ÇEKİLDİ!
   PnL: {pnl_percent:.2f}%
   Entry: ${entry_price:.4f}
   SL: ${sl_entry:.4f} (başabaş)
""")
                        self.update_stop_loss(symbol, sl_entry)
                        state['current_sl_level'] = 0
                        time.sleep(1)
                    
                    # Şimdi gerçek SL seviyesini ayarla
                    if new_sl_level > 0:
                        logger.info(f"""
📈 {symbol} - SL YÜKSELTİLDİ!
   PnL: {pnl_percent:.2f}%
   Entry: ${entry_price:.4f}
   Eski SL Seviyesi: %{old_sl_level}
   Yeni SL Seviyesi: %{new_sl_level}
   Yeni SL Fiyat: ${new_sl_price:.4f}
""")
                        if self.update_stop_loss(symbol, new_sl_price):
                            state['current_sl_level'] = new_sl_level
                            logger.success(f"✅ {symbol} SL güncellendi: ${new_sl_price:.4f} (+%{new_sl_level})")
                        else:
                            logger.error(f"❌ {symbol} SL güncellenemedi")
                
                # Durumu logla (her 60 saniyede bir)
                if hasattr(self, '_last_log') and symbol in self._last_log:
                    if time.time() - self._last_log[symbol] < 60:
                        continue
                
                if not hasattr(self, '_last_log'):
                    self._last_log = {}
                self._last_log[symbol] = time.time()
                
                logger.info(f"📊 {symbol} | {side} | PnL: {pnl_percent:+.2f}% | SL Level: %{state['current_sl_level']}")
                
        except Exception as e:
            logger.error(f"❌ Position check hatası: {e}")
    
    def run(self, interval_seconds: int = 10):
        """Position manager'ı başlat"""
        logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║          📊 TRAILING STOP YÖNETİCİSİ BAŞLADI                ║
║                                                              ║
║  🎯 %20 kârda → SL entry'ye (başabaş)                       ║
║  📈 Her %20 artışta → SL yukarı taşınır                     ║
║                                                              ║
║  Örnek (LONG):                                               ║
║  • %20 kâr → SL = Entry (0%)                                ║
║  • %40 kâr → SL = %20 kâr                                   ║
║  • %60 kâr → SL = %40 kâr                                   ║
║  • %80 kâr → SL = %60 kâr                                   ║
╚══════════════════════════════════════════════════════════════╝
""")
        
        logger.info(f"⏱️ Kontrol aralığı: {interval_seconds} saniye")
        
        while True:
            try:
                self.check_positions()
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("⏹️ Position manager durduruldu")
                break
            except Exception as e:
                logger.error(f"❌ Hata: {e}")
                time.sleep(30)


def main():
    manager = PositionManager()
    manager.run(interval_seconds=10)  # Her 10 saniyede kontrol


if __name__ == "__main__":
    main()
