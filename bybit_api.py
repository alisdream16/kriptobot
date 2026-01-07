"""
Bybit API Entegrasyonu - Spot ve Futures Trading
Bybit V5 API: https://bybit-exchange.github.io/docs/v5/intro
"""
import hmac
import hashlib
import time
import json
import requests
from typing import Dict, Optional, List
from loguru import logger
import config


class BybitAPI:
    """Bybit V5 API Client - Unified Trading Account"""
    
    def __init__(self):
        self.api_key = config.BYBIT_API_KEY
        self.api_secret = config.BYBIT_API_SECRET
        self.base_url = "https://api.bybit.com"
        self.recv_window = "5000"
        self.session = requests.Session()
    
    def _generate_signature(self, timestamp: str, params: str) -> str:
        """Generate HMAC SHA256 signature for Bybit V5"""
        sign_str = f"{timestamp}{self.api_key}{self.recv_window}{params}"
        return hmac.new(
            self.api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """Make authenticated request to Bybit V5 API"""
        if params is None:
            params = {}
        
        timestamp = str(int(time.time() * 1000))
        
        # Prepare params string for signature
        if method == 'GET':
            param_str = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        else:
            param_str = json.dumps(params)
        
        # Generate signature
        signature = self._generate_signature(timestamp, param_str)
        
        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': self.recv_window,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, headers=headers, timeout=30)
            else:
                response = self.session.post(url, data=json.dumps(params), headers=headers, timeout=30)
            
            # Response boş mu kontrol et
            if not response.text:
                logger.error(f"API boş yanıt döndü: {url}")
                return {'success': False, 'error': 'Empty response from API'}
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse hatası: {e} - Response: {response.text[:200]}")
                return {'success': False, 'error': f'JSON parse error: {e}'}
            
            if data.get('retCode') != 0:
                logger.error(f"Bybit API Hatası: {data.get('retCode')} - {data.get('retMsg')}")
                return {'success': False, 'error': data.get('retMsg'), 'code': data.get('retCode')}
            
            return {'success': True, 'data': data.get('result', {})}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API İsteği Hatası: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== MARKET DATA ====================
    
    def get_ticker(self, symbol: str, category: str = 'linear') -> Dict:
        """Coin fiyat bilgisi al"""
        params = {'category': category, 'symbol': symbol}
        return self._request('GET', '/v5/market/tickers', params)
    
    def get_kline(self, symbol: str, interval: str = '60', limit: int = 100, 
                  category: str = 'linear') -> Dict:
        """Mum verileri al - interval: 1,3,5,15,30,60,120,240,360,720,D,W,M"""
        params = {
            'category': category,
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        return self._request('GET', '/v5/market/kline', params)
    
    def get_orderbook(self, symbol: str, category: str = 'linear', limit: int = 50) -> Dict:
        """Order book bilgisi al"""
        params = {'category': category, 'symbol': symbol, 'limit': limit}
        return self._request('GET', '/v5/market/orderbook', params)
    
    # ==================== ACCOUNT ====================
    
    def get_wallet_balance(self, account_type: str = 'UNIFIED') -> Dict:
        """Cüzdan bakiyesi al - UNIFIED, SPOT, CONTRACT"""
        params = {'accountType': account_type}
        return self._request('GET', '/v5/account/wallet-balance', params)
    
    def get_positions(self, category: str = 'linear', symbol: str = None) -> Dict:
        """Açık pozisyonları al"""
        params = {'category': category, 'settleCoin': 'USDT'}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', '/v5/position/list', params)
    
    # ==================== TRADING ====================
    
    def place_order(self, symbol: str, side: str, qty: str, 
                    order_type: str = 'Market', price: str = None,
                    stop_loss: str = None, take_profit: str = None,
                    leverage: int = None, category: str = 'linear',
                    reduce_only: bool = False) -> Dict:
        """
        Emir ver
        
        Args:
            symbol: İşlem çifti (örn: BTCUSDT)
            side: 'Buy' veya 'Sell'
            qty: Miktar
            order_type: 'Market' veya 'Limit'
            price: Limit fiyat (Limit order için)
            stop_loss: Stop loss fiyatı
            take_profit: Take profit fiyatı
            leverage: Kaldıraç (opsiyonel)
            category: 'linear' (USDT perpetual), 'inverse', 'spot'
        """
        # Kaldıraç ayarla
        if leverage:
            self.set_leverage(symbol, leverage, category)
        
        params = {
            'category': category,
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'qty': str(qty),
        }
        
        if order_type == 'Limit' and price:
            params['price'] = str(price)
        
        if stop_loss:
            params['stopLoss'] = str(stop_loss)
        
        if take_profit:
            params['takeProfit'] = str(take_profit)
        
        if reduce_only:
            params['reduceOnly'] = True
        
        logger.info(f"Emir veriliyor: {symbol} {side} {qty}")
        return self._request('POST', '/v5/order/create', params)
    
    def cancel_order(self, symbol: str, order_id: str, category: str = 'linear') -> Dict:
        """Emir iptal et"""
        params = {
            'category': category,
            'symbol': symbol,
            'orderId': order_id
        }
        return self._request('POST', '/v5/order/cancel', params)
    
    def cancel_all_orders(self, category: str = 'linear', symbol: str = None) -> Dict:
        """Tüm emirleri iptal et"""
        params = {'category': category}
        if symbol:
            params['symbol'] = symbol
        return self._request('POST', '/v5/order/cancel-all', params)
    
    def get_open_orders(self, category: str = 'linear', symbol: str = None) -> Dict:
        """Açık emirleri al"""
        params = {'category': category}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', '/v5/order/realtime', params)
    
    # ==================== POSITION MANAGEMENT ====================
    
    def set_leverage(self, symbol: str, leverage: int, category: str = 'linear') -> Dict:
        """Kaldıraç ayarla"""
        params = {
            'category': category,
            'symbol': symbol,
            'buyLeverage': str(leverage),
            'sellLeverage': str(leverage)
        }
        return self._request('POST', '/v5/position/set-leverage', params)
    
    def set_trading_stop(self, symbol: str, stop_loss: str = None, 
                         take_profit: str = None, category: str = 'linear') -> Dict:
        """Pozisyon SL/TP güncelle"""
        params = {
            'category': category,
            'symbol': symbol,
            'positionIdx': 0  # One-way mode
        }
        
        if stop_loss:
            params['stopLoss'] = str(stop_loss)
        if take_profit:
            params['takeProfit'] = str(take_profit)
        
        return self._request('POST', '/v5/position/trading-stop', params)
    
    def close_position(self, symbol: str, side: str, qty: str = None,
                       category: str = 'linear') -> Dict:
        """
        Pozisyon kapat
        
        Args:
            symbol: İşlem çifti
            side: Pozisyonun tersi ('Buy' long kapatır, 'Sell' short kapatır)
            qty: Kapatılacak miktar (None ise tamamı)
        """
        # Mevcut pozisyonu al
        if qty is None:
            positions = self.get_positions(category, symbol)
            if positions['success']:
                pos_list = positions['data'].get('list', [])
                for pos in pos_list:
                    if pos['symbol'] == symbol and float(pos['size']) > 0:
                        qty = pos['size']
                        break
        
        if not qty:
            return {'success': False, 'error': 'Pozisyon bulunamadı'}
        
        # Pozisyonu kapat (ters işlem)
        return self.place_order(
            symbol=symbol,
            side='Sell' if side == 'Buy' else 'Buy',
            qty=qty,
            order_type='Market',
            category=category
        )


class BybitTrader:
    """Bybit Trading İşlemleri Yöneticisi"""
    
    def __init__(self):
        self.api = BybitAPI()
        self.leverage = config.LEVERAGE
        self.risk_percentage = config.RISK_PERCENTAGE
        self.trading_pairs = getattr(config, 'TRADING_PAIRS', ['BTCUSDT'])
    
    def get_available_balance(self) -> float:
        """Kullanılabilir USDT bakiyesini al"""
        result = self.api.get_wallet_balance('UNIFIED')
        if result['success']:
            coins = result['data'].get('list', [{}])[0].get('coin', [])
            for coin in coins:
                if coin['coin'] == 'USDT':
                    available = coin.get('availableToWithdraw') or coin.get('walletBalance') or '0'
                    if available == '' or available is None:
                        available = '0'
                    return float(available)
        return 0.0
    
    def calculate_position_size(self, balance: float = None) -> float:
        """Risk yönetimine göre pozisyon büyüklüğü hesapla"""
        if balance is None:
            balance = self.get_available_balance()
        
        position_size = balance * (self.risk_percentage / 100)
        return round(position_size, 2)
    
    def get_current_price(self, symbol: str) -> float:
        """Güncel fiyat al"""
        result = self.api.get_ticker(symbol)
        if result['success']:
            tickers = result['data'].get('list', [])
            if tickers:
                return float(tickers[0].get('lastPrice', 0))
        return 0.0
    
    def get_qty_step(self, symbol: str) -> tuple:
        """Sembol için miktar adımı ve minimum miktarı al"""
        # Yaygın coinler için miktar kuralları
        qty_rules = {
            'BTCUSDT': (0.001, 3),   # min 0.001, 3 decimal
            'ETHUSDT': (0.01, 2),    # min 0.01, 2 decimal
            'BNBUSDT': (0.01, 2),
            'SOLUSDT': (0.1, 1),
            'XRPUSDT': (1, 0),       # min 1, integer
            'DOGEUSDT': (1, 0),
            'ADAUSDT': (1, 0),
            'AVAXUSDT': (0.1, 1),
            'DOTUSDT': (0.1, 1),
            'LINKUSDT': (0.1, 1),
            'POLUSDT': (1, 0),
            'SHIBUSDT': (1, 0),
            'LTCUSDT': (0.1, 1),
            'ATOMUSDT': (0.1, 1),
            'UNIUSDT': (0.1, 1),
            'NEARUSDT': (0.1, 1),
            'APTUSDT': (0.1, 1),
            'ARBUSDT': (1, 0),
            'OPUSDT': (0.1, 1),
            'SUIUSDT': (1, 0),  # Integer only
            'PEPEUSDT': (1, 0),
        }
        return qty_rules.get(symbol, (0.1, 1))  # Default
    
    def open_long(self, symbol: str, usdt_amount: float = None,
                  stop_loss: float = None, take_profit: float = None) -> Dict:
        """Long pozisyon aç"""
        if usdt_amount is None:
            usdt_amount = self.calculate_position_size()
        
        # Kaldıraç ayarla
        self.api.set_leverage(symbol, self.leverage)
        
        # Fiyat al ve miktar hesapla
        price = self.get_current_price(symbol)
        if price == 0:
            return {'success': False, 'error': 'Fiyat alınamadı'}
        
        # Miktar kurallarını al
        min_qty, decimals = self.get_qty_step(symbol)
        
        # Kontrat miktarı hesapla (USDT / fiyat * kaldıraç)
        raw_qty = (usdt_amount * self.leverage) / price
        qty = max(min_qty, round(raw_qty, decimals))
        
        # Integer gerektiren coinler için
        if decimals == 0:
            qty = int(qty)
        
        logger.info(f"LONG açılıyor: {symbol} - {qty} kontrat @ {price} ({self.leverage}x)")
        
        return self.api.place_order(
            symbol=symbol,
            side='Buy',
            qty=str(qty),
            order_type='Market',
            stop_loss=str(stop_loss) if stop_loss else None,
            take_profit=str(take_profit) if take_profit else None
        )
    
    def open_short(self, symbol: str, usdt_amount: float = None,
                   stop_loss: float = None, take_profit: float = None) -> Dict:
        """Short pozisyon aç"""
        if usdt_amount is None:
            usdt_amount = self.calculate_position_size()
        
        # Kaldıraç ayarla
        self.api.set_leverage(symbol, self.leverage)
        
        # Fiyat al ve miktar hesapla
        price = self.get_current_price(symbol)
        if price == 0:
            return {'success': False, 'error': 'Fiyat alınamadı'}
        
        # Miktar kurallarını al
        min_qty, decimals = self.get_qty_step(symbol)
        
        # Kontrat miktarı hesapla
        raw_qty = (usdt_amount * self.leverage) / price
        qty = max(min_qty, round(raw_qty, decimals))
        
        # Integer gerektiren coinler için
        if decimals == 0:
            qty = int(qty)
        
        logger.info(f"SHORT açılıyor: {symbol} - {qty} kontrat @ {price} ({self.leverage}x)")
        
        return self.api.place_order(
            symbol=symbol,
            side='Sell',
            qty=str(qty),
            order_type='Market',
            stop_loss=str(stop_loss) if stop_loss else None,
            take_profit=str(take_profit) if take_profit else None
        )
    
    def close_all_positions(self, symbol: str = None) -> List[Dict]:
        """Tüm pozisyonları kapat"""
        results = []
        positions = self.api.get_positions(symbol=symbol)
        
        if not positions['success']:
            return [positions]
        
        for pos in positions['data'].get('list', []):
            if float(pos.get('size', 0)) > 0:
                close_side = 'Sell' if pos['side'] == 'Buy' else 'Buy'
                result = self.api.place_order(
                    symbol=pos['symbol'],
                    side=close_side,
                    qty=pos['size'],
                    order_type='Market'
                )
                results.append({
                    'symbol': pos['symbol'],
                    'closed_size': pos['size'],
                    'result': result
                })
                logger.info(f"Pozisyon kapatıldı: {pos['symbol']} {pos['size']}")
        
        return results
    
    def update_stop_loss(self, symbol: str, stop_loss: float) -> Dict:
        """Stop loss güncelle"""
        return self.api.set_trading_stop(symbol, stop_loss=stop_loss)
    
    def update_take_profit(self, symbol: str, take_profit: float) -> Dict:
        """Take profit güncelle"""
        return self.api.set_trading_stop(symbol, take_profit=take_profit)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Tüm paritelerin fiyatlarını al"""
        prices = {}
        for symbol in self.trading_pairs:
            price = self.get_current_price(symbol)
            if price > 0:
                prices[symbol] = price
        return prices
    
    def get_all_positions(self) -> List[Dict]:
        """Tüm açık pozisyonları al"""
        result = self.api.get_positions()
        if result['success']:
            positions = []
            for pos in result['data'].get('list', []):
                if float(pos.get('size', 0)) > 0:
                    positions.append({
                        'symbol': pos['symbol'],
                        'side': pos['side'],
                        'size': pos['size'],
                        'entry_price': pos.get('avgPrice', '0'),
                        'mark_price': pos.get('markPrice', '0'),
                        'unrealized_pnl': pos.get('unrealisedPnl', '0'),
                        'leverage': pos.get('leverage', '0'),
                    })
            return positions
        return []
    
    def open_trade(self, symbol: str, side: str, usdt_amount: float = None,
                   stop_loss: float = None, take_profit: float = None) -> Dict:
        """
        Herhangi bir paritede işlem aç
        
        Args:
            symbol: Parite (örn: BTCUSDT, ETHUSDT)
            side: 'LONG' veya 'SHORT'
            usdt_amount: İşlem miktarı (USDT)
            stop_loss: Stop loss fiyatı
            take_profit: Take profit fiyatı
        """
        if side.upper() == 'LONG':
            return self.open_long(symbol, usdt_amount, stop_loss, take_profit)
        elif side.upper() == 'SHORT':
            return self.open_short(symbol, usdt_amount, stop_loss, take_profit)
        else:
            return {'success': False, 'error': f'Geçersiz side: {side}'}
    
    def get_portfolio_summary(self) -> Dict:
        """Portföy özeti al"""
        balance = self.get_available_balance()
        positions = self.get_all_positions()
        
        total_pnl = sum(float(p.get('unrealized_pnl', 0)) for p in positions)
        
        return {
            'available_balance': balance,
            'open_positions': len(positions),
            'positions': positions,
            'total_unrealized_pnl': total_pnl,
            'trading_pairs': self.trading_pairs
        }
    
    def scan_opportunities(self) -> List[Dict]:
        """Tüm pariteleri tara ve fırsatları bul (placeholder)"""
        opportunities = []
        prices = self.get_all_prices()
        
        for symbol, price in prices.items():
            opportunities.append({
                'symbol': symbol,
                'price': price,
                'signal': None  # Sinyal analizi eklenecek
            })
        
        return opportunities


# Test fonksiyonu
def test_connection():
    """API bağlantısını test et"""
    api = BybitAPI()
    trader = BybitTrader()
    
    print("=" * 50)
    print("Bybit API Bağlantı Testi")
    print("=" * 50)
    
    # Ticker testi
    print("\n1. BTC/USDT Fiyatı:")
    result = api.get_ticker('BTCUSDT')
    if result['success']:
        price = result['data']['list'][0]['lastPrice']
        print(f"   ✅ BTC/USDT: ${price}")
    else:
        print(f"   ❌ Hata: {result.get('error')}")
    
    # Bakiye testi
    print("\n2. Hesap Bakiyesi:")
    balance = trader.get_available_balance()
    print(f"   💰 Kullanılabilir: {balance} USDT")
    
    # Pozisyon testi
    print("\n3. Açık Pozisyonlar:")
    result = api.get_positions()
    if result['success']:
        positions = result['data'].get('list', [])
        if positions:
            for pos in positions:
                if float(pos.get('size', 0)) > 0:
                    print(f"   📈 {pos['symbol']}: {pos['side']} {pos['size']}")
        else:
            print("   Açık pozisyon yok")
    
    print("\n" + "=" * 50)
    print("Test tamamlandı!")
    print("=" * 50)


if __name__ == "__main__":
    test_connection()

