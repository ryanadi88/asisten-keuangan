"""
Google Gemini Free Tier Engine for Vision OCR, Voice Audio Transcription, and NLP.
Utilizes the official Google Gemini API (Free tier from Google AI Studio).
"""

import os
import re
import json
import base64
import logging
from typing import Optional, List, Dict, Any

import httpx

from config import settings
from database.models import Category, TransactionType, ParsedAIInput

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _clean_json_payload(raw: str) -> Optional[Dict[str, Any]]:
    """Clean markdown code fences, comments, or trailing commas from Gemini JSON responses."""
    if not raw:
        return None
    cleaned = raw.strip()
    # Strip markdown fences
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    # Extract outermost JSON object if surrounded by extra text
    json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(1).strip()

    try:
        return json.loads(cleaned)
    except Exception:
        # Try fixing single quotes or common syntax slips
        try:
            fixed = re.sub(r"'\s*:\s*", '": ', cleaned)
            fixed = re.sub(r",\s*([\}\]])", r"\1", fixed)
            return json.loads(fixed)
        except Exception as e:
            logger.warning("Failed to deserialize Gemini JSON: %s (raw: %s)", e, raw[:100])
            return None

GEMINI_SYSTEM_PROMPT = """
You are an intelligent freelance personal finance assistant.
Your task is to parse conversational income/expense text or receipt images into structured financial JSON.
Languages: Indonesian and English (including slang like '50k', '1.5jt', '200rb', 'warteg', 'dapet transferan').

Categories:
- "Needs": Basic food, groceries, warteg, rent, electricity, health, essential transport.
- "Wants": Dining out, cafe, coffee, starbucks, entertainment, shopping, fashion, hobbies.
- "Operational": Freelance tools, SaaS software, cloud hosting, domain, coworking space, hardware, business meals.
- "Investment": Stocks, crypto, mutual funds, gold.
- "Buffer": Emergency savings transfers.

Type:
- "INCOME": Invoices, client payments, salary, project revenue, freelance fees, bonus, transfer masuk.
- "EXPENSE": Purchases, food, bills, subscriptions, paid transfers.

Output JSON format strictly:
{
  "type": "INCOME" or "EXPENSE",
  "category": "Needs" or "Wants" or "Operational" or "Investment" or "Buffer",
  "amount": 0.0,
  "source_or_merchant": "string",
  "notes": "string",
  "confidence": 0.95
}
"""


class GeminiEngine:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model if model is not None else settings.GEMINI_MODEL

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def generate_content(
        self,
        parts: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        response_json: bool = False,
    ) -> Optional[str]:
        """Send asynchronous request to Google Gemini REST API with resilient fallback across models."""
        if not self.is_available:
            return None

        # Detect input modality
        has_image = any("inlineData" in p and p["inlineData"].get("mimeType", "").startswith("image/") for p in parts)
        has_audio = any("inlineData" in p and p["inlineData"].get("mimeType", "").startswith("audio/") for p in parts)

        if has_image:
            candidate_models = ["gemini-3-flash-preview", self.model, "gemini-2.5-flash", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]
        elif has_audio:
            candidate_models = ["gemini-3-flash-preview", self.model, "gemini-2.5-flash", "gemini-3.1-flash-lite-preview"]
        else:
            candidate_models = ["gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", self.model, "gemini-3.5-flash", "gemini-2.5-flash"]

        # deduplicate while preserving order
        unique_models = []
        for m in candidate_models:
            if m and m not in unique_models:
                unique_models.append(m)

        payload: Dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 800,
            },
        }

        if response_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        for model_name in unique_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in [429, 404, 503]:
                        logger.warning("Gemini model %s returned HTTP %s, trying fallback...", model_name, resp.status_code)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        first = candidates[0]
                        content = first.get("content", {})
                        parts_out = content.get("parts", [])
                        if parts_out:
                            return parts_out[0].get("text", "")
            except Exception as e:
                logger.warning("Google Gemini API request failed on model %s: %s", model_name, e)
                continue

        return None

    async def parse_text(self, text: str) -> Optional[ParsedAIInput]:
        """Parse natural language transaction using Gemini."""
        if not self.is_available:
            return None

        parts = [{"text": f"Parse this financial transaction into JSON: \"{text}\""}]
        raw = await self.generate_content(
            parts=parts,
            system_instruction=GEMINI_SYSTEM_PROMPT,
            response_json=True,
        )

        data = _clean_json_payload(raw)
        if not data:
            return None

        try:
            tx_type = TransactionType.INCOME if str(data.get("type", "")).upper() == "INCOME" else TransactionType.EXPENSE
            cat_str = str(data.get("category", "Needs")).capitalize()
            category = Category.NEEDS
            for c in Category:
                if c.value.lower() == cat_str.lower():
                    category = c
                    break

            return ParsedAIInput(
                type=tx_type,
                category=category,
                amount=float(data.get("amount", 0.0)),
                source_or_merchant=str(data.get("source_or_merchant", "Direct Input")),
                notes=str(data.get("notes", text)),
                confidence=float(data.get("confidence", 0.95)),
            )
        except Exception as e:
            logger.warning("Failed to deserialize Gemini JSON: %s", e)
            return None

    async def parse_receipt_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> Optional[ParsedAIInput]:
        """Extract merchant, total amount, category, and items from receipt photo."""
        if not self.is_available:
            return None

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        parts = [
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": b64_data,
                }
            },
            {
                "text": (
                    "Extract the store name/merchant, total transaction amount (numeric float only), "
                    "category (Needs, Wants, or Operational), and a summary note of items purchased from this receipt."
                )
            },
        ]

        raw = await self.generate_content(
            parts=parts,
            system_instruction=GEMINI_SYSTEM_PROMPT,
            response_json=True,
        )

        if not raw:
            return None

        data = _clean_json_payload(raw)
        if not data:
            return None

        try:
            cat_str = str(data.get("category", "Needs")).capitalize()
            category = Category.NEEDS
            for c in Category:
                if c.value.lower() == cat_str.lower():
                    category = c
                    break

            items = data.get("items")
            if isinstance(items, list):
                items = [str(it) for it in items]
            else:
                items = []

            return ParsedAIInput(
                type=TransactionType.EXPENSE,
                category=category,
                amount=float(data.get("amount", 0.0)),
                source_or_merchant=str(data.get("source_or_merchant", "Store Receipt")),
                notes=str(data.get("notes", "Receipt Scan")),
                items=items,
                date=data.get("date"),
                confidence=float(data.get("confidence", 0.95)),
            )
        except Exception as e:
            logger.warning("Failed to parse Gemini OCR receipt JSON: %s", e)
            return None

    async def transcribe_voice(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
        """Transcribe voice note audio (Telegram .ogg/.oga voice message) to Indonesian text."""
        if not self.is_available:
            return None

        b64_data = base64.b64encode(audio_bytes).decode("utf-8")
        parts = [
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": b64_data,
                }
            },
            {
                "text": "Transcribe the spoken Indonesian or English words in this audio voice message accurately. Return ONLY the transcribed text without extra commentary."
            },
        ]

        result = await self.generate_content(
            parts=parts,
            system_instruction="You are a high-accuracy voice transcription engine.",
            response_json=False,
        )
        return result.strip() if result else None

    async def ask_financial_advisor(
        self,
        context_data: Dict[str, Any],
        user_question: str,
    ) -> str:
        """Consult Gemini AI Financial Advisor using real user balance and budget context."""
        if not self.is_available:
            return (
                "🤖 *AI Financial Advisor Siap Digunakan!*\n\n"
                "Untuk mengaktifkan konsultasi finansial pintar via Google Gemini gratis, "
                "masukkan `GEMINI_API_KEY` pada file `.env`!"
            )

        advisor_prompt = f"""
Anda adalah Penasihat Keuangan Freelance Profesional Indonesia (Freelance Financial Coach).
Berikan saran finansial yang bijak, realistis, objektif, dan suportif berdasarkan data keuangan riil pengguna berikut:

📊 DATA KEUANGAN PENGGUNA SAAT INI:
- Bulan: {context_data.get('month_year')}
- Mata Uang: {context_data.get('currency', 'IDR')}
- Total Pemasukan Bulan Ini: {context_data.get('total_income')}
- Total Pengeluaran Bulan Ini: {context_data.get('total_expense')}
- Buffer Runway Dana Darurat: {context_data.get('buffer_runway_months')} Bulan Biaya Hidup
- Total Saldo Buffer: {context_data.get('buffer_fund_balance')}
- Batas Anggaran Needs (Kebutuhan Pokok): Terpakai {context_data.get('needs_spent')} dari limit {context_data.get('needs_budget')}
- Batas Anggaran Wants (Keinginan/Hiburan): Terpakai {context_data.get('wants_spent')} dari limit {context_data.get('wants_budget')}
- Target Gaji Bulanan: {context_data.get('target_salary')} (Tercapai: {context_data.get('actual_salary_drawn')})
- Target Impian / Wishlist Aktif: {context_data.get('active_goals_summary')}
- Langganan Rutin Bulanan: {context_data.get('subscriptions_summary')}

PERTANYAAN PENGGUNA:
"{user_question}"

INSTRUKSI JAWABAN:
1. Berikan jawaban dalam Bahasa Indonesia yang ramah, profesional, dan to the point.
2. Evaluasi apakah keputusan keuangan/pembelian tersebut aman berdasarkan sisa kuota Wants, Runway Buffer, dan Target Goal yang sedang berjalan.
3. Berikan rekomendasi langkah konkret (misal: "Aman dibeli sekarang", "Tunda sampai fee cair", atau "Gunakan sistem cicilan tabungan target").
4. Gunakan format Telegram Markdown yang rapi (bullet points, emoji, bold text).
"""

        parts = [{"text": advisor_prompt}]
        response = await self.generate_content(
            parts=parts,
            system_instruction="Anda adalah konsultan keuangan freelance Indonesia yang ahli dan ramah.",
            response_json=False,
        )

        if response:
            return response.strip()
        return "⚠️ Maaf, AI Advisor sedang sibuk. Silakan coba ajukan pertanyaan Anda kembali sesaat lagi."


gemini_engine = GeminiEngine()

