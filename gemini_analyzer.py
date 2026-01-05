"""
Gemini AI Kripto Analiz Modülü
RSI, Trend, Likidite, Hacim ve Elliott Wave analizi
"""
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import google.generativeai as genai
from loguru import logger
import config


@dataclass
class MarketAnalysis:
    """Piyasa analizi sonucu"""
    coin: str
    timestamp: datetime
    recommendation: str           # BUY, SELL, HOLD
    confidence: float             # 0-1 arası güven skoru
    entry_price: Optional[float]
    take_profits: List[float]
    stop_loss: Optional[float]
    leverage: int
    reasoning: str
    technical_summary: Dict
    risk_level: str              # LOW, MEDIUM, HIGH


class TechnicalIndicators:
    """Teknik göstergeler hesaplayıcı"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """RSI hesapla"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        """EMA hesapla"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # İlk SMA
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return round(ema, 8)
    
    @staticmethod
    def calculate_trend(prices: List[float]) -> str:
        """Trend belirle"""
        if len(prices) < 20:
            return "NEUTRAL"
        
        ema_fast = TechnicalIndicators.calculate_ema(prices, 9)
        ema_slow = TechnicalIndicators.calculate_ema(prices, 21)
        ema_trend = TechnicalIndicators.calculate_ema(prices, 50)
        
        current_price = prices[-1]
        
        if current_price > ema_fast > ema_slow > ema_trend:
            return "STRONG_BULLISH"
        elif current_price > ema_fast > ema_slow:
            return "BULLISH"
        elif current_price < ema_fast < ema_slow < ema_trend:
            return "STRONG_BEARISH"
        elif current_price < ema_fast < ema_slow:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    @staticmethod
    def detect_elliott_wave(prices: List[float]) -> Dict:
        """
        Basit Elliott Wave tespiti
        5 dalga impulse + 3 dalga correction
        """
        if len(prices) < 50:
            return {"wave": "UNKNOWN", "phase": "UNKNOWN", "next_move": "UNKNOWN"}
        
        # Pivot noktaları bul
        pivots = []
        for i in range(2, len(prices) - 2):
            # Local high
            if prices[i] > prices[i-1] and prices[i] > prices[i-2] and \
               prices[i] > prices[i+1] and prices[i] > prices[i+2]:
                pivots.append(("HIGH", i, prices[i]))
            # Local low
            elif prices[i] < prices[i-1] and prices[i] < prices[i-2] and \
                 prices[i] < prices[i+1] and prices[i] < prices[i+2]:
                pivots.append(("LOW", i, prices[i]))
        
        if len(pivots) < 5:
            return {"wave": "FORMING", "phase": "ACCUMULATION", "next_move": "WAIT"}
        
        # Son 5 pivot'u analiz et
        recent_pivots = pivots[-5:]
        
        # Impulse wave kontrolü (alternatif HIGH-LOW)
        is_impulse = True
        for i in range(1, len(recent_pivots)):
            if recent_pivots[i][0] == recent_pivots[i-1][0]:
                is_impulse = False
                break
        
        if is_impulse:
            # Yükseliş impulse (1-2-3-4-5)
            if recent_pivots[-1][0] == "HIGH" and recent_pivots[-1][2] > recent_pivots[-3][2]:
                return {
                    "wave": "IMPULSE_5",
                    "phase": "DISTRIBUTION",
                    "next_move": "CORRECTION_EXPECTED",
                    "description": "5. dalga tamamlanıyor, düzeltme bekleniyor"
                }
            # Düşüş impulse
            elif recent_pivots[-1][0] == "LOW" and recent_pivots[-1][2] < recent_pivots[-3][2]:
                return {
                    "wave": "IMPULSE_5_DOWN",
                    "phase": "CAPITULATION",
                    "next_move": "BOUNCE_EXPECTED",
                    "description": "Düşüş 5. dalga, toparlanma bekleniyor"
                }
            # Dalga 3 (en güçlü dalga)
            elif recent_pivots[-1][0] == "HIGH":
                return {
                    "wave": "IMPULSE_3",
                    "phase": "MARKUP",
                    "next_move": "CONTINUE_UP",
                    "description": "3. dalga (en güçlü), yükseliş devam edebilir"
                }
        
        # Correction wave
        return {
            "wave": "CORRECTION",
            "phase": "CONSOLIDATION",
            "next_move": "WAIT_FOR_BREAKOUT",
            "description": "Düzeltme dalgası, kırılım bekle"
        }
    
    @staticmethod
    def analyze_volume(volumes: List[float]) -> Dict:
        """Hacim analizi"""
        if len(volumes) < 20:
            return {"trend": "UNKNOWN", "strength": "UNKNOWN"}
        
        avg_volume = sum(volumes[-20:]) / 20
        recent_volume = sum(volumes[-5:]) / 5
        
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
        
        if volume_ratio > 1.5:
            return {"trend": "INCREASING", "strength": "HIGH", "ratio": volume_ratio}
        elif volume_ratio > 1.1:
            return {"trend": "INCREASING", "strength": "MODERATE", "ratio": volume_ratio}
        elif volume_ratio < 0.7:
            return {"trend": "DECREASING", "strength": "LOW", "ratio": volume_ratio}
        else:
            return {"trend": "STABLE", "strength": "NORMAL", "ratio": volume_ratio}


class GeminiAnalyzer:
    """Gemini AI Kripto Analiz Motoru"""
    
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)
        self.tech = TechnicalIndicators()
        self.last_request_time = 0
        self.request_interval = 2  # Saniye - rate limit koruması
    
    def _rate_limit(self):
        """Rate limit koruması"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self.last_request_time = time.time()
    
    def analyze_coin(self, coin: str, prices: List[float], 
                     volumes: List[float] = None,
                     additional_context: str = "") -> MarketAnalysis:
        """
        Coin'i kapsamlı analiz et
        
        Args:
            coin: Coin sembolü
            prices: Fiyat listesi (en eski -> en yeni)
            volumes: Hacim listesi
            additional_context: Ek bağlam (sinyal bilgisi vb.)
        """
        self._rate_limit()
        
        # Teknik göstergeleri hesapla
        current_price = prices[-1] if prices else 0
        rsi = self.tech.calculate_rsi(prices)
        trend = self.tech.calculate_trend(prices)
        elliott = self.tech.detect_elliott_wave(prices)
        volume_analysis = self.tech.analyze_volume(volumes) if volumes else {"trend": "UNKNOWN"}
        
        # EMA'ları hesapla
        ema_9 = self.tech.calculate_ema(prices, 9)
        ema_21 = self.tech.calculate_ema(prices, 21)
        ema_50 = self.tech.calculate_ema(prices, 50)
        
        technical_data = {
            "current_price": current_price,
            "rsi": rsi,
            "trend": trend,
            "ema_9": ema_9,
            "ema_21": ema_21,
            "ema_50": ema_50,
            "elliott_wave": elliott,
            "volume": volume_analysis,
            "price_change_24h": ((prices[-1] - prices[-24]) / prices[-24] * 100) if len(prices) >= 24 else 0
        }
        
        # Gemini'ye sor
        prompt = self._create_analysis_prompt(coin, technical_data, additional_context)
        
        try:
            response = self.model.generate_content(prompt)
            analysis = self._parse_gemini_response(response.text, coin, technical_data)
            return analysis
        except Exception as e:
            logger.error(f"Gemini analiz hatası: {e}")
            return self._fallback_analysis(coin, technical_data)
    
    def _create_analysis_prompt(self, coin: str, technical_data: Dict, 
                                 additional_context: str = "") -> str:
        """Gemini için analiz prompt'u oluştur"""
        prompt = f"""
Sen profesyonel bir kripto trader'ısın. Aşağıdaki teknik verilere göre {coin}/USDT için detaylı analiz yap.

## Teknik Veriler:
- Güncel Fiyat: {technical_data['current_price']}
- RSI (14): {technical_data['rsi']}
- Trend: {technical_data['trend']}
- EMA 9: {technical_data['ema_9']}
- EMA 21: {technical_data['ema_21']}
- EMA 50: {technical_data['ema_50']}
- Elliott Wave: {technical_data['elliott_wave']}
- Hacim Analizi: {technical_data['volume']}
- 24s Değişim: {technical_data['price_change_24h']:.2f}%

{f"## Ek Bilgi: {additional_context}" if additional_context else ""}

## Analiz Kriterleri:
1. RSI değerlendirmesi (aşırı alım/satım)
2. Trend gücü ve yönü
3. Elliott Wave fazı ve beklenen hareket
4. Hacim teyidi
5. Risk/Ödül oranı
6. Likidite bölgeleri

## İstenen Çıktı Formatı (JSON):
{{
    "recommendation": "BUY/SELL/HOLD",
    "confidence": 0.0-1.0,
    "entry_price": fiyat veya null,
    "take_profits": [tp1, tp2, tp3, tp4, tp5],
    "stop_loss": fiyat,
    "leverage": 1-20,
    "risk_level": "LOW/MEDIUM/HIGH",
    "reasoning": "Detaylı açıklama"
}}

Günlük %10 kar hedefine ulaşmak için agresif ama kontrollü işlemler öner.
Scalper gibi düşün - kısa vadeli fırsatları değerlendir.
Risk yönetimini unutma - kasanın %2'si ile işlem yapılacak.

SADECE JSON formatında yanıt ver, başka açıklama ekleme.
"""
        return prompt
    
    def _parse_gemini_response(self, response_text: str, coin: str, 
                                technical_data: Dict) -> MarketAnalysis:
        """Gemini yanıtını parse et"""
        try:
            # JSON'u temizle
            json_text = response_text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.startswith("```"):
                json_text = json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            
            data = json.loads(json_text.strip())
            
            return MarketAnalysis(
                coin=coin,
                timestamp=datetime.now(),
                recommendation=data.get("recommendation", "HOLD"),
                confidence=float(data.get("confidence", 0.5)),
                entry_price=data.get("entry_price"),
                take_profits=data.get("take_profits", []),
                stop_loss=data.get("stop_loss"),
                leverage=int(data.get("leverage", config.LEVERAGE)),
                reasoning=data.get("reasoning", ""),
                technical_summary=technical_data,
                risk_level=data.get("risk_level", "MEDIUM")
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Gemini yanıtı parse edilemedi: {e}")
            return self._fallback_analysis(coin, technical_data)
    
    def _fallback_analysis(self, coin: str, technical_data: Dict) -> MarketAnalysis:
        """Parse başarısız olursa fallback analiz"""
        rsi = technical_data.get("rsi", 50)
        trend = technical_data.get("trend", "NEUTRAL")
        current_price = technical_data.get("current_price", 0)
        
        # Basit kural bazlı karar
        recommendation = "HOLD"
        confidence = 0.3
        
        if rsi < 30 and "BULLISH" in trend:
            recommendation = "BUY"
            confidence = 0.6
        elif rsi > 70 and "BEARISH" in trend:
            recommendation = "SELL"
            confidence = 0.6
        elif rsi < 40 and trend == "STRONG_BULLISH":
            recommendation = "BUY"
            confidence = 0.7
        elif rsi > 60 and trend == "STRONG_BEARISH":
            recommendation = "SELL"
            confidence = 0.7
        
        # TP ve SL hesapla
        if recommendation == "BUY":
            take_profits = [
                current_price * 1.02,
                current_price * 1.04,
                current_price * 1.06,
                current_price * 1.08,
                current_price * 1.10
            ]
            stop_loss = current_price * 0.97
        elif recommendation == "SELL":
            take_profits = [
                current_price * 0.98,
                current_price * 0.96,
                current_price * 0.94,
                current_price * 0.92,
                current_price * 0.90
            ]
            stop_loss = current_price * 1.03
        else:
            take_profits = []
            stop_loss = None
        
        return MarketAnalysis(
            coin=coin,
            timestamp=datetime.now(),
            recommendation=recommendation,
            confidence=confidence,
            entry_price=current_price if recommendation != "HOLD" else None,
            take_profits=take_profits,
            stop_loss=stop_loss,
            leverage=config.LEVERAGE,
            reasoning=f"Fallback analiz: RSI={rsi}, Trend={trend}",
            technical_summary=technical_data,
            risk_level="MEDIUM"
        )
    
    def scalper_analysis(self, coin: str, prices: List[float],
                         volumes: List[float] = None) -> MarketAnalysis:
        """
        Scalper modu - kısa vadeli hızlı işlemler için
        """
        self._rate_limit()
        
        current_price = prices[-1] if prices else 0
        rsi = self.tech.calculate_rsi(prices[-50:]) if len(prices) >= 50 else 50
        
        # Son 1 saatlik trend
        short_trend = "NEUTRAL"
        if len(prices) >= 12:  # 5 dakikalık mumlar için
            recent_prices = prices[-12:]
            if recent_prices[-1] > recent_prices[0] * 1.005:
                short_trend = "BULLISH"
            elif recent_prices[-1] < recent_prices[0] * 0.995:
                short_trend = "BEARISH"
        
        prompt = f"""
Sen agresif bir kripto scalper'ısın. {coin}/USDT için 15 dakika - 1 saat içinde kapanacak kısa vadeli işlem öner.

## Veriler:
- Fiyat: {current_price}
- RSI: {rsi}
- Kısa Vadeli Trend: {short_trend}
- Son fiyatlar: {prices[-10:]}

## Kurallar:
- %0.5 - %2 arası kar hedefle
- Sıkı stop loss kullan (%1 max)
- Yüksek güven (>0.7) olmadan işlem önerme
- Scalp için ideal RSI: 35-45 (long), 55-65 (short)

JSON formatında yanıt ver:
{{
    "recommendation": "BUY/SELL/HOLD",
    "confidence": 0.0-1.0,
    "entry_price": fiyat,
    "take_profits": [tp1, tp2],
    "stop_loss": fiyat,
    "leverage": 10-20,
    "risk_level": "LOW/MEDIUM/HIGH",
    "reasoning": "Kısa açıklama"
}}

SADECE JSON ver.
"""
        
        try:
            response = self.model.generate_content(prompt)
            technical_data = {
                "current_price": current_price,
                "rsi": rsi,
                "trend": short_trend,
                "mode": "SCALPER"
            }
            return self._parse_gemini_response(response.text, coin, technical_data)
        except Exception as e:
            logger.error(f"Scalper analiz hatası: {e}")
            return self._fallback_analysis(coin, {"current_price": current_price, "rsi": rsi, "trend": short_trend})
    
    def validate_signal(self, coin: str, side: str, entry: float,
                        prices: List[float]) -> Tuple[bool, str, float]:
        """
        Telegram sinyalini doğrula
        
        Returns:
            (geçerli_mi, açıklama, güven_skoru)
        """
        self._rate_limit()
        
        current_price = prices[-1] if prices else entry
        rsi = self.tech.calculate_rsi(prices)
        trend = self.tech.calculate_trend(prices)
        elliott = self.tech.detect_elliott_wave(prices)
        
        prompt = f"""
Bir Telegram kanalından gelen kripto sinyalini doğrula:

## Sinyal:
- Coin: {coin}/USDT
- Yön: {side}
- Giriş Fiyatı: {entry}
- Güncel Fiyat: {current_price}

## Teknik Durum:
- RSI: {rsi}
- Trend: {trend}
- Elliott Wave: {elliott}

## Soru:
Bu sinyal güvenilir mi? İşleme girmeli miyiz?

JSON formatında yanıt:
{{
    "valid": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Açıklama"
}}

SADECE JSON ver.
"""
        
        try:
            response = self.model.generate_content(prompt)
            json_text = response.text.strip()
            if "```" in json_text:
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
            
            data = json.loads(json_text.strip())
            return (
                data.get("valid", False),
                data.get("reasoning", ""),
                float(data.get("confidence", 0.5))
            )
        except Exception as e:
            logger.error(f"Sinyal doğrulama hatası: {e}")
            # Fallback: Basit kontrol
            price_diff = abs(current_price - entry) / entry
            if price_diff > 0.05:  # %5'ten fazla fark
                return (False, "Fiyat girişten çok uzaklaştı", 0.3)
            
            trend_match = (side == "LONG" and "BULLISH" in trend) or \
                          (side == "SHORT" and "BEARISH" in trend)
            
            if trend_match:
                return (True, "Trend uyumlu", 0.6)
            else:
                return (False, "Trend uyumsuz", 0.4)


# Test
def test_gemini():
    """Gemini analizini test et"""
    print("=" * 60)
    print("Gemini AI Analiz Testi")
    print("=" * 60)
    
    # Örnek fiyat verisi oluştur
    import random
    base_price = 42000
    prices = []
    for i in range(100):
        change = random.uniform(-0.01, 0.012)  # Hafif yükseliş eğilimi
        base_price = base_price * (1 + change)
        prices.append(round(base_price, 2))
    
    volumes = [random.uniform(1000, 5000) for _ in range(100)]
    
    analyzer = GeminiAnalyzer()
    
    print("\n1. Teknik Göstergeler:")
    tech = TechnicalIndicators()
    print(f"   RSI: {tech.calculate_rsi(prices)}")
    print(f"   Trend: {tech.calculate_trend(prices)}")
    print(f"   Elliott: {tech.detect_elliott_wave(prices)}")
    print(f"   Volume: {tech.analyze_volume(volumes)}")
    
    print("\n2. Gemini Analizi (BTC):")
    analysis = analyzer.analyze_coin("BTC", prices, volumes)
    print(f"   Öneri: {analysis.recommendation}")
    print(f"   Güven: {analysis.confidence:.0%}")
    print(f"   Giriş: {analysis.entry_price}")
    print(f"   TPs: {analysis.take_profits}")
    print(f"   SL: {analysis.stop_loss}")
    print(f"   Risk: {analysis.risk_level}")
    print(f"   Açıklama: {analysis.reasoning[:200]}...")
    
    print("\n3. Scalper Analizi:")
    scalp = analyzer.scalper_analysis("BTC", prices, volumes)
    print(f"   Öneri: {scalp.recommendation}")
    print(f"   Güven: {scalp.confidence:.0%}")


if __name__ == "__main__":
    test_gemini()


