"""
KriptoBot Web Uygulaması - FastAPI Backend
Multi-user trading platform with Bybit integration
"""
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import hashlib
import jwt
import time
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

# Bybit API import
from bybit_api import BybitAPI, BybitTrader
import config

# ==================== APP CONFIG ====================
app = FastAPI(title="KriptoBot", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Secret
JWT_SECRET = os.getenv("JWT_SECRET", "kriptobot_secret_key_2024_change_this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 gün

security = HTTPBearer()

# ==================== DATABASE ====================
DB_PATH = "kriptobot.db"

def init_db():
    """Veritabanını başlat"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users tablosu
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # API Keys tablosu
    c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exchange TEXT DEFAULT 'bybit',
            api_key TEXT NOT NULL,
            api_secret TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Trades tablosu
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl REAL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Initialize database
init_db()

# ==================== MODELS ====================
class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class APIKeyCreate(BaseModel):
    api_key: str
    api_secret: str
    exchange: str = "bybit"

class TradeRequest(BaseModel):
    symbol: str
    side: str  # LONG or SHORT
    amount: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

# ==================== HELPERS ====================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(user_id: int, username: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz token")

def get_user_trader(user_id: int) -> Optional[BybitTrader]:
    """Kullanıcının API key'leri ile trader oluştur"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT api_key, api_secret FROM api_keys WHERE user_id = ? AND is_active = 1", (user_id,))
        row = c.fetchone()
        
        if row:
            # Geçici olarak config'i override et
            trader = BybitTrader()
            trader.api.api_key = row['api_key']
            trader.api.api_secret = row['api_secret']
            return trader
    return None

# ==================== AUTH ENDPOINTS ====================
@app.post("/api/register")
async def register(user: UserRegister):
    """Yeni kullanıcı kaydı"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Kullanıcı var mı kontrol
        c.execute("SELECT id FROM users WHERE username = ? OR email = ?", 
                  (user.username, user.email))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Kullanıcı adı veya email zaten kayıtlı")
        
        # Kullanıcı oluştur
        password_hash = hash_password(user.password)
        c.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                  (user.username, user.email, password_hash))
        conn.commit()
        
        user_id = c.lastrowid
        token = create_token(user_id, user.username)
        
        return {"success": True, "token": token, "user": {"id": user_id, "username": user.username}}

@app.post("/api/login")
async def login(user: UserLogin):
    """Kullanıcı girişi"""
    with get_db() as conn:
        c = conn.cursor()
        password_hash = hash_password(user.password)
        
        c.execute("SELECT id, username FROM users WHERE username = ? AND password_hash = ?",
                  (user.username, password_hash))
        row = c.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")
        
        token = create_token(row['id'], row['username'])
        return {"success": True, "token": token, "user": {"id": row['id'], "username": row['username']}}

@app.get("/api/me")
async def get_me(payload: dict = Depends(verify_token)):
    """Mevcut kullanıcı bilgisi"""
    return {"user_id": payload['user_id'], "username": payload['username']}

# ==================== API KEY ENDPOINTS ====================
@app.post("/api/keys")
async def add_api_key(key_data: APIKeyCreate, payload: dict = Depends(verify_token)):
    """API key ekle"""
    user_id = payload['user_id']
    
    # API key'i test et
    test_api = BybitAPI()
    test_api.api_key = key_data.api_key
    test_api.api_secret = key_data.api_secret
    
    result = test_api._request('GET', '/v5/user/query-api')
    if not result['success']:
        raise HTTPException(status_code=400, detail=f"API key geçersiz: {result.get('error')}")
    
    with get_db() as conn:
        c = conn.cursor()
        # Eski key'leri deaktif et
        c.execute("UPDATE api_keys SET is_active = 0 WHERE user_id = ?", (user_id,))
        # Yeni key ekle
        c.execute("INSERT INTO api_keys (user_id, exchange, api_key, api_secret) VALUES (?, ?, ?, ?)",
                  (user_id, key_data.exchange, key_data.api_key, key_data.api_secret))
        conn.commit()
    
    return {"success": True, "message": "API key eklendi"}

@app.get("/api/keys")
async def get_api_keys(payload: dict = Depends(verify_token)):
    """Kullanıcının API key'lerini listele"""
    user_id = payload['user_id']
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, exchange, api_key, is_active, created_at FROM api_keys WHERE user_id = ?", (user_id,))
        keys = []
        for row in c.fetchall():
            keys.append({
                "id": row['id'],
                "exchange": row['exchange'],
                "api_key": row['api_key'][:8] + "..." + row['api_key'][-4:],  # Gizle
                "is_active": row['is_active'],
                "created_at": row['created_at']
            })
    
    return {"keys": keys}

# ==================== TRADING ENDPOINTS ====================
@app.get("/api/balance")
async def get_balance(payload: dict = Depends(verify_token)):
    """Bakiye bilgisi"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        raise HTTPException(status_code=400, detail="API key bulunamadı. Önce API key ekleyin.")
    
    balance = trader.get_available_balance()
    return {"balance": balance, "currency": "USDT"}

@app.get("/api/positions")
async def get_positions(payload: dict = Depends(verify_token)):
    """Açık pozisyonlar"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        raise HTTPException(status_code=400, detail="API key bulunamadı")
    
    positions = trader.get_all_positions()
    return {"positions": positions}

@app.get("/api/prices")
async def get_prices(payload: dict = Depends(verify_token)):
    """Tüm paritelerin fiyatları"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        # Public API kullan
        trader = BybitTrader()
    
    prices = trader.get_all_prices()
    return {"prices": prices}

@app.get("/api/portfolio")
async def get_portfolio(payload: dict = Depends(verify_token)):
    """Portföy özeti"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        raise HTTPException(status_code=400, detail="API key bulunamadı")
    
    summary = trader.get_portfolio_summary()
    return summary

@app.post("/api/trade")
async def open_trade(trade: TradeRequest, payload: dict = Depends(verify_token)):
    """İşlem aç"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        raise HTTPException(status_code=400, detail="API key bulunamadı")
    
    # Bakiye kontrol
    balance = trader.get_available_balance()
    if balance <= 0:
        raise HTTPException(status_code=400, detail="Yetersiz bakiye")
    
    result = trader.open_trade(
        symbol=trade.symbol,
        side=trade.side,
        usdt_amount=trade.amount,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit
    )
    
    if result['success']:
        # Trade'i kaydet
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trades (user_id, symbol, side, quantity, status)
                VALUES (?, ?, ?, ?, 'open')
            """, (payload['user_id'], trade.symbol, trade.side, trade.amount or 0))
            conn.commit()
    
    return result

@app.post("/api/close-all")
async def close_all_positions(payload: dict = Depends(verify_token)):
    """Tüm pozisyonları kapat"""
    trader = get_user_trader(payload['user_id'])
    if not trader:
        raise HTTPException(status_code=400, detail="API key bulunamadı")
    
    results = trader.close_all_positions()
    return {"results": results}

# ==================== AUTO TRADER ====================
import threading
from loguru import logger

auto_trader_running = False
auto_trader_thread = None
position_manager_thread = None

def run_auto_trader_background():
    """Background'da auto trader çalıştır"""
    global auto_trader_running
    try:
        from auto_trader import AutoTrader
        logger.info("🤖 Auto Trader başlatılıyor...")
        trader = AutoTrader()
        auto_trader_running = True
        trader.start()
    except Exception as e:
        logger.error(f"❌ Auto Trader hatası: {e}")
        auto_trader_running = False

def run_position_manager_background():
    """Background'da position manager çalıştır - DEVRE DIŞI (n8n yönetecek)"""
    # Position management artık n8n tarafından yapılacak
    # Railway'den Bybit API'ye erişim engelli
    logger.info("📊 Position Manager DEVRE DIŞI - n8n yönetecek")
    pass

# FastAPI başlangıcında bot'ları otomatik başlat
@app.on_event("startup")
async def startup_event():
    """Uygulama başladığında bot'ları başlat"""
    global auto_trader_thread, position_manager_thread, auto_trader_running
    
    logger.info("=" * 60)
    logger.info("🚀 KRİPTOBOT BAŞLATILIYOR...")
    logger.info("=" * 60)
    
    # Position Manager başlat
    position_manager_thread = threading.Thread(target=run_position_manager_background, daemon=True)
    position_manager_thread.start()
    logger.info("✅ Position Manager başlatıldı")
    
    # Auto Trader başlat
    auto_trader_thread = threading.Thread(target=run_auto_trader_background, daemon=True)
    auto_trader_thread.start()
    logger.info("✅ Auto Trader başlatıldı")
    
    logger.info("=" * 60)
    logger.info("🟢 Tüm servisler aktif!")
    logger.info("=" * 60)

@app.post("/api/auto-trader/start")
async def start_auto_trader(payload: dict = Depends(verify_token)):
    """Otomatik trader'ı başlat (zaten startup'ta başlıyor)"""
    global auto_trader_running, auto_trader_thread
    
    if auto_trader_running:
        return {"success": True, "message": "Auto trader zaten çalışıyor"}
    
    auto_trader_thread = threading.Thread(target=run_auto_trader_background, daemon=True)
    auto_trader_thread.start()
    
    return {"success": True, "message": "Auto trader başlatıldı"}

@app.get("/api/auto-trader/status")
async def get_auto_trader_status():
    """Auto trader durumu"""
    return {"running": auto_trader_running}

# ==================== PUBLIC ENDPOINTS ====================
@app.get("/api/pairs")
async def get_trading_pairs():
    """İşlem yapılabilir pariteler"""
    return {"pairs": config.TRADING_PAIRS, "count": len(config.TRADING_PAIRS)}

@app.get("/api/health")
async def health_check():
    """Sistem sağlık kontrolü"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# ==================== STATIC FILES ====================
# Frontend dosyaları için static klasör
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# Ana sayfa
@app.get("/", response_class=HTMLResponse)
async def root():
    return open("static/index.html", "r", encoding="utf-8").read()

# ==================== RUN ====================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

