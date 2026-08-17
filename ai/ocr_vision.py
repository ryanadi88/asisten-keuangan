"""
Vision OCR Engine for receipt and invoice processing.
Supports Google Gemini Free Tier, OpenAI Vision, and deterministic fallback.
Extracts merchant name, total amount, transaction date, line items, and best-fit category.
"""

import os
import base64
import json
import logging
from typing import Optional, Union
from pathlib import Path

from config import settings
from database.models import Category, TransactionType, ParsedAIInput
from ai.gemini_engine import gemini_engine

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """
You are an expert financial receipt OCR engine and accountant.
Analyze the provided receipt/invoice image and extract transaction details into structured JSON.

Rules:
1. 'merchant_name': Name of store, vendor, freelancer platform, or client.
2. 'total_amount': The final total payable amount as a float number (exclude currency symbols, dots, commas).
3. 'date': Transaction date in ISO format YYYY-MM-DD if visible, or null.
4. 'category': Must be strictly one of:
   - "Needs": Groceries, basic food, utilities, health, rent, transportation.
   - "Wants": Cafe, restaurant dining out, entertainment, shopping, leisure, games.
   - "Operational": Work tools, software SaaS, cloud hosting, coworking, business equipment, client meetings.
   - "Investment": Stock, crypto, mutual funds, gold.
   - "Buffer": Emergency savings transfers.
5. 'type': Usually "EXPENSE" for receipts/bills. If it is a client invoice paid to the user, mark as "INCOME".
6. 'items': List of top extracted item lines.
7. 'notes': Brief 1-line description of the purchase.
8. 'confidence': Float between 0.0 and 1.0 reflecting OCR clarity.

Output ONLY valid JSON matching this schema:
{
  "merchant_name": "string",
  "total_amount": 0.0,
  "date": "YYYY-MM-DD or null",
  "category": "Needs|Wants|Operational|Investment|Buffer",
  "type": "EXPENSE|INCOME",
  "items": ["item 1", "item 2"],
  "notes": "string",
  "confidence": 0.95
}
"""


class OCRVisionEngine:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY is not configured in environment or settings.")
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=self.api_key)
        return self._openai_client

    @staticmethod
    def encode_image_bytes(image_input: Union[str, bytes, bytearray, memoryview, Path]) -> bytes:
        """Convert image input to raw bytes."""
        if isinstance(image_input, (str, Path)):
            with open(image_input, "rb") as f:
                return f.read()
        elif isinstance(image_input, (bytes, bytearray, memoryview)):
            return bytes(image_input)
        else:
            raise ValueError("Unsupported image input type.")

    async def extract_receipt(self, image_input: Union[str, bytes, Path]) -> ParsedAIInput:
        """Process receipt image using Google Gemini Free Tier, OpenAI Vision, or mock fallback."""
        raw_bytes = self.encode_image_bytes(image_input)

        # 1. Try Google Gemini Free AI Engine
        if gemini_engine.is_available:
            try:
                gemini_res = await gemini_engine.parse_receipt_image(raw_bytes)
                if gemini_res and gemini_res.amount > 0:
                    return gemini_res
            except Exception as e:
                logger.warning("Gemini Vision OCR failed: %s", e)

        # 2. Try OpenAI Vision if configured
        if self.api_key:
            try:
                client = self._get_openai_client()
                b64_image = base64.b64encode(raw_bytes).decode("utf-8")

                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": VISION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Extract all financial receipt details from this image accurately.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64_image}",
                                        "detail": "high",
                                    },
                                },
                            ],
                        },
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=600,
                )

                raw_content = response.choices[0].message.content
                data = json.loads(raw_content)

                cat_str = str(data.get("category", "Needs")).capitalize()
                category = Category.NEEDS
                for c in Category:
                    if c.value.lower() == cat_str.lower():
                        category = c
                        break

                tx_type = TransactionType.INCOME if str(data.get("type", "")).upper() == "INCOME" else TransactionType.EXPENSE

                return ParsedAIInput(
                    type=tx_type,
                    category=category,
                    amount=float(data.get("total_amount", 0.0)),
                    source_or_merchant=str(data.get("merchant_name", "Unknown Merchant")),
                    date=data.get("date"),
                    items=data.get("items", []),
                    notes=data.get("notes", ""),
                    confidence=float(data.get("confidence", 0.9)),
                )

            except Exception as e:
                logger.error("Error running OpenAI Vision OCR: %s", e, exc_info=True)

        return self._mock_ocr_fallback()

    def _mock_ocr_fallback(self, error_note: Optional[str] = None) -> ParsedAIInput:
        """Safe fallback for offline/test mode."""
        return ParsedAIInput(
            type=TransactionType.EXPENSE,
            category=Category.NEEDS,
            amount=50000.0,
            source_or_merchant="Sample Store (Receipt OCR)",
            items=["Struk Belanja"],
            notes=f"OCR Struk Belanja {f'({error_note})' if error_note else ''}".strip(),
            confidence=0.6,
        )


ocr_engine = OCRVisionEngine()
