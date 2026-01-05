"""
Trading Stratejisi ve Risk Yönetimi Modülü
Kasayı korurken agresif işlem stratejisi
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
import config
from lbank_api import LBankAPI, LBankTrader
from gemini_analyzer import GeminiAnalyzer, MarketAnalysis
from telegram_signals import TradingSignal
from database import Database


@dataclass
class TradeDecision:
    """İşlem kararı"""
    should_trade: bool
    action: str                    # OPEN_LONG, OPEN_SHORT, CLOSE, MODIFY, SKIP
    symbol: str
    volume: float
    leverage: int
    entry_price: Optional[float]
    take_profits: List[float]
    stop_loss: Optional[float]
    reason: str
    confidence: float
    risk_level: str


class RiskManager:
    """Risk Yöneticisi"""
    
    def __init__(self, db: Database):
        self.db = db
        self.max_open_trades = 5          # Aynı anda max açık işlem
        self.max_daily_loss_percent = 10  # Günlük max kayıp %10
        self.max_single_trade_risk = 2    # Tek işlem max %2
        self.min_risk_reward = 1.5        # Min risk/ödül oranı
    
    def can_open_trade(self, balance: float) -> Tuple[bool, str]:
        """
        Yeni işlem açılabilir mi kontrol et
        
        Returns:
            (açılabilir_mi, sebep)
        """
        # Açık işlem sayısı kontrolü
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= self.max_open_trades:
            return False, f"Max açık işlem sayısına ulaşıldı ({self.max_open_trades})"
        
        # Günlük kayıp kontrolü
        daily_perf = self.db.get_daily_performance()
        if daily_perf:
            pnl_pct = float(daily_perf.get('pnl_percentage', 0))
            if pnl_pct <= -self.max_daily_loss_percent:
                return False, f"Günlük max kayıp limitine ulaşıldı ({pnl_pct:.2f}%)"
        
        return True, "OK"
    
    def calculate_position_size(self, balance: float, stop_loss_percent: float = 3) -> float:
        """
        Pozisyon büyüklüğü hesapla
        Risk bazlı pozisyon boyutlandırma
        """
        risk_amount = balance * (self.max_single_trade_risk / 100)
        
        # Kaldıraçlı pozisyon için stop loss mesafesine göre hesapla
        position_size = risk_amount / (stop_loss_percent / 100)
        
        # Max pozisyon kasanın %5'i
        max_position = balance * 0.05
        
        return min(position_size, max_position)
    
    def validate_risk_reward(self, entry: float, stop_loss: float, 
                             take_profit: float, side: str) -> Tuple[bool, float]:
        """
        Risk/Ödül oranını doğrula
        
        Returns:
            (geçerli_mi, risk_reward_oranı)
        """
        if side == "LONG":
            risk = entry - stop_loss
            reward = take_profit - entry
        else:
            risk = stop_loss - entry
            reward = entry - take_profit
        
        if risk <= 0:
            return False, 0
        
        rr_ratio = reward / risk
        
        return rr_ratio >= self.min_risk_reward, rr_ratio
    
    def adjust_stop_loss_to_entry(self, entry_price: float, side: str, 
                                   current_pnl_percent: float) -> Optional[float]:
        """
        TP alındığında stop loss'u giriş fiyatına çek
        """
        if current_pnl_percent >= 2:  # En az %2 kârda
            if side == "LONG":
                return entry_price * 1.001  # Küçük buffer
            else:
                return entry_price * 0.999
        return None


class TradingStrategy:
    """Ana Trading Stratejisi"""
    
    def __init__(self):
        self.db = Database()
        self.lbank = LBankTrader()
        self.gemini = GeminiAnalyzer()
        self.risk_manager = RiskManager(self.db)
        self.leverage = config.LEVERAGE
    
    def process_telegram_signal(self, signal: TradingSignal) -> TradeDecision:
        """
        Telegram sinyalini işle ve karar ver
        """
        logger.info(f"Sinyal işleniyor: {signal.coin} {signal.side}")
        
        # Sinyali kaydet
        signal_id = self.db.save_signal({
            'coin': signal.coin,
            'side': signal.side,
            'entries': signal.entries,
            'take_profits': signal.take_profits,
            'stop_loss': signal.stop_loss,
            'leverage': signal.leverage,
            'source': signal.source,
            'confidence': signal.confidence,
            'raw_message': signal.raw_message
        })
        
        # Bakiye al
        balance = self.lbank.get_available_balance()
        
        # Risk kontrolü
        can_trade, reason = self.risk_manager.can_open_trade(balance)
        if not can_trade:
            self.db.update_signal_status(signal_id, 'REJECTED', reason)
            return TradeDecision(
                should_trade=False,
                action='SKIP',
                symbol=signal.coin,
                volume=0,
                leverage=self.leverage,
                entry_price=None,
                take_profits=[],
                stop_loss=None,
                reason=reason,
                confidence=0,
                risk_level='HIGH'
            )
        
        # Coin fiyat verisi al ve Gemini'ye doğrulat
        symbol = f"{signal.coin}_USDT"
        price_data = self.lbank.api.futures_get_kline(symbol, '1h', 100)
        
        prices = []
        if price_data['success'] and price_data.get('data'):
            for candle in price_data['data']:
                if isinstance(candle, list) and len(candle) >= 5:
                    prices.append(float(candle[4]))  # Close price
        
        # Gemini doğrulaması
        if prices and signal.entries:
            valid, reasoning, gemini_confidence = self.gemini.validate_signal(
                signal.coin, signal.side, signal.entries[0], prices
            )
            
            if not valid or gemini_confidence < 0.5:
                self.db.update_signal_status(signal_id, 'REJECTED', f"Gemini red: {reasoning}")
                return TradeDecision(
                    should_trade=False,
                    action='SKIP',
                    symbol=signal.coin,
                    volume=0,
                    leverage=self.leverage,
                    entry_price=None,
                    take_profits=[],
                    stop_loss=None,
                    reason=f"Gemini doğrulamadı: {reasoning}",
                    confidence=gemini_confidence,
                    risk_level='HIGH'
                )
        
        # Risk/Ödül kontrolü
        if signal.entries and signal.take_profits and signal.stop_loss:
            entry = signal.entries[0]
            tp = signal.take_profits[0] if signal.take_profits else entry * 1.05
            valid_rr, rr_ratio = self.risk_manager.validate_risk_reward(
                entry, signal.stop_loss, tp, signal.side
            )
            
            if not valid_rr:
                self.db.update_signal_status(signal_id, 'REJECTED', 
                                            f"Düşük R/R: {rr_ratio:.2f}")
                return TradeDecision(
                    should_trade=False,
                    action='SKIP',
                    symbol=signal.coin,
                    volume=0,
                    leverage=self.leverage,
                    entry_price=None,
                    take_profits=[],
                    stop_loss=None,
                    reason=f"Risk/Ödül oranı düşük: {rr_ratio:.2f}",
                    confidence=signal.confidence,
                    risk_level='HIGH'
                )
        
        # Pozisyon büyüklüğü hesapla
        stop_loss_pct = 3  # Varsayılan %3
        if signal.entries and signal.stop_loss:
            stop_loss_pct = abs(signal.entries[0] - signal.stop_loss) / signal.entries[0] * 100
        
        volume = self.risk_manager.calculate_position_size(balance, stop_loss_pct)
        
        # Sinyal durumunu güncelle
        self.db.update_signal_status(signal_id, 'APPROVED')
        
        action = f"OPEN_{signal.side}"
        
        return TradeDecision(
            should_trade=True,
            action=action,
            symbol=signal.coin,
            volume=volume,
            leverage=signal.leverage,
            entry_price=signal.entries[0] if signal.entries else None,
            take_profits=signal.take_profits,
            stop_loss=signal.stop_loss,
            reason=f"Sinyal onaylandı: Güven={signal.confidence:.0%}",
            confidence=signal.confidence,
            risk_level='MEDIUM' if signal.confidence > 0.7 else 'HIGH'
        )
    
    def process_gemini_analysis(self, analysis: MarketAnalysis) -> TradeDecision:
        """
        Gemini analizini işle (scalper ve saatlik analiz)
        """
        logger.info(f"Gemini analizi işleniyor: {analysis.coin} {analysis.recommendation}")
        
        # Analizi kaydet
        analysis_id = self.db.save_gemini_analysis({
            'coin': analysis.coin,
            'recommendation': analysis.recommendation,
            'confidence': analysis.confidence,
            'entry_price': analysis.entry_price,
            'take_profits': analysis.take_profits,
            'stop_loss': analysis.stop_loss,
            'leverage': analysis.leverage,
            'risk_level': analysis.risk_level,
            'reasoning': analysis.reasoning,
            'technical_summary': analysis.technical_summary,
            'analysis_type': analysis.technical_summary.get('mode', 'STANDARD')
        })
        
        # HOLD önerisiyse işlem yapma
        if analysis.recommendation == 'HOLD':
            return TradeDecision(
                should_trade=False,
                action='SKIP',
                symbol=analysis.coin,
                volume=0,
                leverage=self.leverage,
                entry_price=None,
                take_profits=[],
                stop_loss=None,
                reason="Gemini HOLD önerdi",
                confidence=analysis.confidence,
                risk_level=analysis.risk_level
            )
        
        # Düşük güven kontrolü
        if analysis.confidence < 0.6:
            return TradeDecision(
                should_trade=False,
                action='SKIP',
                symbol=analysis.coin,
                volume=0,
                leverage=self.leverage,
                entry_price=None,
                take_profits=[],
                stop_loss=None,
                reason=f"Düşük güven skoru: {analysis.confidence:.0%}",
                confidence=analysis.confidence,
                risk_level='HIGH'
            )
        
        # Risk kontrolü
        balance = self.lbank.get_available_balance()
        can_trade, reason = self.risk_manager.can_open_trade(balance)
        
        if not can_trade:
            return TradeDecision(
                should_trade=False,
                action='SKIP',
                symbol=analysis.coin,
                volume=0,
                leverage=self.leverage,
                entry_price=None,
                take_profits=[],
                stop_loss=None,
                reason=reason,
                confidence=analysis.confidence,
                risk_level='HIGH'
            )
        
        # Pozisyon büyüklüğü
        volume = self.risk_manager.calculate_position_size(balance)
        
        side = "LONG" if analysis.recommendation == "BUY" else "SHORT"
        action = f"OPEN_{side}"
        
        return TradeDecision(
            should_trade=True,
            action=action,
            symbol=analysis.coin,
            volume=volume,
            leverage=analysis.leverage,
            entry_price=analysis.entry_price,
            take_profits=analysis.take_profits,
            stop_loss=analysis.stop_loss,
            reason=f"Gemini {analysis.recommendation}: {analysis.reasoning[:100]}...",
            confidence=analysis.confidence,
            risk_level=analysis.risk_level
        )
    
    def execute_trade(self, decision: TradeDecision) -> Dict:
        """
        İşlem kararını uygula
        """
        if not decision.should_trade:
            logger.info(f"İşlem atlandı: {decision.reason}")
            return {'success': False, 'reason': decision.reason}
        
        symbol = decision.symbol
        if not symbol.endswith('_USDT'):
            symbol = f"{symbol}_USDT"
        
        logger.info(f"İşlem açılıyor: {symbol} {decision.action}")
        
        # Side belirle
        side = "LONG" if "LONG" in decision.action else "SHORT"
        
        # Birden fazla giriş için entries listesi oluştur
        entries = [decision.entry_price] if decision.entry_price else None
        
        # LBank'ta işlem aç
        result = self.lbank.open_trade(
            symbol=symbol,
            side=side,
            entries=entries,
            take_profits=decision.take_profits,
            stop_loss=decision.stop_loss
        )
        
        # Veritabanına kaydet
        if result:
            for entry_result in result.get('entries', []):
                if entry_result.get('result', {}).get('success'):
                    trade_id = self.db.save_trade({
                        'coin': decision.symbol,
                        'side': side,
                        'entry_price': entry_result.get('price') or decision.entry_price,
                        'volume': entry_result.get('volume'),
                        'leverage': decision.leverage,
                        'stop_loss': decision.stop_loss,
                        'take_profit': decision.take_profits[0] if decision.take_profits else None,
                        'lbank_order_id': entry_result.get('result', {}).get('data', {}).get('orderId'),
                        'status': 'OPEN'
                    })
                    logger.info(f"İşlem DB'ye kaydedildi: ID={trade_id}")
        
        return result
    
    def manage_open_trades(self):
        """
        Açık işlemleri yönet (TP takibi, SL güncelleme)
        """
        open_trades = self.db.get_open_trades()
        
        for trade in open_trades:
            symbol = f"{trade['coin']}_USDT"
            
            # Güncel fiyat al
            price_result = self.lbank.api.futures_get_market_price(symbol)
            if not price_result['success']:
                continue
            
            current_price = float(price_result.get('data', {}).get('price', 0))
            if current_price == 0:
                continue
            
            entry_price = float(trade['entry_price'])
            side = trade['side']
            
            # PNL hesapla
            if side == 'LONG':
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100
            
            # Trade güncelle
            self.db.update_trade(trade['id'], {
                'current_price': current_price,
                'pnl_percentage': pnl_pct
            })
            
            # TP kontrolü - kademeli TP alma
            take_profit = float(trade.get('take_profit', 0))
            if take_profit > 0:
                if side == 'LONG' and current_price >= take_profit:
                    self._process_tp(trade, current_price, pnl_pct)
                elif side == 'SHORT' and current_price <= take_profit:
                    self._process_tp(trade, current_price, pnl_pct)
            
            # Stop loss'u entry'e çek (kârda ise)
            if pnl_pct >= 2:
                new_sl = self.risk_manager.adjust_stop_loss_to_entry(
                    entry_price, side, pnl_pct
                )
                if new_sl:
                    self.lbank.move_stop_to_entry(symbol, new_sl)
                    logger.info(f"SL entry'e çekildi: {trade['coin']} @ {new_sl}")
            
            # SL kontrolü
            stop_loss = float(trade.get('stop_loss', 0))
            if stop_loss > 0:
                if side == 'LONG' and current_price <= stop_loss:
                    self._close_trade_sl(trade, current_price, pnl_pct)
                elif side == 'SHORT' and current_price >= stop_loss:
                    self._close_trade_sl(trade, current_price, pnl_pct)
    
    def _process_tp(self, trade: Dict, current_price: float, pnl_pct: float):
        """TP işle - %20 kapat"""
        symbol = f"{trade['coin']}_USDT"
        
        # %20 kapat
        result = self.lbank.close_partial(symbol, percentage=20)
        
        if result.get('success'):
            # TP kaydı
            volume = float(trade.get('volume', 0))
            closed_volume = volume * 0.2
            pnl = closed_volume * (pnl_pct / 100)
            
            self.db.save_tp_record(
                trade_id=trade['id'],
                tp_level=1,
                price=current_price,
                volume_closed=closed_volume,
                percentage=20,
                pnl=pnl
            )
            
            logger.info(f"TP alındı: {trade['coin']} %20, PNL={pnl:.2f} USDT")
    
    def _close_trade_sl(self, trade: Dict, current_price: float, pnl_pct: float):
        """SL ile işlem kapat"""
        symbol = f"{trade['coin']}_USDT"
        
        result = self.lbank.api.futures_close_position(symbol)
        
        volume = float(trade.get('volume', 0))
        pnl = volume * (pnl_pct / 100)
        
        self.db.close_trade(
            trade_id=trade['id'],
            pnl=pnl,
            pnl_percentage=pnl_pct,
            reason='STOP_LOSS'
        )
        
        logger.warning(f"SL tetiklendi: {trade['coin']}, PNL={pnl:.2f} USDT ({pnl_pct:.2f}%)")


class TPManager:
    """Take Profit Yöneticisi - Kademeli TP Stratejisi"""
    
    def __init__(self, db: Database, lbank: LBankTrader):
        self.db = db
        self.lbank = lbank
        self.tp_percentages = config.TP_PERCENTAGES  # [20, 20, 20, 20, 20]
    
    def calculate_tp_levels(self, entry: float, side: str, 
                           target_profits: List[float] = None) -> List[Dict]:
        """
        TP seviyelerini hesapla
        
        Args:
            entry: Giriş fiyatı
            side: LONG veya SHORT
            target_profits: Hedef TP fiyatları (opsiyonel)
        
        Returns:
            [{'level': 1, 'price': 100, 'percentage': 20}, ...]
        """
        if target_profits:
            return [
                {'level': i + 1, 'price': tp, 'percentage': self.tp_percentages[i]}
                for i, tp in enumerate(target_profits[:5])
            ]
        
        # Varsayılan TP seviyeleri (girişten %2, %4, %6, %8, %10)
        multipliers = [1.02, 1.04, 1.06, 1.08, 1.10] if side == "LONG" else \
                      [0.98, 0.96, 0.94, 0.92, 0.90]
        
        return [
            {
                'level': i + 1,
                'price': entry * mult,
                'percentage': self.tp_percentages[i]
            }
            for i, mult in enumerate(multipliers)
        ]
    
    def check_and_execute_tp(self, trade: Dict, current_price: float) -> Optional[Dict]:
        """
        TP koşulunu kontrol et ve uygula
        """
        entry = float(trade['entry_price'])
        side = trade['side']
        symbol = f"{trade['coin']}_USDT"
        
        # Alınan TP'leri kontrol et
        executed_tps = self._get_executed_tps(trade['id'])
        next_tp_level = len(executed_tps) + 1
        
        if next_tp_level > 5:
            return None  # Tüm TP'ler alınmış
        
        # TP seviyelerini al
        tp_levels = self.calculate_tp_levels(entry, side)
        current_tp = tp_levels[next_tp_level - 1]
        
        # TP koşulu kontrolü
        tp_hit = False
        if side == "LONG" and current_price >= current_tp['price']:
            tp_hit = True
        elif side == "SHORT" and current_price <= current_tp['price']:
            tp_hit = True
        
        if not tp_hit:
            return None
        
        # TP uygula
        result = self.lbank.close_partial(symbol, percentage=current_tp['percentage'])
        
        if result.get('success'):
            volume = float(trade.get('volume', 0))
            remaining_volume = volume * (1 - sum([tp['percentage'] for tp in executed_tps]) / 100)
            closed_volume = remaining_volume * (current_tp['percentage'] / 100)
            
            pnl_pct = abs(current_price - entry) / entry * 100
            pnl = closed_volume * pnl_pct / 100
            
            self.db.save_tp_record(
                trade_id=trade['id'],
                tp_level=next_tp_level,
                price=current_price,
                volume_closed=closed_volume,
                percentage=current_tp['percentage'],
                pnl=pnl
            )
            
            logger.info(f"TP{next_tp_level} alındı: {trade['coin']} @ {current_price}, PNL={pnl:.4f}")
            
            # İlk TP'den sonra SL'yi entry'e çek
            if next_tp_level == 1:
                self.lbank.move_stop_to_entry(symbol, entry)
            
            return {
                'tp_level': next_tp_level,
                'price': current_price,
                'volume_closed': closed_volume,
                'pnl': pnl
            }
        
        return None
    
    def _get_executed_tps(self, trade_id: int) -> List[Dict]:
        """Alınan TP'leri al"""
        # DB'den çek
        sql = "SELECT * FROM tp_records WHERE trade_id = %s ORDER BY tp_level"
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (trade_id,))
                    return [dict(row) for row in cur.fetchall()]
        except:
            return []


# Test
def test_strategy():
    """Strateji testleri"""
    print("=" * 60)
    print("Trading Stratejisi Testi")
    print("=" * 60)
    
    strategy = TradingStrategy()
    
    # Test sinyal
    test_signal = TradingSignal(
        coin="BTC",
        side="LONG",
        entries=[42000, 41500],
        take_profits=[43000, 44000, 45000, 46000, 48000],
        stop_loss=40500,
        leverage=20,
        source="test",
        timestamp=datetime.now(),
        confidence=0.85
    )
    
    print("\n1. Sinyal İşleme Testi:")
    decision = strategy.process_telegram_signal(test_signal)
    print(f"   İşlem yapılsın mı: {decision.should_trade}")
    print(f"   Aksiyon: {decision.action}")
    print(f"   Sebep: {decision.reason}")
    print(f"   Güven: {decision.confidence:.0%}")
    
    print("\n" + "=" * 60)
    print("Strateji testi tamamlandı!")
    print("=" * 60)


if __name__ == "__main__":
    test_strategy()


