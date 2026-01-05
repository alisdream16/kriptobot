import requests
import time
import hashlib
import base64

# LBank Futures API - Session Based
BASE_URL = "https://uuapi.rerrkvifj.com"

# Tarayıcıdan aldığın token (bu geçici, her oturumda değişir)
EX_TOKEN = "312a9390ca9b4abf9b123e7deab0603a"
EX_DEVICE_ID = "GAr7hwZYk7krdfVNMFLiFGjUcqoCWCmU"

def generate_signature(timestamp):
    """Generate ex-signature"""
    # Bu muhtemelen timestamp + secret hash
    data = str(timestamp)
    signature = hashlib.sha256(data.encode()).hexdigest()
    return base64.b64encode(signature.encode()).decode()

def make_futures_request(endpoint, params=None):
    """Make request to LBank Futures API"""
    if params is None:
        params = {}
    
    timestamp = str(int(time.time() * 1000))
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'ex-token': EX_TOKEN,
        'ex-device-id': EX_DEVICE_ID,
        'ex-timestamp': timestamp,
        'ex-signature': generate_signature(timestamp),
        'ex-browser-name': 'Chrome',
        'ex-browser-version': '143.0.0.0',
        'ex-client-channel': 'WEB',
        'ex-client-source': 'WEB',
        'ex-client-type': 'WEB',
        'ex-client-version-code': '20251120',
        'ex-language': 'en-US',
        'ex-os-name': 'Windows',
        'ex-os-version': '10',
        'businessversioncode': '201',
        'source': '4',
        'versionflage': 'true',
        'origin': 'https://www.lbank.com',
        'referer': 'https://www.lbank.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else r.text
    except Exception as e:
        return 0, str(e)

print("=" * 70)
print("LBANK FUTURES API - SESSION TOKEN TESTİ")
print("=" * 70)

# Test endpoints
tests = [
    # Pozisyonlar
    ("/cfd/query/v1.0/Position", {
        'ProductGroup': 'SwapU',
        'Valid': '1',
        'pageIndex': '1',
        'pageSize': '1000'
    }),
    # Hesap bilgisi
    ("/cfd/user/v1/Account", {}),
    ("/cfd/user/v1/getAccount", {}),
    ("/cfd/query/v1.0/Account", {'ProductGroup': 'SwapU'}),
    # Bakiye
    ("/cfd/user/v1/Balance", {}),
    ("/cfd/query/v1.0/Balance", {'ProductGroup': 'SwapU'}),
    # Emirler
    ("/cfd/query/v1.0/Order", {
        'ProductGroup': 'SwapU',
        'ExchangeID': 'Exchange',
        'pageIndex': '1',
        'pageSize': '1000'
    }),
    # Kupon/Popup (bu çalıştığını biliyoruz)
    ("/cfd/user/v1/positionCouponPopup", {}),
]

print("\n📌 Endpoint Testleri:\n")

for endpoint, params in tests:
    status, response = make_futures_request(endpoint, params)
    print(f"🔹 {endpoint}")
    print(f"   Status: {status}")
    if isinstance(response, dict):
        if response.get('success') == True or response.get('result') == 'true':
            print(f"   ✅ SUCCESS: {str(response)[:200]}")
        else:
            print(f"   ❌ Error: {response.get('msg', response)}")
    else:
        print(f"   Response: {str(response)[:150]}")
    print()

print("=" * 70)
print("\n💡 NOT: ex-token tarayıcı oturumundan alındı.")
print("   Token süresi dolmuşsa yeni token almak gerekir!")
print("=" * 70)
