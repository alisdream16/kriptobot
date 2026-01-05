from bybit_api import BybitAPI, BybitTrader
import config

print("=" * 70)
print("BYBIT MULTI-PAIR FUTURES TEST")
print("=" * 70)

api = BybitAPI()
trader = BybitTrader()

# 1. Bakiye
print("\n📌 1. Bakiye:")
balance = trader.get_available_balance()
print(f"   💰 Kullanılabilir USDT: {balance}")

# 2. Tüm paritelerin fiyatları
print(f"\n📌 2. Parite Fiyatları ({len(trader.trading_pairs)} parite):")
print("-" * 50)
prices = trader.get_all_prices()
for symbol, price in prices.items():
    print(f"   {symbol:12} : ${price:,.2f}")

# 3. Açık pozisyonlar
print(f"\n📌 3. Açık Pozisyonlar:")
print("-" * 50)
positions = trader.get_all_positions()
if positions:
    for pos in positions:
        pnl = float(pos['unrealized_pnl'])
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        print(f"   {pos['symbol']:12} | {pos['side']:5} | Size: {pos['size']}")
        print(f"   {'':<12} | Entry: {pos['entry_price']} | PnL: {pnl_color} {pnl:.2f} USDT")
        print()
else:
    print("   Açık pozisyon yok")

# 4. Portföy özeti
print(f"\n📌 4. Portföy Özeti:")
print("-" * 50)
summary = trader.get_portfolio_summary()
print(f"   Bakiye: {summary['available_balance']} USDT")
print(f"   Açık Pozisyon: {summary['open_positions']}")
print(f"   Toplam PnL: {summary['total_unrealized_pnl']:.2f} USDT")
print(f"   Takip Edilen Parite: {len(summary['trading_pairs'])}")

# 5. İşlem örneği
print(f"\n📌 5. İşlem Açma Örnekleri:")
print("-" * 50)
if balance > 0:
    print("   ✅ Bakiye var - İşlem açılabilir!\n")
    print("   # BTC LONG:")
    print("   trader.open_trade('BTCUSDT', 'LONG', stop_loss=93000, take_profit=96000)")
    print("\n   # ETH SHORT:")
    print("   trader.open_trade('ETHUSDT', 'SHORT', stop_loss=3500, take_profit=3200)")
    print("\n   # SOL LONG:")
    print("   trader.open_trade('SOLUSDT', 'LONG', stop_loss=180, take_profit=220)")
else:
    print("   ⚠️ Bakiye 0 - Önce Bybit'e USDT yatır!")

# 6. Mevcut pariteler
print(f"\n📌 6. Desteklenen Pariteler:")
print("-" * 50)
pairs_str = ", ".join(trader.trading_pairs)
print(f"   {pairs_str}")

print("\n" + "=" * 70)
print("✅ Tüm pariteler çalışıyor!")
print("=" * 70)
