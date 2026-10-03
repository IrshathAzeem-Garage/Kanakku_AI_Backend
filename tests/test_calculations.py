import pytest
from app.services.calculation_service import calculate_record_totals, parse_expense_text


def test_calculation_case_1():
    """
    Test 1:
    Customer = 10000
    Digital = 3000
    Expense cashbox = 2000
    Expected:
    Cash = 7000
    In-hand = 5000
    """
    customer_amounts = [10000.0]
    digital_amounts = [3000.0]
    expenses = [
        {"description": "Shop cost", "total_amount": 2000.0, "own_amount": 0.0, "cash_box_amount": 2000.0}
    ]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 10000.0
    assert totals["total_digital_money"] == 3000.0
    assert totals["total_cash_received"] == 7000.0
    assert totals["total_expenses"] == 2000.0
    assert totals["total_own_money"] == 0.0
    assert totals["total_cash_box_expenses"] == 2000.0
    assert totals["in_hand_money"] == 5000.0


def test_calculation_case_2():
    """
    Test 2:
    Customer = 10000
    Digital = 3000
    Expense = 5000 own
    Expected:
    Cash = 7000
    In-hand = 7000 (Own money does NOT reduce in-hand money)
    """
    customer_amounts = [10000.0]
    digital_amounts = [3000.0]
    expenses = [
        {"description": "Aachi Masala", "total_amount": 5000.0, "own_amount": 5000.0, "cash_box_amount": 0.0}
    ]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 10000.0
    assert totals["total_digital_money"] == 3000.0
    assert totals["total_cash_received"] == 7000.0
    assert totals["total_expenses"] == 5000.0
    assert totals["total_own_money"] == 5000.0
    assert totals["total_cash_box_expenses"] == 0.0
    assert totals["in_hand_money"] == 7000.0


def test_calculation_case_3():
    """
    Test 3:
    Customer = 10000
    Digital = 3000
    Expense = 10572
    Own = 10000
    CashBox = 572
    Expected:
    Cash = 7000
    In-hand = 6428
    """
    customer_amounts = [10000.0]
    digital_amounts = [3000.0]
    expenses = [
        {"description": "Supplier", "total_amount": 10572.0, "own_amount": 10000.0, "cash_box_amount": 572.0}
    ]

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 10000.0
    assert totals["total_digital_money"] == 3000.0
    assert totals["total_cash_received"] == 7000.0
    assert totals["total_expenses"] == 10572.0
    assert totals["total_own_money"] == 10000.0
    assert totals["total_cash_box_expenses"] == 572.0
    assert totals["in_hand_money"] == 6428.0


def test_digital_never_added_to_customer_money_duplicate_rule():
    """
    Test 4:
    Digital references must never be added again to customer money.
    If Customer = 10000 and Digital = 3000:
    Customer total must stay 10000 (NOT 13000).
    Cash received must be 7000.
    """
    customer_amounts = [2000.0, 5000.0, 3000.0]  # Sum = 10000
    digital_amounts = [1000.0, 2000.0]  # Sum = 3000
    expenses = []

    totals = calculate_record_totals(customer_amounts, digital_amounts, expenses)

    assert totals["total_customer_money"] == 10000.0
    assert totals["total_digital_money"] == 3000.0
    assert totals["total_cash_received"] == 7000.0
    assert totals["in_hand_money"] == 7000.0


def test_mixed_expense_parsing():
    """
    Test 5:
    Mixed expense text parsing:
    '10000 own + 572' or '10000 (own) + 572'
    must become:
    total = 10572
    own = 10000
    cash_box = 572
    """
    p1 = parse_expense_text("10000 own + 572")
    assert p1["total_amount"] == 10572.0
    assert p1["own_amount"] == 10000.0
    assert p1["cash_box_amount"] == 572.0

    p2 = parse_expense_text("10000 (own) + 572 cash")
    assert p2["total_amount"] == 10572.0
    assert p2["own_amount"] == 10000.0
    assert p2["cash_box_amount"] == 572.0

    p3 = parse_expense_text("Aachi 5000 (own)")
    assert p3["total_amount"] == 5000.0
    assert p3["own_amount"] == 5000.0
    assert p3["cash_box_amount"] == 0.0

    p4 = parse_expense_text("Cartage 350")
    assert p4["total_amount"] == 350.0
    assert p4["own_amount"] == 0.0
    assert p4["cash_box_amount"] == 350.0
