"""
Kripto Trading Bot - Yapılandırma Dosyası
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== BYBIT API ====================
BYBIT_API_KEY = "NdLbjwjnMhkzkeyjdQ"
BYBIT_API_SECRET = "fOtnTlaFk6frzihzS9msBVqXTzdpX08Ww3en"
BYBIT_BASE_URL = "https://api.bybit.com"

# ==================== LBANK API (Spot için) ====================
LBANK_API_KEY = "f40dd424-0453-4aff-abd1-19e4874ac01c"
LBANK_SECRET_KEY = "F8C97FD1151A2C0CC73B57699F6B5D18"
LBANK_BASE_URL = "https://api.lbank.info"
LBANK_FUTURES_URL = "https://fapi.lbank.info"

# ==================== TELEGRAM ====================
TELEGRAM_API_ID = "30699278"
TELEGRAM_API_HASH = "414fce59162a6c4cd114e8d4397ec896"
TELEGRAM_PHONE = "+905384877162"
TELEGRAM_PASSWORD = ""  # 2FA şifren varsa buraya yaz

# İzlenecek kanallar (t.me/ linkinden sonraki kısım)
TELEGRAM_CHANNELS = [
    "kazan_7234",             # Silver Trade ana kanal
    "SilverTradeVIP",         # Silver Trade VIP (büyük küçük harf önemli)
    "BalinaSinyalleri",       # Balina Sinyalleri
]

# ==================== GEMINI AI ====================
GEMINI_API_KEY = "AIzaSyBo83RBvYCJbKahS0l3qBJ7RAr2XCxOVxE"
GEMINI_MODEL = "gemini-1.5-flash"

# ==================== SUPABASE ====================
SUPABASE_URL = "postgresql://postgres.ldimzjflhvtpeqacbjcm:KriptoBot16@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

# ==================== TİCARET AYARLARI ====================
# İşlem yapılacak pariteler (60 parite - Bybit destekli)
TRADING_PAIRS = [
    # Top 20
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "POLUSDT", "SHIBUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
    # 21-40
    "PEPEUSDT", "FILUSDT", "ICPUSDT", "HBARUSDT", "VETUSDT",
    "MKRUSDT", "AAVEUSDT", "GRTUSDT", "INJUSDT", "RENDERUSDT",
    "FTMUSDT", "THETAUSDT", "ALGOUSDT", "FLOWUSDT", "XTZUSDT",
    "AXSUSDT", "SANDUSDT", "MANAUSDT", "GALAUSDT", "APEUSDT",
    # 41-60
    "LDOUSDT", "CRVUSDT", "QNTUSDT", "EGLDUSDT", "EOSUSDT",
    "CFXUSDT", "STXUSDT", "IMXUSDT", "RUNEUSDT", "MINAUSDT",
    "KAVAUSDT", "SNXUSDT", "ZECUSDT", "NEOUSDT", "IOTAUSDT",
    "COMPUSDT", "1INCHUSDT", "ENSUSDT", "GMXUSDT", "WOOUSDT",
]

# Risk Yönetimi
RISK_PERCENTAGE = 4.0          # Kasanın %4'ü ile işlem
LEVERAGE = 20                   # 20x kaldıraç
MIN_DAILY_PROFIT_TARGET = 10.0  # Günlük minimum %10 hedef

# TP Stratejisi (5 TP noktası için)
TP_PERCENTAGES = [20, 20, 20, 20, 20]  # Her TP'de %20 kapat

# Zamanlama
SIGNAL_CHECK_INTERVAL = 30      # Dakika - sinyal kontrolü
GEMINI_ANALYSIS_INTERVAL = 60   # Dakika - Gemini analizi
SCALPER_INTERVAL = 60           # Dakika - Scalper modu

# ==================== TEKNİK ANALİZ ====================
# RSI Ayarları
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# EMA Ayarları
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

# Elliott Wave parametreleri
ELLIOTT_MIN_WAVE_SIZE = 0.5  # Minimum dalga büyüklüğü (%)

# ==================== LOGLAMA ====================
LOG_LEVEL = "INFO"
LOG_FILE = "trading_bot.log"

