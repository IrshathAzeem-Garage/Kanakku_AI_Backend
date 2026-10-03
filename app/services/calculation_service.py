from typing import List, Dict, Any, Tuple
import re


def parse_expense_text(text: str, default_description: str = "Expense") -> Dict[str, Any]:
    """
    Parses handwritten/OCR expense text patterns:
    - Normal: "5000", "Aachi 5000", "Dealer 3500"
    - Own: "5000 (own)", "Aachi 2000 (own)", "5000 own"
    - Mixed: "10000 (own) + 572", "Supplier 10000 own + 572 cash", "10000(own)+572"
    """
    # Strip formatting commas between digits (e.g. 2,350 -> 2350, 10,000 -> 10000)
    clean_text = re.sub(r'(?<=\d),(?=\d)', '', text.strip())
    
    # 1. Check for mixed pattern: e.g. 10000 (own) + 572 (cash)
    mixed_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:\(?\s*own\s*\)?)\s*\+\s*(\d+(?:\.\d+)?)\s*(?:\(?\s*cash\s*\)?)?',
        clean_text,
        re.IGNORECASE
    )
    if mixed_match:
        own = float(mixed_match.group(1))
        cash_box = float(mixed_match.group(2))
        total = round(own + cash_box, 2)
        desc = re.sub(
            r'(\d+(?:\.\d+)?)\s*(?:\(?\s*own\s*\)?)\s*\+\s*(\d+(?:\.\d+)?)\s*(?:\(?\s*cash\s*\)?)?',
            '',
            clean_text,
            flags=re.IGNORECASE
        ).strip(" -:;,")
        return {
            "description": desc or default_description,
            "total_amount": total,
            "own_amount": own,
            "cash_box_amount": cash_box,
            "raw_text": text
        }

    # 2. Check for purely own pattern: e.g. 5000 (own) or 5000 own
    own_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\(\s*own\s*\)|(?:\bown\b))', clean_text, re.IGNORECASE)
    if own_match:
        own = float(own_match.group(1))
        desc = re.sub(r'(\d+(?:\.\d+)?)\s*(?:\(\s*own\s*\)|(?:\bown\b))', '', clean_text, flags=re.IGNORECASE).strip(" -:;,")
        return {
            "description": desc or default_description,
            "total_amount": own,
            "own_amount": own,
            "cash_box_amount": 0.0,
            "raw_text": text
        }

    # 3. Check for standard numeric amount
    amounts = re.findall(r'(\d+(?:\.\d+)?)', clean_text)
    if amounts:
        amount = float(amounts[-1])
        desc = clean_text[:clean_text.rfind(amounts[-1])].strip(" -:;,")
        return {
            "description": desc or default_description,
            "total_amount": amount,
            "own_amount": 0.0,
            "cash_box_amount": amount,
            "raw_text": text
        }

    return {
        "description": clean_text or default_description,
        "total_amount": 0.0,
        "own_amount": 0.0,
        "cash_box_amount": 0.0,
        "raw_text": text
    }


def calculate_record_totals(
    customer_amounts: List[float],
    digital_amounts: List[float],
    expenses_data: List[Dict[str, Any]]
) -> Dict[str, float]:
    """
    Core Chellam Traders Financial Calculation Engine.
    
    Formulas:
    1. total_customer_money = SUM(customer_receipts)
    2. total_digital_money = SUM(digital_entries)
    3. total_cash_received = total_customer_money - total_digital_money
    4. total_expenses = SUM(expense.total_amount)
    5. total_own_money = SUM(expense.own_amount)
    6. total_cash_box_expenses = SUM(expense.cash_box_amount)
    7. in_hand_money = total_cash_received - total_cash_box_expenses

    CRITICAL RULES:
    - Digital references are NOT added to customer money again.
    - Own money must NOT reduce cash box / in-hand money.
    - For each expense: total_amount == own_amount + cash_box_amount.
    """
    total_customer_money = round(sum(float(a) for a in customer_amounts if a is not None), 2)
    total_digital_money = round(sum(float(a) for a in digital_amounts if a is not None), 2)
    
    # RULE 4: Cash Received = Customer Money - Digital Received
    total_cash_received = round(total_customer_money - total_digital_money, 2)
    
    total_expenses = 0.0
    total_own_money = 0.0
    total_cash_box_expenses = 0.0
    
    for exp in expenses_data:
        t_amt = round(float(exp.get("total_amount", 0.0)), 2)
        o_amt = round(float(exp.get("own_amount", 0.0)), 2)
        c_amt = round(float(exp.get("cash_box_amount", 0.0)), 2)
        
        # Enforce consistency: if total doesn't match sum, fix total or cash box
        if abs(t_amt - (o_amt + c_amt)) > 0.01:
            t_amt = round(o_amt + c_amt, 2)
            
        total_expenses += t_amt
        total_own_money += o_amt
        total_cash_box_expenses += c_amt

    total_expenses = round(total_expenses, 2)
    total_own_money = round(total_own_money, 2)
    total_cash_box_expenses = round(total_cash_box_expenses, 2)
    
    # RULE 8: In-Hand Money = Cash Received - Cash Box Expenses
    in_hand_money = round(total_cash_received - total_cash_box_expenses, 2)
    
    return {
        "total_customer_money": total_customer_money,
        "total_digital_money": total_digital_money,
        "total_cash_received": total_cash_received,
        "total_expenses": total_expenses,
        "total_own_money": total_own_money,
        "total_cash_box_expenses": total_cash_box_expenses,
        "in_hand_money": in_hand_money
    }
