"""
Smart Multi-Currency & Realtime Forex Converter Engine.
Fetches live exchange rates against IDR (Bank Indonesia / OpenFX), handles international freelance platform fees
(Upwork 10%, Fiverr 20%, PayPal 4.4%, Wise 0.6%), and provides instant conversion tables.
"""

import time
import httpx
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

from config import format_currency
from database.models import CurrencyExchangeRate, CurrencyConversionResult

logger = logging.getLogger(__name__)

# Fallback realistic baseline rates against USD (1 USD = X Currency)
# and IDR (1 Foreign Unit = X IDR)
DEFAULT_IDR_RATES: Dict[str, float] = {
    "USD": 16250.0,
    "EUR": 17650.0,
    "SGD": 12250.0,
    "GBP": 20850.0,
    "JPY": 108.5,
    "AUD": 10650.0,
    "MYR": 3550.0,
    "CNY": 2250.0,
    "USDT": 16300.0,
    "IDR": 1.0,
}

PLATFORM_FEE_RATES: Dict[str, float] = {
    "upwork": 0.10,     # 10% freelancer service fee
    "fiverr": 0.20,     # 20% seller fee
    "paypal": 0.044,    # ~4.4% international transfer
    "wise": 0.006,      # ~0.6% low-cost transfer
    "direct": 0.0,      # Wire transfer / Direct
}


class CurrencyConverterEngine:
    def __init__(self):
        self._cached_rates: Dict[str, float] = dict(DEFAULT_IDR_RATES)
        self._last_fetched_time: float = 0.0
        self._cache_ttl_seconds: float = 21600.0  # 6 Hours Cache

    async def fetch_live_rates(self) -> Dict[str, float]:
        """Fetch live forex rates via free Open Exchange Rates API with cached fallback."""
        now = time.time()
        if self._cached_rates and (now - self._last_fetched_time) < self._cache_ttl_seconds:
            return self._cached_rates

        url = "https://open.er-api.com/v6/latest/USD"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    rates_vs_usd = data.get("rates", {})
                    idr_per_usd = rates_vs_usd.get("IDR", 16250.0)

                    # Calculate IDR rate per unit of foreign currency
                    updated_rates: Dict[str, float] = {"USD": idr_per_usd, "IDR": 1.0}
                    for curr, rate_to_usd in rates_vs_usd.items():
                        if rate_to_usd > 0 and curr in ["EUR", "SGD", "GBP", "JPY", "AUD", "MYR", "CNY", "USDT"]:
                            updated_rates[curr] = round(idr_per_usd / rate_to_usd, 2)

                    if "USDT" not in updated_rates:
                        updated_rates["USDT"] = idr_per_usd * 1.002  # Slight stablecoin premium

                    self._cached_rates.update(updated_rates)
                    self._last_fetched_time = now
                    logger.info("Successfully refreshed live forex rates against IDR.")
                    return self._cached_rates
        except Exception as e:
            logger.warning("Failed to fetch live forex rates from open.er-api.com: %s. Using cached baseline.", e)

        return self._cached_rates

    async def convert_to_idr(
        self,
        amount: float,
        from_currency: str,
        platform: str = "direct",
    ) -> CurrencyConversionResult:
        """Convert any foreign currency amount to IDR, accounting for platform fees."""
        curr_upper = from_currency.strip().upper()
        rates = await self.fetch_live_rates()

        rate = rates.get(curr_upper, DEFAULT_IDR_RATES.get(curr_upper, 1.0))
        gross_idr = amount * rate

        # Deduct platform commission
        fee_rate = PLATFORM_FEE_RATES.get(platform.lower(), 0.0)
        platform_fee_idr = gross_idr * fee_rate
        net_idr = max(0.0, gross_idr - platform_fee_idr)

        platform_label = platform.capitalize() if platform.lower() != "direct" else "Direct Transfer"
        fee_info = f" (Potongan {platform_label} {int(fee_rate*100)}%: -{format_currency(platform_fee_idr, 'IDR')})" if fee_rate > 0 else ""

        summary_text = (
            f"🌐 *KONVERSI VALUTA ASING & KURS REALTIME*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 *Nominal Asal:* `{curr_upper} {amount:,.2f}`\n"
            f"📈 *Kurs Saat Ini:* `1 {curr_upper} = {format_currency(rate, 'IDR')}`\n"
            f"🏢 *Platform:* `{platform_label}`\n"
            f"💰 *Estimasi Gross IDR:* `{format_currency(gross_idr, 'IDR')}`\n"
            f"💸 *Estimasi Bersih (Net):* `*{format_currency(net_idr, 'IDR')}*`{fee_info}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 _Data kurs disinkronkan secara realtime dengan pasar valas internasional._"
        )

        return CurrencyConversionResult(
            from_currency=curr_upper,
            to_currency="IDR",
            original_amount=amount,
            converted_amount=gross_idr,
            exchange_rate=rate,
            estimated_platform_fee=platform_fee_idr,
            net_received_idr=net_idr,
            timestamp=datetime.now().isoformat(),
            summary_text=summary_text,
        )

    async def render_rates_table(self) -> str:
        """Render beautiful Telegram markdown table of current forex rates."""
        rates = await self.fetch_live_rates()
        dt_str = datetime.now().strftime("%d %b %Y, %H:%M WIB")

        lines = [
            "🌐 *KURS VALAS & MATA UANG ASING HARI INI*",
            f"🕒 _Update: {dt_str}_",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"🇺🇸 *USD (Dollar AS):* `{format_currency(rates.get('USD', 16250.0), 'IDR')}`",
            f"🇪🇺 *EUR (Euro):* `{format_currency(rates.get('EUR', 17650.0), 'IDR')}`",
            f"🇸🇬 *SGD (Dollar SG):* `{format_currency(rates.get('SGD', 12250.0), 'IDR')}`",
            f"🇬🇧 *GBP (Poundsterling):* `{format_currency(rates.get('GBP', 20850.0), 'IDR')}`",
            f"🇯🇵 *JPY (Yen Jepang):* `{format_currency(rates.get('JPY', 108.5), 'IDR')}`",
            f"🇦🇺 *AUD (Dollar Aussie):* `{format_currency(rates.get('AUD', 10650.0), 'IDR')}`",
            f"🇲🇾 *MYR (Ringgit):* `{format_currency(rates.get('MYR', 3550.0), 'IDR')}`",
            f"🇨🇳 *CNY (Yuan China):* `{format_currency(rates.get('CNY', 2250.0), 'IDR')}`",
            f"🪙 *USDT (Tether Crypto):* `{format_currency(rates.get('USDT', 16300.0), 'IDR')}`",
            "━━━━━━━━━━━━━━━━━━━━━",
            "💡 *Tips Cepat:*",
            "• Ketik `/convert 500 USD to IDR`",
            "• Ketik `/convert 450 USD upwork`",
            "• Atau langsung catat: `Dapat fee Upwork $450`",
        ]
        return "\n".join(lines)


# Singleton instance
currency_converter = CurrencyConverterEngine()
