"""
Supabase/PostgreSQL Veritabanı Modülü
İşlem geçmişi, sinyal kayıtları ve bot durumu
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from loguru import logger
import config


class Database:
    """PostgreSQL/Supabase Veritabanı Yöneticisi"""
    
    def __init__(self):
        self.connection_string = config.SUPABASE_URL
        self._init_tables()
    
    @contextmanager
    def get_connection(self):
        """Bağlantı context manager"""
        conn = None
        try:
            conn = psycopg2.connect(self.connection_string)
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Veritabanı hatası: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def _init_tables(self):
        """Tabloları oluştur"""
        create_tables_sql = """
        -- Sinyaller tablosu
        CREATE TABLE IF NOT EXISTS signals (
            id SERIAL PRIMARY KEY,
            coin VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            entries JSONB,
            take_profits JSONB,
            stop_loss DECIMAL(20, 8),
            leverage INTEGER DEFAULT 20,
            source VARCHAR(100),
            confidence DECIMAL(5, 4),
            raw_message TEXT,
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            notes TEXT
        );
        
        -- İşlemler tablosu
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            signal_id INTEGER REFERENCES signals(id),
            coin VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            entry_price DECIMAL(20, 8),
            current_price DECIMAL(20, 8),
            volume DECIMAL(20, 8),
            leverage INTEGER,
            stop_loss DECIMAL(20, 8),
            take_profit DECIMAL(20, 8),
            pnl DECIMAL(20, 8) DEFAULT 0,
            pnl_percentage DECIMAL(10, 4) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'OPEN',
            lbank_order_id VARCHAR(100),
            lbank_position_id VARCHAR(100),
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            close_reason VARCHAR(50),
            notes TEXT
        );
        
        -- TP kayıtları
        CREATE TABLE IF NOT EXISTS tp_records (
            id SERIAL PRIMARY KEY,
            trade_id INTEGER REFERENCES trades(id),
            tp_level INTEGER,
            price DECIMAL(20, 8),
            volume_closed DECIMAL(20, 8),
            percentage_closed DECIMAL(5, 2),
            pnl DECIMAL(20, 8),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Günlük performans
        CREATE TABLE IF NOT EXISTS daily_performance (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            starting_balance DECIMAL(20, 8),
            ending_balance DECIMAL(20, 8),
            total_pnl DECIMAL(20, 8),
            pnl_percentage DECIMAL(10, 4),
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            win_rate DECIMAL(5, 2),
            best_trade_pnl DECIMAL(20, 8),
            worst_trade_pnl DECIMAL(20, 8),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Gemini analizleri
        CREATE TABLE IF NOT EXISTS gemini_analyses (
            id SERIAL PRIMARY KEY,
            coin VARCHAR(20) NOT NULL,
            recommendation VARCHAR(10),
            confidence DECIMAL(5, 4),
            entry_price DECIMAL(20, 8),
            take_profits JSONB,
            stop_loss DECIMAL(20, 8),
            leverage INTEGER,
            risk_level VARCHAR(20),
            reasoning TEXT,
            technical_summary JSONB,
            analysis_type VARCHAR(20) DEFAULT 'STANDARD',
            executed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Bot durumu
        CREATE TABLE IF NOT EXISTS bot_status (
            id SERIAL PRIMARY KEY,
            key VARCHAR(50) UNIQUE NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- İndeksler
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
        CREATE INDEX IF NOT EXISTS idx_trades_coin ON trades(coin);
        CREATE INDEX IF NOT EXISTS idx_daily_perf_date ON daily_performance(date);
        CREATE INDEX IF NOT EXISTS idx_gemini_coin ON gemini_analyses(coin);
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_tables_sql)
            logger.info("Veritabanı tabloları oluşturuldu/kontrol edildi")
        except Exception as e:
            logger.error(f"Tablo oluşturma hatası: {e}")
    
    # ==================== SİNYAL İŞLEMLERİ ====================
    
    def save_signal(self, signal_data: Dict) -> int:
        """Sinyal kaydet"""
        sql = """
        INSERT INTO signals (coin, side, entries, take_profits, stop_loss, 
                            leverage, source, confidence, raw_message, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    signal_data.get('coin'),
                    signal_data.get('side'),
                    json.dumps(signal_data.get('entries', [])),
                    json.dumps(signal_data.get('take_profits', [])),
                    signal_data.get('stop_loss'),
                    signal_data.get('leverage', 20),
                    signal_data.get('source'),
                    signal_data.get('confidence'),
                    signal_data.get('raw_message'),
                    signal_data.get('status', 'PENDING')
                ))
                signal_id = cur.fetchone()[0]
                logger.info(f"Sinyal kaydedildi: ID={signal_id}")
                return signal_id
    
    def update_signal_status(self, signal_id: int, status: str, notes: str = None):
        """Sinyal durumunu güncelle"""
        sql = """
        UPDATE signals 
        SET status = %s, processed_at = CURRENT_TIMESTAMP, notes = %s
        WHERE id = %s
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (status, notes, signal_id))
    
    def get_pending_signals(self) -> List[Dict]:
        """Bekleyen sinyalleri al"""
        sql = """
        SELECT * FROM signals 
        WHERE status = 'PENDING' 
        ORDER BY created_at DESC
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]
    
    def get_recent_signals(self, hours: int = 24) -> List[Dict]:
        """Son X saatteki sinyalleri al"""
        sql = """
        SELECT * FROM signals 
        WHERE created_at > %s
        ORDER BY created_at DESC
        """
        
        cutoff = datetime.now() - timedelta(hours=hours)
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (cutoff,))
                return [dict(row) for row in cur.fetchall()]
    
    # ==================== İŞLEM (TRADE) İŞLEMLERİ ====================
    
    def save_trade(self, trade_data: Dict) -> int:
        """İşlem kaydet"""
        sql = """
        INSERT INTO trades (signal_id, coin, side, entry_price, volume, leverage,
                           stop_loss, take_profit, lbank_order_id, lbank_position_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    trade_data.get('signal_id'),
                    trade_data.get('coin'),
                    trade_data.get('side'),
                    trade_data.get('entry_price'),
                    trade_data.get('volume'),
                    trade_data.get('leverage'),
                    trade_data.get('stop_loss'),
                    trade_data.get('take_profit'),
                    trade_data.get('lbank_order_id'),
                    trade_data.get('lbank_position_id'),
                    trade_data.get('status', 'OPEN')
                ))
                trade_id = cur.fetchone()[0]
                logger.info(f"İşlem kaydedildi: ID={trade_id}")
                return trade_id
    
    def update_trade(self, trade_id: int, updates: Dict):
        """İşlem güncelle"""
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(trade_id)
        
        sql = f"""
        UPDATE trades 
        SET {', '.join(set_clauses)}
        WHERE id = %s
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
    
    def close_trade(self, trade_id: int, pnl: float, pnl_percentage: float, 
                    reason: str = "MANUAL"):
        """İşlem kapat"""
        sql = """
        UPDATE trades 
        SET status = 'CLOSED', pnl = %s, pnl_percentage = %s, 
            closed_at = CURRENT_TIMESTAMP, close_reason = %s
        WHERE id = %s
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (pnl, pnl_percentage, reason, trade_id))
        
        logger.info(f"İşlem kapatıldı: ID={trade_id}, PNL={pnl}, Reason={reason}")
    
    def get_open_trades(self) -> List[Dict]:
        """Açık işlemleri al"""
        sql = """
        SELECT * FROM trades 
        WHERE status = 'OPEN'
        ORDER BY opened_at DESC
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]
    
    def get_trade_by_coin(self, coin: str) -> Optional[Dict]:
        """Coin'e göre açık işlem bul"""
        sql = """
        SELECT * FROM trades 
        WHERE coin = %s AND status = 'OPEN'
        ORDER BY opened_at DESC
        LIMIT 1
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (coin,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    # ==================== TP KAYITLARI ====================
    
    def save_tp_record(self, trade_id: int, tp_level: int, price: float,
                       volume_closed: float, percentage: float, pnl: float):
        """TP kaydı ekle"""
        sql = """
        INSERT INTO tp_records (trade_id, tp_level, price, volume_closed, 
                               percentage_closed, pnl)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (trade_id, tp_level, price, volume_closed, 
                                 percentage, pnl))
    
    # ==================== GÜNLÜK PERFORMANS ====================
    
    def save_daily_performance(self, date: datetime.date, stats: Dict):
        """Günlük performans kaydet"""
        sql = """
        INSERT INTO daily_performance (date, starting_balance, ending_balance,
                                       total_pnl, pnl_percentage, total_trades,
                                       winning_trades, losing_trades, win_rate,
                                       best_trade_pnl, worst_trade_pnl)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
            ending_balance = EXCLUDED.ending_balance,
            total_pnl = EXCLUDED.total_pnl,
            pnl_percentage = EXCLUDED.pnl_percentage,
            total_trades = EXCLUDED.total_trades,
            winning_trades = EXCLUDED.winning_trades,
            losing_trades = EXCLUDED.losing_trades,
            win_rate = EXCLUDED.win_rate,
            best_trade_pnl = EXCLUDED.best_trade_pnl,
            worst_trade_pnl = EXCLUDED.worst_trade_pnl
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    date,
                    stats.get('starting_balance'),
                    stats.get('ending_balance'),
                    stats.get('total_pnl'),
                    stats.get('pnl_percentage'),
                    stats.get('total_trades', 0),
                    stats.get('winning_trades', 0),
                    stats.get('losing_trades', 0),
                    stats.get('win_rate'),
                    stats.get('best_trade_pnl'),
                    stats.get('worst_trade_pnl')
                ))
    
    def get_daily_performance(self, date: datetime.date = None) -> Optional[Dict]:
        """Günlük performans al"""
        if date is None:
            date = datetime.now().date()
        
        sql = "SELECT * FROM daily_performance WHERE date = %s"
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (date,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def get_weekly_performance(self) -> List[Dict]:
        """Haftalık performans al"""
        sql = """
        SELECT * FROM daily_performance 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY date DESC
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]
    
    # ==================== GEMİNİ ANALİZLERİ ====================
    
    def save_gemini_analysis(self, analysis_data: Dict) -> int:
        """Gemini analizi kaydet"""
        sql = """
        INSERT INTO gemini_analyses (coin, recommendation, confidence, entry_price,
                                     take_profits, stop_loss, leverage, risk_level,
                                     reasoning, technical_summary, analysis_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    analysis_data.get('coin'),
                    analysis_data.get('recommendation'),
                    analysis_data.get('confidence'),
                    analysis_data.get('entry_price'),
                    json.dumps(analysis_data.get('take_profits', [])),
                    analysis_data.get('stop_loss'),
                    analysis_data.get('leverage'),
                    analysis_data.get('risk_level'),
                    analysis_data.get('reasoning'),
                    json.dumps(analysis_data.get('technical_summary', {})),
                    analysis_data.get('analysis_type', 'STANDARD')
                ))
                return cur.fetchone()[0]
    
    def get_recent_analyses(self, coin: str = None, hours: int = 24) -> List[Dict]:
        """Son analizleri al"""
        sql = """
        SELECT * FROM gemini_analyses 
        WHERE created_at > %s
        """
        params = [datetime.now() - timedelta(hours=hours)]
        
        if coin:
            sql += " AND coin = %s"
            params.append(coin)
        
        sql += " ORDER BY created_at DESC"
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
    
    # ==================== BOT DURUMU ====================
    
    def set_bot_status(self, key: str, value: str):
        """Bot durumu kaydet"""
        sql = """
        INSERT INTO bot_status (key, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = CURRENT_TIMESTAMP
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (key, value))
    
    def get_bot_status(self, key: str) -> Optional[str]:
        """Bot durumu al"""
        sql = "SELECT value FROM bot_status WHERE key = %s"
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (key,))
                row = cur.fetchone()
                return row[0] if row else None
    
    # ==================== İSTATİSTİKLER ====================
    
    def get_trade_statistics(self, days: int = 30) -> Dict:
        """İşlem istatistiklerini al"""
        sql = """
        SELECT 
            COUNT(*) as total_trades,
            COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
            COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_trades,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl,
            MAX(pnl) as best_trade,
            MIN(pnl) as worst_trade,
            AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
            AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss
        FROM trades
        WHERE opened_at > %s AND status = 'CLOSED'
        """
        
        cutoff = datetime.now() - timedelta(days=days)
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (cutoff,))
                row = cur.fetchone()
                if row:
                    stats = dict(row)
                    total = stats['total_trades'] or 0
                    winning = stats['winning_trades'] or 0
                    stats['win_rate'] = (winning / total * 100) if total > 0 else 0
                    return stats
                return {}


# Test
def test_database():
    """Veritabanı testleri"""
    print("=" * 60)
    print("Veritabanı Testi")
    print("=" * 60)
    
    db = Database()
    
    # Test sinyal kaydet
    signal_id = db.save_signal({
        'coin': 'BTC',
        'side': 'LONG',
        'entries': [42000, 41500],
        'take_profits': [43000, 44000, 45000],
        'stop_loss': 40000,
        'leverage': 20,
        'source': 'test',
        'confidence': 0.85,
        'raw_message': 'Test sinyal mesajı'
    })
    print(f"\n✓ Sinyal kaydedildi: ID={signal_id}")
    
    # Test işlem kaydet
    trade_id = db.save_trade({
        'signal_id': signal_id,
        'coin': 'BTC',
        'side': 'LONG',
        'entry_price': 42000,
        'volume': 100,
        'leverage': 20,
        'stop_loss': 40000,
        'take_profit': 45000
    })
    print(f"✓ İşlem kaydedildi: ID={trade_id}")
    
    # Test bot durumu
    db.set_bot_status('last_run', datetime.now().isoformat())
    status = db.get_bot_status('last_run')
    print(f"✓ Bot durumu kaydedildi: {status}")
    
    # Açık işlemler
    open_trades = db.get_open_trades()
    print(f"✓ Açık işlem sayısı: {len(open_trades)}")
    
    print("\n" + "=" * 60)
    print("Veritabanı testi tamamlandı!")
    print("=" * 60)


if __name__ == "__main__":
    test_database()


