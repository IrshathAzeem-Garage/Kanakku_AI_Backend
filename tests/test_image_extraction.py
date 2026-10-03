import os
import hashlib
import io
import pytest
from PIL import Image, ImageDraw

from app.services.calculation_service import calculate_record_totals, parse_expense_text
from app.services.ai_service import (
    validate_amount_in_raw_text,
    analyze_kanakku_image,
    parse_date_string
)


def create_test_image(text_lines: list, filename: str) -> str:
    """Helper to generate a synthetic test ledger image."""
    img = Image.new("RGB", (600, 800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    y = 30
    for line in text_lines:
        draw.text((40, y), line, fill=(0, 0, 0))
        y += 35
        
    os.makedirs("test_scratch", exist_ok=True)
    file_path = os.path.join("test_scratch", filename)
    img.save(file_path, "JPEG")
    return file_path


def test_image_hash_validation():
    """
    Requirement 8:
    Verify that different images produce different SHA-256 hashes,
    and identical images produce the identical hash.
    """
    img1_path = create_test_image(["Ledger Sheet A", "Customer: 500"], "test_ledger_a.jpg")
    img2_path = create_test_image(["Ledger Sheet B", "Customer: 1500"], "test_ledger_b.jpg")

    with open(img1_path, "rb") as f:
        hash1 = hashlib.sha256(f.read()).hexdigest()

    with open(img2_path, "rb") as f:
        hash2 = hashlib.sha256(f.read()).hexdigest()

    # Re-reading image 1 must match hash1
    with open(img1_path, "rb") as f:
        hash1_repeat = hashlib.sha256(f.read()).hexdigest()

    assert hash1 == hash1_repeat
    assert hash1 != hash2, "Different images MUST produce different SHA-256 hashes"


def test_unconfigured_or_unreadable_image_never_hallucinates():
    """
    Requirement 1, 2, 21:
    When no API key is configured or image is unreadable:
    - AI must NEVER invent mock numbers (like 2000, 5500, 1250, 3000)
    - Returns empty lists and uncertain_entries
    - All totals must be exactly 0.0
    """
    blank_img_path = create_test_image([], "blank_slip.jpg")
    with open(blank_img_path, "rb") as f:
        img_hash = hashlib.sha256(f.read()).hexdigest()

    result = analyze_kanakku_image(
        image_path=blank_img_path,
        image_url="/uploads/blank_slip.jpg",
        image_hash=img_hash,
        request_id="req-test-blank",
        image_id="img-test-blank"
    )

    # Critical assertions: zero invented values
    assert len(result.customer_money) == 0
    assert len(result.digital_entries) == 0
    assert len(result.expenses) == 0
    assert result.total_customer_money == 0.0
    assert result.total_digital_money == 0.0
    assert result.total_cash_received == 0.0
    assert result.total_expenses == 0.0
    assert result.total_own_money == 0.0
    assert result.total_cash_box_expenses == 0.0
    assert result.in_hand_money == 0.0
    assert len(result.uncertain_entries) > 0
    assert result.request_id == "req-test-blank"
    assert result.image_id == "img-test-blank"


def test_known_ledger_case_1():
    """
    Requirement 22 — Test 1:
    Customer: 500, 200
    Digital: PP - 500
    Expense: 1000 own
    
    Expected:
    Customer = 700
    Digital = 500
    Cash = 200
    Expense = 1000
    Own = 1000
    Cash Box = 0
    In Hand = 200
    """
    customer_amounts = [500.0, 200.0]
    digital_amounts = [500.0]
    
    exp_parsed = parse_expense_text("1000 own")
    expenses = [exp_parsed]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 700.0
    assert totals["total_digital_money"] == 500.0
    assert totals["total_cash_received"] == 200.0
    assert totals["total_expenses"] == 1000.0
    assert totals["total_own_money"] == 1000.0
    assert totals["total_cash_box_expenses"] == 0.0
    assert totals["in_hand_money"] == 200.0


def test_known_ledger_case_2():
    """
    Requirement 22 — Test 2:
    Customer: 1000, 500
    Digital: GPay - 500
    Expense: 10000 own + 572
    
    Expected:
    Customer = 1500
    Digital = 500
    Cash = 1000
    Expense = 10572
    Own = 10000
    Cash Box = 572
    In Hand = 428
    """
    customer_amounts = [1000.0, 500.0]
    digital_amounts = [500.0]
    
    exp_parsed = parse_expense_text("Dealer 10000 own + 572")
    expenses = [exp_parsed]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 1500.0
    assert totals["total_digital_money"] == 500.0
    assert totals["total_cash_received"] == 1000.0
    assert totals["total_expenses"] == 10572.0
    assert totals["total_own_money"] == 10000.0
    assert totals["total_cash_box_expenses"] == 572.0
    assert totals["in_hand_money"] == 428.0


def test_known_ledger_case_3():
    """
    Requirement 22 — Test 3:
    Customer: 120, 350, 780
    Digital: PP - 400
    Expense: Aachi - 2,350
    
    Expected:
    Customer = 1250
    Digital = 400
    Cash = 850
    Expense = 2350
    Own = 0
    Cash Box = 2350
    In Hand = 850 - 2350 = -1500
    """
    customer_amounts = [120.0, 350.0, 780.0]
    digital_amounts = [400.0]
    
    exp_parsed = parse_expense_text("Aachi - 2,350")
    expenses = [exp_parsed]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 1250.0
    assert totals["total_digital_money"] == 400.0
    assert totals["total_cash_received"] == 850.0
    assert totals["total_expenses"] == 2350.0
    assert totals["total_own_money"] == 0.0
    assert totals["total_cash_box_expenses"] == 2350.0
    assert totals["in_hand_money"] == -1500.0


def test_known_ledger_case_4_blank_image():
    """
    Requirement 22 — Test 4:
    Blank / Unreadable image:
    Expected:
    Customer = 0, Digital = 0, Cash = 0, Expense = 0, Own = 0, Cash Box = 0, In Hand = 0
    """
    totals = calculate_record_totals([], [], [])
    assert totals["total_customer_money"] == 0.0
    assert totals["total_digital_money"] == 0.0
    assert totals["total_cash_received"] == 0.0
    assert totals["total_expenses"] == 0.0
    assert totals["total_own_money"] == 0.0
    assert totals["total_cash_box_expenses"] == 0.0
    assert totals["in_hand_money"] == 0.0


def test_known_ledger_case_5():
    """
    Requirement 22 — Test 5:
    Customer: 250, 600, 150
    Digital: (none)
    Expense: 500 own + 100
    
    Expected:
    Customer = 1000
    Digital = 0
    Cash = 1000
    Expense = 600
    Own = 500
    Cash Box = 100
    In Hand = 900
    """
    customer_amounts = [250.0, 600.0, 150.0]
    digital_amounts = []
    
    exp_parsed = parse_expense_text("Supplier 500 own + 100 cash")
    expenses = [exp_parsed]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 1000.0
    assert totals["total_digital_money"] == 0.0
    assert totals["total_cash_received"] == 1000.0
    assert totals["total_expenses"] == 600.0
    assert totals["total_own_money"] == 500.0
    assert totals["total_cash_box_expenses"] == 100.0
    assert totals["in_hand_money"] == 900.0


def test_validation_flags_hallucinated_amounts():
    """
    Requirement 15:
    If AI returns an amount (e.g. 8732) that has no corresponding readable text/evidence,
    flag it as suspicious.
    """
    # 1. Valid matching pairs
    assert validate_amount_in_raw_text(500.0, "PP - 500") is True
    assert validate_amount_in_raw_text(1250.0, "Vijay - 1,250") is True
    assert validate_amount_in_raw_text(2350.0, "Aachi - 2,350") is True
    assert validate_amount_in_raw_text(95.0, "Sakthi Traders - 95") is True

    # 2. Fabricated / hallucinated amounts that do not exist in the raw text
    assert validate_amount_in_raw_text(8732.0, "PP - 500") is False
    assert validate_amount_in_raw_text(9999.0, "Ravi 120") is False
    assert validate_amount_in_raw_text(5000.0, "Unclear smudge") is False
    assert validate_amount_in_raw_text(100.0, "") is False


def test_parse_date_string():
    """
    Requirement 10:
    Date must only be extracted if valid. If unreadable, return None.
    Do NOT invent today's date.
    """
    from datetime import date
    assert parse_date_string("2026-10-03") == date(2026, 10, 3)
    assert parse_date_string("03/10/2026") == date(2026, 10, 3)
    assert parse_date_string("03-10-2026") == date(2026, 10, 3)
    assert parse_date_string(None) is None
    assert parse_date_string("") is None
    assert parse_date_string("unreadable") is None
