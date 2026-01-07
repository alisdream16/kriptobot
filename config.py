"""
Kripto Trading Bot - Yapılandırma Dosyası
API key'ler .env dosyasından okunur (güvenlik için)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== BYBIT API ====================
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
BYBIT_BASE_URL = "https://api.bybit.com"

# ==================== LBANK API (Spot için) ====================
LBANK_API_KEY = os.getenv("LBANK_API_KEY", "")
LBANK_SECRET_KEY = os.getenv("LBANK_SECRET_KEY", "")
LBANK_BASE_URL = "https://api.lbank.info"
LBANK_FUTURES_URL = "https://fapi.lbank.info"

# ==================== TELEGRAM ====================
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_PASSWORD = ""  # 2FA şifren varsa buraya yaz

# İzlenecek kanallar (t.me/ linkinden sonraki kısım)
TELEGRAM_CHANNELS = [
    "kazan_7234",             # Silver Trade ana kanal
    "SilverTradeVIP",         # Silver Trade VIP (büyük küçük harf önemli)
    "BalinaSinyalleri",       # Balina Sinyalleri
]

# ==================== GEMINI AI ====================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# ==================== SUPABASE ====================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

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

