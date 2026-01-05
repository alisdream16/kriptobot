"""
LBank API Entegrasyonu - Spot ve Futures Trading
LBank API Dokümantasyonu: https://www.lbank.com/docs/index.html
"""
import hashlib
import hmac
import time
import json
import random
import string
import requests
from urllib.parse import urlencode
from typing import Dict, Optional, List
from loguru import logger
import config


class LBankAPI:
    """LBank Spot ve Futures API Client - V2 API"""
    
    def __init__(self):
        self.api_key = config.LBANK_API_KEY
        self.secret_key = config.LBANK_SECRET_KEY
        self.base_url = "https://api.lbank.info"
        self.futures_url = "https://fapi.lbank.info"
        self.session = requests.Session()
    
    def _generate_echostr(self, length: int = 35) -> str:
        """30-40 karakter arası rastgele echostr oluştur"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    def _generate_sign_v2(self, params: Dict) -> str:
        """
        LBank V2 API için HmacSHA256 imza oluştur
        1. Parametreleri alfabetik sırala
        2. MD5 hash al (uppercase)
        3. HmacSHA256 ile imzala
        """
        # Parametreleri alfabetik sırala
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        params_string = urlencode(sorted_params)
        
        # MD5 hash al ve uppercase yap
        md5_hash = hashlib.md5(params_string.encode('utf-8')).hexdigest().upper()
        
        # HmacSHA256 ile imzala
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            md5_hash.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _get_timestamp(self) -> str:
        """Milisaniye cinsinden timestamp"""
        return str(int(time.time() * 1000))
    
    def _request(self, method: str, endpoint: str, params: Dict = None, 
                 is_futures: bool = False, signed: bool = True) -> Dict:
        """API isteği gönder - LBank V2 formatında"""
        base = self.futures_url if is_futures else self.base_url
        url = f"{base}{endpoint}"
        
        if params is None:
            params = {}
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        if signed:
            # V2 API gereksinimleri
            params['api_key'] = self.api_key
            timestamp = self._get_timestamp()
            echostr = self._generate_echostr()
            
            # Header'lara ekle
            headers['timestamp'] = timestamp
            headers['signature_method'] = 'HmacSHA256'
            headers['echostr'] = echostr
            
            # İmza için parametrelere ekle
            sign_params = params.copy()
            sign_params['timestamp'] = timestamp
            sign_params['echostr'] = echostr
            sign_params['signature_method'] = 'HmacSHA256'
            
            # İmza oluştur
            params['sign'] = self._generate_sign_v2(sign_params)
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, headers=headers, timeout=30)
            else:
                response = self.session.post(url, data=params, headers=headers, timeout=30)
            
            response.raise_for_status()
            data = response.json()
            
            # LBank hata kontrolü
            if isinstance(data, dict):
                error_code = data.get('error_code')
                if error_code and str(error_code) != '0':
                    error_msg = data.get('msg') or self._get_error_message(error_code)
                    logger.error(f"LBank API Hatası: {error_code} - {error_msg}")
                    return {'success': False, 'error': error_msg, 'code': error_code}
                if data.get('result') == 'false':
                    error_code = data.get('error_code', 'unknown')
                    error_msg = data.get('msg') or self._get_error_message(error_code)
                    logger.error(f"LBank API Hatası: {error_code} - {error_msg}")
                    return {'success': False, 'error': error_msg, 'code': error_code}
            
            return {'success': True, 'data': data}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API İsteği Hatası: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_error_message(self, error_code) -> str:
        """LBank hata kodlarını çevir"""
        error_messages = {
            '10000': 'Dahili hata',
            '10001': 'Gerekli parametreler eksik',
            '10002': 'Doğrulama hatası',
            '10003': 'Geçersiz parametre',
            '10004': 'İstek çok sık',
            '10005': 'Secret key mevcut değil',
            '10006': 'Kullanıcı mevcut değil',
            '10007': 'Geçersiz imza',
            '10008': 'Geçersiz işlem çifti',
            '10009': 'Limit emir için fiyat ve miktar gerekli',
            '10010': 'Fiyat/miktar minimum gereksinimin altında',
            '10014': 'Hesapta yetersiz bakiye',
            '10016': 'Yetersiz hesap bakiyesi',
            '10022': 'API Key izni reddedildi - Geçersiz IP veya yetkiler',
            '10031': 'echostr uzunluğu 30-40 karakter olmalı',
            '10600': 'Replay saldırısı filtresi - timestamp kontrol edin',
        }
        return error_messages.get(str(error_code), f'Bilinmeyen hata: {error_code}')
    
    # ==================== SPOT API ====================
    
    def get_ticker(self, symbol: str) -> Dict:
        """Coin fiyat bilgisi al"""
        params = {'symbol': symbol.lower()}
        return self._request('GET', '/v2/ticker.do', params, signed=False)
    
    def get_depth(self, symbol: str, size: int = 60) -> Dict:
        """Order book bilgisi al"""
        params = {'symbol': symbol.lower(), 'size': size}
        return self._request('GET', '/v2/depth.do', params, signed=False)
    
    def get_kline(self, symbol: str, size: int = 100, type_: str = '1hour') -> Dict:
        """Mum verileri al"""
        params = {
            'symbol': symbol.lower(),
            'size': size,
            'type': type_,
            'time': self._get_timestamp()
        }
        return self._request('GET', '/v2/kline.do', params, signed=False)
    
    def get_user_info(self) -> Dict:
        """Hesap bilgilerini al"""
        return self._request('POST', '/v2/user_info.do', {})
    
    def get_balance(self) -> Dict:
        """Bakiye bilgilerini al"""
        result = self.get_user_info()
        if result['success']:
            return result
        return result
    
    # ==================== FUTURES API ====================
    
    def futures_get_account(self) -> Dict:
        """Futures hesap bilgilerini al"""
        return self._request('POST', '/cfd/openApi/v1/pub/getAccount', {}, is_futures=True)
    
    def futures_get_positions(self) -> Dict:
        """Açık pozisyonları al"""
        return self._request('POST', '/cfd/openApi/v1/pub/getPositions', {}, is_futures=True)
    
    def futures_open_position(self, symbol: str, side: str, volume: float, 
                               leverage: int = 20, price: float = None,
                               stop_loss: float = None, take_profit: float = None) -> Dict:
        """
        Futures pozisyon aç
        
        Args:
            symbol: İşlem çifti (örn: BTC_USDT)
            side: 'LONG' veya 'SHORT'
            volume: İşlem miktarı (USDT)
            leverage: Kaldıraç oranı
            price: Limit fiyat (None ise market order)
            stop_loss: Stop loss fiyatı
            take_profit: Take profit fiyatı
        """
        params = {
            'symbol': symbol.upper(),
            'direction': '1' if side.upper() == 'LONG' else '2',  # 1=Long, 2=Short
            'leverRate': str(leverage),
            'volume': str(volume),
            'orderType': '2' if price is None else '1',  # 1=Limit, 2=Market
        }
        
        if price:
            params['price'] = str(price)
        
        if stop_loss:
            params['stopLoss'] = str(stop_loss)
        
        if take_profit:
            params['takeProfit'] = str(take_profit)
        
        logger.info(f"Pozisyon açılıyor: {symbol} {side} {volume} USDT, {leverage}x")
        return self._request('POST', '/cfd/openApi/v1/pub/openPosition', params, is_futures=True)
    
    def futures_close_position(self, symbol: str, position_id: str = None,
                                close_volume: float = None) -> Dict:
        """
        Futures pozisyon kapat
        
        Args:
            symbol: İşlem çifti
            position_id: Pozisyon ID (opsiyonel)
            close_volume: Kapatılacak miktar (kısmi kapatma için)
        """
        params = {
            'symbol': symbol.upper(),
        }
        
        if position_id:
            params['positionId'] = position_id
        
        if close_volume:
            params['closeVolume'] = str(close_volume)
        
        logger.info(f"Pozisyon kapatılıyor: {symbol}")
        return self._request('POST', '/cfd/openApi/v1/pub/closePosition', params, is_futures=True)
    
    def futures_set_leverage(self, symbol: str, leverage: int) -> Dict:
        """Kaldıraç oranı ayarla"""
        params = {
            'symbol': symbol.upper(),
            'leverRate': str(leverage)
        }
        return self._request('POST', '/cfd/openApi/v1/pub/setLeverage', params, is_futures=True)
    
    def futures_get_orders(self, symbol: str = None, status: str = 'open') -> Dict:
        """Emirleri listele"""
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        params['status'] = status
        return self._request('POST', '/cfd/openApi/v1/pub/getOrders', params, is_futures=True)
    
    def futures_cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Emir iptal et"""
        params = {
            'symbol': symbol.upper(),
            'orderId': order_id
        }
        return self._request('POST', '/cfd/openApi/v1/pub/cancelOrder', params, is_futures=True)
    
    def futures_modify_position(self, symbol: str, position_id: str,
                                 stop_loss: float = None, 
                                 take_profit: float = None) -> Dict:
        """Pozisyon SL/TP güncelle"""
        params = {
            'symbol': symbol.upper(),
            'positionId': position_id
        }
        
        if stop_loss:
            params['stopLoss'] = str(stop_loss)
        if take_profit:
            params['takeProfit'] = str(take_profit)
        
        return self._request('POST', '/cfd/openApi/v1/pub/modifyPosition', params, is_futures=True)
    
    def futures_get_market_price(self, symbol: str) -> Dict:
        """Futures market fiyatını al"""
        params = {'symbol': symbol.upper()}
        return self._request('GET', '/cfd/openApi/v1/pub/getMarketPrice', params, 
                           is_futures=True, signed=False)
    
    def futures_get_kline(self, symbol: str, interval: str = '1h', 
                          limit: int = 100) -> Dict:
        """Futures mum verilerini al"""
        params = {
            'symbol': symbol.upper(),
            'interval': interval,
            'limit': limit
        }
        return self._request('GET', '/cfd/openApi/v1/pub/getKline', params,
                           is_futures=True, signed=False)


class LBankTrader:
    """LBank Trading İşlemleri Yöneticisi"""
    
    def __init__(self):
        self.api = LBankAPI()
        self.leverage = config.LEVERAGE
        self.risk_percentage = config.RISK_PERCENTAGE
    
    def get_available_balance(self) -> float:
        """Kullanılabilir bakiyeyi al"""
        result = self.api.futures_get_account()
        if result['success']:
            data = result.get('data', {})
            # LBank API'den gelen bakiye formatına göre ayarla
            if isinstance(data, dict):
                available = data.get('availableBalance') or data.get('available') or 0
                return float(available)
        return 0.0
    
    def calculate_position_size(self, balance: float = None) -> float:
        """
        Risk yönetimine göre pozisyon büyüklüğü hesapla
        Kasanın %2'si ile işlem
        """
        if balance is None:
            balance = self.get_available_balance()
        
        position_size = balance * (self.risk_percentage / 100)
        return round(position_size, 2)
    
    def open_trade(self, symbol: str, side: str, entries: List[float] = None,
                   take_profits: List[float] = None, stop_loss: float = None) -> Dict:
        """
        İşlem aç
        
        Args:
            symbol: Coin sembolü (örn: BTCUSDT)
            side: 'LONG' veya 'SHORT'
            entries: Giriş fiyatları listesi (birden fazla giriş için)
            take_profits: TP fiyatları listesi
            stop_loss: Stop loss fiyatı
        """
        # Sembolü formatla
        if not symbol.endswith('_USDT'):
            symbol = symbol.replace('USDT', '_USDT')
        
        balance = self.get_available_balance()
        total_position = self.calculate_position_size(balance)
        
        results = []
        
        # Birden fazla giriş varsa böl
        if entries and len(entries) > 1:
            position_per_entry = total_position / len(entries)
            for i, entry_price in enumerate(entries):
                result = self.api.futures_open_position(
                    symbol=symbol,
                    side=side,
                    volume=position_per_entry,
                    leverage=self.leverage,
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profits[0] if take_profits else None
                )
                results.append({
                    'entry': i + 1,
                    'price': entry_price,
                    'volume': position_per_entry,
                    'result': result
                })
                logger.info(f"Giriş {i+1}: {entry_price} @ {position_per_entry} USDT")
        else:
            # Tek giriş
            entry_price = entries[0] if entries else None
            result = self.api.futures_open_position(
                symbol=symbol,
                side=side,
                volume=total_position,
                leverage=self.leverage,
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profits[0] if take_profits else None
            )
            results.append({
                'entry': 1,
                'price': entry_price,
                'volume': total_position,
                'result': result
            })
        
        return {
            'symbol': symbol,
            'side': side,
            'total_volume': total_position,
            'entries': results,
            'take_profits': take_profits,
            'stop_loss': stop_loss
        }
    
    def close_partial(self, symbol: str, percentage: float = 20) -> Dict:
        """
        Pozisyonun belirli bir yüzdesini kapat (TP için)
        """
        if not symbol.endswith('_USDT'):
            symbol = symbol.replace('USDT', '_USDT')
        
        positions = self.api.futures_get_positions()
        if not positions['success']:
            return positions
        
        for pos in positions.get('data', []):
            if pos.get('symbol') == symbol:
                current_volume = float(pos.get('volume', 0))
                close_volume = current_volume * (percentage / 100)
                
                return self.api.futures_close_position(
                    symbol=symbol,
                    position_id=pos.get('positionId'),
                    close_volume=close_volume
                )
        
        return {'success': False, 'error': 'Pozisyon bulunamadı'}
    
    def move_stop_to_entry(self, symbol: str, entry_price: float) -> Dict:
        """Stop loss'u giriş fiyatına çek (başabaş)"""
        if not symbol.endswith('_USDT'):
            symbol = symbol.replace('USDT', '_USDT')
        
        positions = self.api.futures_get_positions()
        if not positions['success']:
            return positions
        
        for pos in positions.get('data', []):
            if pos.get('symbol') == symbol:
                return self.api.futures_modify_position(
                    symbol=symbol,
                    position_id=pos.get('positionId'),
                    stop_loss=entry_price
                )
        
        return {'success': False, 'error': 'Pozisyon bulunamadı'}


# Test fonksiyonu
def test_connection():
    """API bağlantısını test et"""
    api = LBankAPI()
    
    print("=" * 50)
    print("LBank API Bağlantı Testi")
    print("=" * 50)
    
    # Spot ticker testi
    print("\n1. Spot Ticker Testi (BTC/USDT):")
    result = api.get_ticker('btc_usdt')
    print(f"   Sonuç: {result}")
    
    # Futures hesap testi
    print("\n2. Futures Hesap Testi:")
    result = api.futures_get_account()
    print(f"   Sonuç: {result}")
    
    # Bakiye testi
    print("\n3. Bakiye Testi:")
    trader = LBankTrader()
    balance = trader.get_available_balance()
    print(f"   Kullanılabilir Bakiye: {balance} USDT")
    
    print("\n" + "=" * 50)
    print("Test tamamlandı!")
    print("=" * 50)


if __name__ == "__main__":
    test_connection()

