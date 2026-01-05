"""
KriptoBot Başlatıcı
Kolay kullanım için basit başlatma scripti
"""
import asyncio
import sys
from loguru import logger


def check_requirements():
    """Gerekli kütüphaneleri kontrol et"""
    required = [
        'requests',
        'psycopg2',
        'google.generativeai',
        'apscheduler',
        'telethon',
        'loguru'
    ]
    
    missing = []
    
    for module in required:
        try:
            __import__(module.split('.')[0])
        except ImportError:
            missing.append(module)
    
    if missing:
        print("❌ Eksik kütüphaneler tespit edildi:")
        for m in missing:
            print(f"   - {m}")
        print("\nKurulum için: pip install -r requirements.txt")
        return False
    
    return True


def test_connections():
    """API bağlantılarını test et"""
    print("\n🔍 Bağlantılar test ediliyor...\n")
    
    # LBank testi
    print("1. LBank API testi...")
    try:
        from lbank_api import LBankAPI
        api = LBankAPI()
        result = api.get_ticker('btc_usdt')
        if result['success']:
            print("   ✅ LBank API: Bağlantı başarılı")
            data = result.get('data', [{}])
            if data:
                ticker = data[0] if isinstance(data, list) else data
                print(f"   BTC/USDT Fiyat: {ticker.get('ticker', {}).get('latest', 'N/A')}")
        else:
            print(f"   ⚠️ LBank API: {result.get('error', 'Bilinmeyen hata')}")
    except Exception as e:
        print(f"   ❌ LBank API Hatası: {e}")
    
    # Futures hesap testi
    print("\n2. LBank Futures hesap testi...")
    try:
        from lbank_api import LBankTrader
        trader = LBankTrader()
        balance = trader.get_available_balance()
        print(f"   ✅ Futures Bakiye: {balance} USDT")
    except Exception as e:
        print(f"   ⚠️ Futures Hesap: {e}")
    
    # Veritabanı testi
    print("\n3. Supabase veritabanı testi...")
    try:
        from database import Database
        db = Database()
        db.set_bot_status('connection_test', 'OK')
        status = db.get_bot_status('connection_test')
        if status == 'OK':
            print("   ✅ Supabase: Bağlantı başarılı")
        else:
            print("   ⚠️ Supabase: Bağlantı sorunu")
    except Exception as e:
        print(f"   ❌ Supabase Hatası: {e}")
    
    # Gemini testi
    print("\n4. Gemini AI testi...")
    try:
        import google.generativeai as genai
        import config
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content("Merhaba, çalışıyor musun? Sadece 'Evet' de.")
        if response and response.text:
            print("   ✅ Gemini AI: Bağlantı başarılı")
        else:
            print("   ⚠️ Gemini AI: Yanıt alınamadı")
    except Exception as e:
        print(f"   ❌ Gemini Hatası: {e}")
    
    print("\n" + "=" * 50)


def main_menu():
    """Ana menü"""
    while True:
        print("""
╔═══════════════════════════════════════════════════════════╗
║                     KRİPTO TRADİNG BOT                    ║
╠═══════════════════════════════════════════════════════════╣
║  1. Botu Başlat (Tam Otomatik)                           ║
║  2. Bağlantı Testi                                        ║
║  3. Manuel Sinyal Gir                                     ║
║  4. Açık İşlemleri Göster                                 ║
║  5. Günlük Rapor                                          ║
║  6. LBank API Testi                                       ║
║  7. Gemini Analiz Testi                                   ║
║  0. Çıkış                                                 ║
╚═══════════════════════════════════════════════════════════╝
        """)
        
        choice = input("Seçiminiz: ").strip()
        
        if choice == '1':
            start_bot()
        elif choice == '2':
            test_connections()
        elif choice == '3':
            manual_signal_input()
        elif choice == '4':
            show_open_trades()
        elif choice == '5':
            show_daily_report()
        elif choice == '6':
            test_lbank()
        elif choice == '7':
            test_gemini()
        elif choice == '0':
            print("\nÇıkılıyor...")
            sys.exit(0)
        else:
            print("\n❌ Geçersiz seçim!")
        
        input("\nDevam etmek için Enter'a basın...")


def start_bot():
    """Botu başlat"""
    print("\n🚀 Bot başlatılıyor...\n")
    try:
        from main import main
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Bot durduruldu.")
    except Exception as e:
        print(f"\n❌ Hata: {e}")


def manual_signal_input():
    """Manuel sinyal girişi"""
    print("\n📝 Manuel Sinyal Girişi")
    print("-" * 40)
    
    try:
        coin = input("Coin (örn: BTC): ").strip().upper()
        side = input("Yön (LONG/SHORT): ").strip().upper()
        entry = float(input("Giriş fiyatı: "))
        
        tp_input = input("TP fiyatları (virgülle ayır, örn: 43000,44000,45000): ")
        take_profits = [float(tp.strip()) for tp in tp_input.split(',')]
        
        stop_loss = float(input("Stop loss: "))
        
        print(f"\n📊 Sinyal Özeti:")
        print(f"   Coin: {coin}")
        print(f"   Yön: {side}")
        print(f"   Giriş: {entry}")
        print(f"   TP: {take_profits}")
        print(f"   SL: {stop_loss}")
        
        confirm = input("\nOnayla (e/h): ").strip().lower()
        
        if confirm == 'e':
            from main import KriptoBot
            bot = KriptoBot()
            result = bot.manual_signal(coin, side, entry, take_profits, stop_loss)
            print(f"\n✅ Sonuç: {result}")
        else:
            print("\n❌ İptal edildi.")
            
    except ValueError as e:
        print(f"\n❌ Geçersiz değer: {e}")
    except Exception as e:
        print(f"\n❌ Hata: {e}")


def show_open_trades():
    """Açık işlemleri göster"""
    print("\n📈 Açık İşlemler")
    print("-" * 60)
    
    try:
        from database import Database
        db = Database()
        trades = db.get_open_trades()
        
        if not trades:
            print("Açık işlem yok.")
            return
        
        for trade in trades:
            print(f"""
   Coin: {trade['coin']}
   Yön: {trade['side']}
   Giriş: {trade['entry_price']}
   Güncel: {trade.get('current_price', 'N/A')}
   PNL: {trade.get('pnl_percentage', 0):.2f}%
   Açılış: {trade['opened_at']}
   ---""")
            
    except Exception as e:
        print(f"❌ Hata: {e}")


def show_daily_report():
    """Günlük rapor"""
    print("\n📊 Günlük Rapor")
    print("-" * 60)
    
    try:
        from database import Database
        from lbank_api import LBankTrader
        
        db = Database()
        trader = LBankTrader()
        
        balance = trader.get_available_balance()
        daily = db.get_daily_performance()
        stats = db.get_trade_statistics(days=1)
        
        print(f"""
   Güncel Bakiye: {balance:.2f} USDT
   
   Bugünkü Performans:
   - Başlangıç: {daily.get('starting_balance', 'N/A') if daily else 'N/A'}
   - PNL: {daily.get('total_pnl', 0) if daily else 0:.2f} USDT
   - PNL %: {daily.get('pnl_percentage', 0) if daily else 0:.2f}%
   
   İşlem İstatistikleri:
   - Toplam: {stats.get('total_trades', 0)}
   - Kazanan: {stats.get('winning_trades', 0)}
   - Kaybeden: {stats.get('losing_trades', 0)}
   - Win Rate: {stats.get('win_rate', 0):.1f}%
        """)
        
    except Exception as e:
        print(f"❌ Hata: {e}")


def test_lbank():
    """LBank API testi"""
    print("\n🔧 LBank API Detaylı Testi")
    print("-" * 60)
    
    try:
        from lbank_api import test_connection
        test_connection()
    except Exception as e:
        print(f"❌ Hata: {e}")


def test_gemini():
    """Gemini analiz testi"""
    print("\n🤖 Gemini Analiz Testi")
    print("-" * 60)
    
    try:
        from gemini_analyzer import test_gemini
        test_gemini()
    except Exception as e:
        print(f"❌ Hata: {e}")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                  KRİPTO BOT BAŞLATICI                     ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    if not check_requirements():
        print("\n⚠️ Önce gerekli kütüphaneleri yükleyin!")
        sys.exit(1)
    
    main_menu()


