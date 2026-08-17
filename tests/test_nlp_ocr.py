"""
Unit tests for AI NLP parsing and OCR fallback schemas.
"""

import pytest
from ai.nlp_parser import NLPParser
from ai.ocr_vision import OCRVisionEngine
from database.models import TransactionType, Category


@pytest.mark.asyncio
async def test_nlp_heuristic_parsing():
    parser = NLPParser(api_key=None)  # Uses heuristic parser

    # Test Income parsing
    res1 = parser.parse_heuristic("Masuk fee klien project web Rp5.000.000")
    assert res1.type == TransactionType.INCOME
    assert res1.amount == 5_000_000.0

    res2 = parser.parse_heuristic("Fee upwork cair 1.5jt")
    assert res2.type == TransactionType.INCOME
    assert res2.amount == 1_500_000.0
    assert res2.source_or_merchant == "Upwork"

    res3 = parser.parse_heuristic("Dapat transferan gaji 12jt")
    assert res3.type == TransactionType.INCOME
    assert res3.amount == 12_000_000.0

    # Test Expense parsing
    res4 = parser.parse_heuristic("Beli kopi starbucks 45rb")
    assert res4.type == TransactionType.EXPENSE
    assert res4.category == Category.WANTS
    assert res4.amount == 45_000.0
    assert res4.source_or_merchant == "Starbucks"

    res5 = parser.parse_heuristic("Bayar sewa vps hosting $50")
    assert res5.type == TransactionType.EXPENSE
    assert res5.category == Category.OPERATIONAL
    assert res5.amount == 50.0 * 16250.0

    res6 = parser.parse_heuristic("Investasi reksadana bibit 500k")
    assert res6.type == TransactionType.EXPENSE
    assert res6.category == Category.INVESTMENT
    assert res6.amount == 500_000.0


@pytest.mark.asyncio
async def test_ocr_mock_fallback():
    engine = OCRVisionEngine(api_key=None)
    res = await engine.extract_receipt(b"fake_image_bytes")
    assert res.type == TransactionType.EXPENSE
    assert res.amount > 0
    assert res.source_or_merchant is not None
