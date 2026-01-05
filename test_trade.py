from bybit_api import BybitAPI, BybitTrader

print("=" * 60)
print("🚀 BTC LONG TEST İŞLEMİ")
print("=" * 60)

trader = BybitTrader()

# 1. Bakiye kontrol
print("\n📌 1. Bakiye Kontrolü:")
balance = trader.get_available_balance()
print(f"   💰 Kullanılabilir: {balance} USDT")

if balance <= 0:
    print("\n   ⚠️ BAKİYE YOK! Bybit'e USDT yatır.")
    print("=" * 60)
    exit()

# 2. BTC fiyatı
print("\n📌 2. BTC Fiyatı:")
price = trader.get_current_price('BTCUSDT')
print(f"   📈 BTC/USDT: ${price:,.2f}")

# 3. Pozisyon hesapla - minimum 0.001 BTC
print("\n📌 3. Pozisyon Hesaplama:")

# BTC için minimum kontrat: 0.001
min_qty = 0.001
min_usdt_needed = (min_qty * price) / 20  # 20x kaldıraç ile
print(f"   Minimum gerekli: ~{min_usdt_needed:.2f} USDT (0.001 BTC @ 20x)")

# %10 kullan (test için)
position_usdt = min(balance * 0.10, balance - 1)  # %10 veya bakiye - 1
leverage = 20

# Minimum 0.001 BTC olacak şekilde hesapla
qty = max(0.001, round((position_usdt * leverage) / price, 3))

print(f"   Kullanılacak: {position_usdt:.2f} USDT")
print(f"   Kaldıraç: {leverage}x")
print(f"   Kontrat: {qty} BTC (~${qty * price:.2f} değerinde)")

# 4. LONG aç
print("\n📌 4. BTC LONG AÇILIYOR...")
print("-" * 40)

# Stop loss ve take profit hesapla
stop_loss = round(price * 0.98, 2)  # %2 aşağı
take_profit = round(price * 1.03, 2)  # %3 yukarı

print(f"   Entry: ~${price:,.2f}")
print(f"   Stop Loss: ${stop_loss:,.2f} (-%2)")
print(f"   Take Profit: ${take_profit:,.2f} (+%3)")

# Kaldıraç ayarla
print("\n   Kaldıraç ayarlanıyor...")
trader.api.set_leverage('BTCUSDT', leverage)

# Emir ver
result = trader.api.place_order(
    symbol='BTCUSDT',
    side='Buy',
    qty=str(qty),
    order_type='Market',
    stop_loss=str(stop_loss),
    take_profit=str(take_profit),
    leverage=leverage
)

print("\n📌 5. SONUÇ:")
print("-" * 40)
if result.get('success'):
    print("   ✅ İŞLEM AÇILDI!")
    order_data = result.get('data', {})
    print(f"   Order ID: {order_data.get('orderId', 'N/A')}")
    print(f"   Order Link ID: {order_data.get('orderLinkId', 'N/A')}")
else:
    print(f"   ❌ HATA: {result.get('error')}")
    print(f"   Kod: {result.get('code')}")

# 6. Pozisyonları kontrol et
import time
print("\n   2 saniye bekleniyor...")
time.sleep(2)

print("\n📌 6. AÇIK POZİSYONLAR:")
positions = trader.get_all_positions()
if positions:
    for pos in positions:
        pnl = float(pos['unrealized_pnl'])
        pnl_str = f"+{pnl:.4f}" if pnl >= 0 else f"{pnl:.4f}"
        print(f"   ✅ {pos['symbol']} | {pos['side']} | Size: {pos['size']}")
        print(f"      Entry: ${pos['entry_price']} | PnL: {pnl_str} USDT")
else:
    print("   Pozisyon bulunamadı")

print("\n" + "=" * 60)
