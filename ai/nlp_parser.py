"""
Natural Language Parser for financial transactions using Gemini Free Tier, OpenAI,
and robust regex multi-item heuristic fallback.
Supports Indonesian and English single and batch conversational inputs.
"""

import re
import json
import logging
from typing import Optional, List, Tuple

from config import settings
from database.models import Category, TransactionType, ParsedAIInput
from ai.gemini_engine import gemini_engine

logger = logging.getLogger(__name__)

NLP_SYSTEM_PROMPT = """
You are an intelligent freelance personal finance assistant.
Your job is to parse conversational income or expense statements into structured JSON.
Languages supported: Indonesian and English (including colloquial terms like '50k', '1.5jt', '200rb', 'dapet transferan', 'beli kopi', 'bayar hosting', 'makan warteg').

Categories:
- "Needs": Basic food, warteg, groceries, rent, utilities, electricity, health, medicine, essential transport, bensin, pulsa.
- "Wants": Dining out, cafe, coffee, entertainment, shopping, gaming, fashion, hobbies.
- "Operational": Freelance tools, SaaS software, cloud hosting, domain, coworking space, hardware, business meals.
- "Investment": Stocks, crypto, mutual funds, gold.
- "Buffer": Emergency savings transfers.

Type:
- "INCOME": Invoices, client payments, salary, project revenue, freelance fees, bonus, dividends, transfer masuk.
- "EXPENSE": Anything purchased, paid for, subscribed, or transferred out.

Rules:
- Parse amounts into pure float values (e.g. "50k" -> 50000.0, "1.5jt" -> 1500000.0, "Rp 250.000" -> 250000.0, "$20" -> 20.0).
- Extract 'source_or_merchant' (e.g. store, client, or vendor name).
- Provide a clear 'notes' summary.

Output ONLY valid JSON matching this schema:
{
  "type": "INCOME|EXPENSE",
  "category": "Needs|Wants|Operational|Investment|Buffer",
  "amount": 0.0,
  "source_or_merchant": "string",
  "notes": "string",
  "confidence": 0.95
}
"""


class NLPParser:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY is not configured.")
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=self.api_key)
        return self._openai_client

    async def parse_text(self, text: str) -> ParsedAIInput:
        """Parse single natural language transaction text with Gemini Free, OpenAI, or regex heuristics."""
        # 1. Try Google Gemini Free AI Engine
        if gemini_engine.is_available:
            try:
                gemini_res = await gemini_engine.parse_text(text)
                if gemini_res and gemini_res.amount > 0:
                    return gemini_res
            except Exception as e:
                logger.warning("Gemini NLP parsing failed: %s", e)

        # 2. Try OpenAI LLM if configured
        if self.api_key:
            try:
                client = self._get_openai_client()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": NLP_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Parse this transaction: \"{text}\""},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=400,
                )

                raw_content = response.choices[0].message.content
                data = json.loads(raw_content)

                tx_type = TransactionType.INCOME if str(data.get("type", "")).upper() == "INCOME" else TransactionType.EXPENSE
                cat_str = str(data.get("category", "Needs")).capitalize()
                category = Category.NEEDS
                for c in Category:
                    if c.value.lower() == cat_str.lower():
                        category = c
                        break

                amount = float(data.get("amount", 0.0))
                if amount <= 0:
                    amount = self._parse_amount_heuristic(text)

                return ParsedAIInput(
                    type=tx_type,
                    category=category,
                    amount=amount,
                    source_or_merchant=str(data.get("source_or_merchant", "Direct Entry")),
                    notes=str(data.get("notes", text)),
                    confidence=float(data.get("confidence", 0.95)),
                )
            except Exception as e:
                logger.warning("OpenAI NLP parsing failed (%s), switching to heuristic regex parser.", e)

        # 3. Fast, 100% Free Heuristic Rule-Based Fallback
        return self.parse_heuristic(text)

    async def parse_multi_text(self, text: str) -> List[ParsedAIInput]:
        """
        Multi-Item Batch Parser:
        Parses text containing multiple comma-separated, newline-separated, or conjunction-separated items.
        Example: "beli buku 30rb, pensil 5rb, makan warteg 20k dan bensin 25rb"
        """
        raw_text = text.strip()
        if not raw_text:
            return []

        # 1. Split candidate segments by newlines, semicolons, commas, or conjunction words
        # e.g. "dan", "terus", "lalu", "serta", "plus", "+"
        segments = []
        # First split by lines or semicolons
        lines = [line.strip() for line in re.split(r"[\n;]+", raw_text) if line.strip()]

        for line in lines:
            # Check if line contains multiple sub-items separated by comma or conjunctions
            # We only split by conjunctions if the line has multiple amount patterns
            amount_matches = len(re.findall(r"\d+\s*(?:jt|juta|mio|k|rb|ribu|thousand|\.000|\d{3,})", line, re.IGNORECASE))
            if amount_matches > 1:
                # Split by comma or conjunctions
                sub_parts = re.split(r",|\s+(?:dan|terus|lalu|serta|plus|\+)\s+", line, flags=re.IGNORECASE)
                for sp in sub_parts:
                    sp_clean = sp.strip()
                    if sp_clean:
                        segments.append(sp_clean)
            else:
                segments.append(line)

        if len(segments) <= 1:
            # Single item fallback
            single = await self.parse_text(raw_text)
            return [single]

        parsed_items: List[ParsedAIInput] = []
        for seg in segments:
            # Only process if segment has some recognizable monetary amount
            amt = self._parse_amount_heuristic(seg)
            if amt > 0:
                parsed_item = self.parse_heuristic(seg)
                parsed_items.append(parsed_item)

        if not parsed_items:
            # Fallback if no individual segments matched amounts
            single = await self.parse_text(raw_text)
            return [single]

        return parsed_items

    @staticmethod
    def _parse_amount_heuristic(text: str) -> float:
        """Extract monetary amounts from text, including k/rb/jt/juta/ribu/rp notations."""
        # 1. Check for foreign currency patterns (USD, EUR, SGD, GBP, JPY, AUD, MYR, CNY, USDT, $, €, £)
        fx_rates = {
            "USD": 16250.0,
            "EUR": 17650.0,
            "SGD": 12250.0,
            "GBP": 20850.0,
            "JPY": 108.5,
            "AUD": 10650.0,
            "MYR": 3550.0,
            "CNY": 2250.0,
            "USDT": 16300.0,
        }

        # Check for dollar sign e.g. $450 or $ 1,500
        dollar_match = re.search(r"\$\s*(\d+(?:[.,]\d+)?)", text)
        if dollar_match:
            raw_val = float(dollar_match.group(1).replace(",", "."))
            return raw_val * fx_rates["USD"]

        # Check for euro sign e.g. €200 or € 350
        euro_match = re.search(r"€\s*(\d+(?:[.,]\d+)?)", text)
        if euro_match:
            raw_val = float(euro_match.group(1).replace(",", "."))
            return raw_val * fx_rates["EUR"]

        # Check for pound sign e.g. £150
        pound_match = re.search(r"£\s*(\d+(?:[.,]\d+)?)", text)
        if pound_match:
            raw_val = float(pound_match.group(1).replace(",", "."))
            return raw_val * fx_rates["GBP"]

        # Check for currency code prefix/suffix e.g. "450 USD", "USD 450", "SGD 1200", "500 USDT"
        # Sort by length descending so "USDT" is matched before "USD"
        sorted_fx = sorted(fx_rates.items(), key=lambda item: len(item[0]), reverse=True)
        for curr_code, rate_val in sorted_fx:
            curr_match = re.search(rf"(?:\b{curr_code}\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*{curr_code}\b)", text, re.IGNORECASE)
            if curr_match:
                val_str = curr_match.group(1) or curr_match.group(2)
                if val_str:
                    raw_val = float(val_str.replace(",", "."))
                    return raw_val * rate_val

        # 2. Check for million patterns: 1.5jt, 10 juta, 2jt, 3.5 jt, etc.
        jt_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:jt|juta|mio|million)", text, re.IGNORECASE)
        if jt_match:
            val_str = jt_match.group(1).replace(",", ".")
            return float(val_str) * 1_000_000.0

        # 3. Check for thousand patterns: 50k, 250rb, 500 ribu, 35.5k
        k_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:k|rb|ribu|thousand)", text, re.IGNORECASE)
        if k_match:
            val_str = k_match.group(1).replace(",", ".")
            return float(val_str) * 1_000.0

        # 4. Check for formatted standard numbers e.g. Rp 10.000.000 or 250000 or 50
        num_match = re.search(r"(?:rp\.?|idr)?\s*(\d{1,3}(?:\.\d{3})+|\d+)", text, re.IGNORECASE)
        if num_match:
            raw_val = num_match.group(1).replace(".", "")
            if raw_val.isdigit() and int(raw_val) > 0:
                return float(raw_val)

        return 0.0

    @staticmethod
    def _parse_indonesian_number(text: str) -> float:
        """Alias for _parse_amount_heuristic."""
        return NLPParser._parse_amount_heuristic(text)

    def parse_heuristic(self, text: str) -> ParsedAIInput:
        """Deterministic rule-based parser for quick execution and 100% offline free testing."""
        text_lower = text.lower()

        # 1. Determine Type
        income_keywords = [
            "masuk", "terima", "dapat", "dapet", "fee", "gaji", "income", "klien", "client",
            "proyek", "project", "invoice", "transferan", "upwork", "fiverr", "cair", "received", "pemasukan"
        ]
        is_income = any(kw in text_lower for kw in income_keywords)
        tx_type = TransactionType.INCOME if is_income else TransactionType.EXPENSE

        # 2. Extract Amount
        amount = self._parse_amount_heuristic(text)
        if amount == 0.0:
            amount = 10000.0  # Safe default

        # 3. Determine Category & Merchant
        category = Category.NEEDS
        merchant = "Direct Input"

        if is_income:
            category = Category.BUFFER
            merchant_patterns = ["upwork", "fiverr", "klien", "client", "pt ", "cv "]
            for kw in merchant_patterns:
                if kw in text_lower:
                    merchant = kw.upper() if len(kw) <= 4 else kw.capitalize()
                    break
        else:
            wants_keywords = [
                "kopi", "coffee", "cafe", "starbucks", "nongkrong", "jajan", "nonton", "cinema",
                "game", "steam", "baju", "liburan", "mixue", "chatime", "janji jiwa", "kenangan",
                "bioskop", "sepatu", "skincare", "netflix", "spotify"
            ]
            operational_keywords = [
                "hosting", "domain", "vps", "server", "aws", "gcp", "chatgpt", "openai", "gemini",
                "figma", "github", "software", "tools", "coworking", "internet", "wifi", "indihome",
                "biznet", "cursor", "adobe", "notion"
            ]
            investment_keywords = [
                "investasi", "saham", "crypto", "bitcoin", "reksadana", "bibit", "ajaib", "gold", "emas", "stock"
            ]

            if any(kw in text_lower for kw in wants_keywords):
                category = Category.WANTS
            elif any(kw in text_lower for kw in operational_keywords):
                category = Category.OPERATIONAL
            elif any(kw in text_lower for kw in investment_keywords):
                category = Category.INVESTMENT
            else:
                category = Category.NEEDS

            # Extract common merchants
            merchant_map = {
                "starbucks": "Starbucks",
                "indomaret": "Indomaret",
                "alfamart": "Alfamart",
                "warteg": "Warteg",
                "gramedia": "Gramedia",
                "pertamina": "Pertamina SPBU",
                "spbu": "SPBU",
                "bensin": "Bensin / SPBU",
                "tokopedia": "Tokopedia",
                "shopee": "Shopee",
                "grab": "Grab",
                "gojek": "Gojek",
                "janji jiwa": "Kopi Janji Jiwa",
                "kenangan": "Kopi Kenangan",
                "mixue": "Mixue",
                "indihome": "Indihome Telkom",
                "biznet": "Biznet",
                "pln": "PLN Listrik",
                "listrik": "PLN Listrik",
                "pulsa": "Pulsa / Paket Data",
                "superindo": "Superindo",
            }
            for kw, m_name in merchant_map.items():
                if kw in text_lower:
                    merchant = m_name
                    break

        return ParsedAIInput(
            type=tx_type,
            category=category,
            amount=amount,
            source_or_merchant=merchant,
            notes=text.strip(),
            confidence=0.85,
        )


nlp_parser = NLPParser()
