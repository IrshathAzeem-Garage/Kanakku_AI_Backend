import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import date

from app.config import settings
from app.utils.logger import logger
from app.schemas.record import (
    ExtractionResult,
    RawCustomerEntry,
    RawDigitalEntry,
    RawExpenseEntry,
    UncertainEntry
)
from app.services.calculation_service import calculate_record_totals, parse_expense_text


# =========================================================================
# ABSOLUTE NO-HALLUCINATION EXTRACTION PROMPT
# =========================================================================
GEMINI_EXTRACTION_PROMPT = """
You are a financial document extraction system for handwritten accounting ledgers (Kanakku).

CRITICAL NO-HALLUCINATION RULES:
1. You MUST extract information ONLY from the pixels/content visible in the provided image.
2. The image is the ONLY source of truth.
3. NEVER guess.
4. NEVER infer a missing amount.
5. NEVER invent a number.
6. NEVER use information from previous images or previous requests.
7. NEVER use example values as actual values.
8. NEVER complete partially visible numbers using assumptions.
9. If an amount cannot be clearly read:
   - Do not guess it.
   - Set amount to null, confidence to 0.4, needs_review to true.
   - Include the raw text as visibly readable.
10. If there are no readable entries in the image:
    Return empty lists for customer_money, digital_entries, and expenses, and add an explanation in uncertain_entries.

DOCUMENT STRUCTURE & RULES:
- DATE:
  Usually written on the top-right area (e.g. "03/10/2026").
  Extract ONLY if visibly readable. Format as YYYY-MM-DD.
  If unreadable or not present: return null. DO NOT invent today's date.

- CUSTOMER MONEY (Right side):
  Contains customer money received (names/goods with numeric amounts, e.g. "Ravi - 120", "Vijay - 1,320").
  Extract every clearly readable numeric amount on the customer-money section.
  Include the raw_text and description.

- DIGITAL PAYMENTS (Left or middle section):
  Contains references like "PP 1 - 400", "PP - 500", "PP 620", "PhonePe 500", "GPay 300", "UPI 700".
  The provider name does NOT matter (PP = PhonePe).
  Extract amount and raw_text.
  IMPORTANT: Digital payments are ALREADY included in the customer-money amounts on the right.
  DO NOT add digital payments again to customer money.

- EXPENSES (Bottom or left area, e.g. "GIVEN TO DEALERS", "Expenses"):
  Payments made to dealers, suppliers, or shop costs (e.g. "Aachi - 2,350", "Dealer 10000 own + 572").
  Extract:
  - description: Supplier / expense name
  - total_amount: Total expense
  - own_amount: Amount paid from owner's own funds (only if specified as 'own' or '(own)')
  - cash_box_amount: Amount paid from shop cash box (default if 'own' not specified)
  - raw_text: Raw text as written

JSON OUTPUT SCHEMA (Return ONLY valid JSON):
{
  "date": "YYYY-MM-DD or null",
  "customer_money": [
    {"amount": 120.0, "raw_text": "Ravi - 120", "description": "Ravi", "confidence": 0.95, "needs_review": false}
  ],
  "digital_entries": [
    {"amount": 400.0, "raw_text": "PP 1 - 400", "confidence": 0.95, "needs_review": false}
  ],
  "expenses": [
    {
      "description": "Aachi",
      "total_amount": 2350.0,
      "own_amount": 0.0,
      "cash_box_amount": 2350.0,
      "raw_text": "Aachi - 2,350",
      "confidence": 0.95,
      "needs_review": false
    }
  ],
  "uncertain_entries": []
}
"""


def extract_with_gemini(
    image_path: str,
    content_type: str = "image/jpeg",
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Sends the exact uploaded image bytes to Google Gemini Vision model.
    Enforces deterministic temperature=0.0 and JSON response schema.
    """
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        
        with open(image_path, "rb") as img_file:
            image_bytes = img_file.read()

        candidate_models = [settings.AI_MODEL, "gemini-flash-lite-latest", "gemini-flash-latest"]
        # Remove duplicates while preserving order
        candidate_models = list(dict.fromkeys(candidate_models))

        for model_name in candidate_models:
            try:
                logger.info(
                    f"Sending {len(image_bytes)} image bytes to Vision model ({model_name})..."
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=content_type,
                        ),
                        GEMINI_EXTRACTION_PROMPT
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0  # Zero temperature for deterministic factual extraction
                    )
                )
                
                text = response.text
                if text:
                    clean_json = text.strip()
                    if clean_json.startswith("```"):
                        clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                        clean_json = re.sub(r"\n?```$", "", clean_json)
                    return json.loads(clean_json)
            except Exception as model_err:
                logger.warning(f"Model {model_name} failed: {model_err}. Trying next candidate...")
                continue
    except Exception as e:
        logger.error(f"Gemini Vision extraction error: {e}")
        return None

    return None


def validate_amount_in_raw_text(amount: Optional[float], raw_text: Optional[str]) -> bool:
    """
    Validation check: Is this extracted amount actually represented in raw_text?
    Strips commas, decimals, and spaces to verify presence.
    """
    if amount is None:
        return True
    if not raw_text:
        return False
    
    clean_raw = re.sub(r'[,.\s]', '', str(raw_text))
    # Check whole number digits or float digits
    int_str = str(int(amount)) if amount == int(amount) else f"{amount:.2f}".replace('.', '')
    return (int_str in clean_raw) or (str(int(amount)) in str(raw_text))


def parse_date_string(date_str: Any) -> Optional[date]:
    """Safely parses dates in YYYY-MM-DD or DD/MM/YYYY formats."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    
    # Try ISO YYYY-MM-DD
    try:
        return date.fromisoformat(date_str)
    except Exception:
        pass
    
    # Try DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$', date_str)
    if m:
        d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mon, d)
        except Exception:
            return None
            
    return None


def analyze_kanakku_image(
    image_path: str,
    image_url: str,
    image_hash: str,
    request_id: Optional[str] = None,
    image_id: Optional[str] = None,
    content_type: str = "image/jpeg",
    is_duplicate: bool = False
) -> ExtractionResult:
    """
    Main extraction pipeline:
    1. If AI API key is configured, send the exact image bytes to Vision model.
    2. If no API key or image is unreadable: RETURN EMPTY RESULT WITH REASON.
       NEVER FABRICATE OR GENERATE RANDOM FINANCIAL DATA.
    3. Run rigorous cross-validation between extracted amounts and visible raw_text.
    4. Backend strictly calculates all financial totals.
    """
    api_key = settings.effective_ai_key
    raw_data = None
    
    if api_key:
        logger.info(f"Triggering Gemini Vision extraction for image_id={image_id}...")
        raw_data = extract_with_gemini(
            image_path=image_path,
            content_type=content_type,
            api_key=api_key
        )
    else:
        logger.warning(
            "GEMINI_API_KEY / AI_API_KEY is not configured in backend/.env. "
            "Returning empty result — ZERO financial values are fabricated."
        )

    # If extraction could not run or returned no data, return empty result
    if not raw_data:
        reason = (
            "AI Vision API key is not configured in backend/.env. Please configure GEMINI_API_KEY or enter values manually."
            if not api_key
            else "The uploaded image could not be read reliably by the AI model. Zero numbers were invented."
        )
        return ExtractionResult(
            date=None,
            customer_money=[],
            digital_entries=[],
            expenses=[],
            uncertain_entries=[UncertainEntry(reason=reason)],
            total_customer_money=0.0,
            total_digital_money=0.0,
            total_cash_received=0.0,
            total_expenses=0.0,
            total_own_money=0.0,
            total_cash_box_expenses=0.0,
            in_hand_money=0.0,
            request_id=request_id,
            image_id=image_id,
            image_url=image_url,
            image_hash=image_hash,
            is_duplicate=is_duplicate,
            warning_message=reason
        )

    uncertain_list: List[UncertainEntry] = []

    # 1. Parse Customer Money entries
    cust_entries: List[RawCustomerEntry] = []
    cust_amounts: List[float] = []
    for item in raw_data.get("customer_money", []):
        amt = item.get("amount")
        raw_txt = str(item.get("raw_text", "")).strip()
        conf = float(item.get("confidence", 1.0))
        needs_rev = item.get("needs_review", False) or (amt is None) or (conf < 0.80)
        
        # Cross-validate amount with raw text evidence
        if amt is not None:
            amt = float(amt)
            if not validate_amount_in_raw_text(amt, raw_txt):
                needs_rev = True
                conf = min(conf, 0.4)
                uncertain_list.append(
                    UncertainEntry(
                        reason=f"Customer amount {amt} is not confirmed in raw text '{raw_txt}'",
                        raw_text=raw_txt,
                        amount=amt,
                        field="customer_money"
                    )
                )

        entry = RawCustomerEntry(
            amount=amt,
            raw_text=raw_txt,
            confidence=conf,
            needs_review=needs_rev,
            description=str(item.get("description", "")).strip()
        )
        cust_entries.append(entry)
        if entry.amount is not None:
            cust_amounts.append(entry.amount)

    # 2. Parse Digital entries
    dig_entries: List[RawDigitalEntry] = []
    dig_amounts: List[float] = []
    for item in raw_data.get("digital_entries", []):
        amt = item.get("amount")
        raw_txt = str(item.get("raw_text", "")).strip()
        conf = float(item.get("confidence", 1.0))
        needs_rev = item.get("needs_review", False) or (amt is None) or (conf < 0.80)
        
        if amt is not None:
            amt = float(amt)
            if not validate_amount_in_raw_text(amt, raw_txt):
                needs_rev = True
                conf = min(conf, 0.4)
                uncertain_list.append(
                    UncertainEntry(
                        reason=f"Digital amount {amt} is not confirmed in raw text '{raw_txt}'",
                        raw_text=raw_txt,
                        amount=amt,
                        field="digital_entries"
                    )
                )

        entry = RawDigitalEntry(
            amount=amt,
            raw_text=raw_txt,
            confidence=conf,
            needs_review=needs_rev
        )
        dig_entries.append(entry)
        if entry.amount is not None:
            dig_amounts.append(entry.amount)

    # 3. Parse Expenses
    exp_entries: List[RawExpenseEntry] = []
    exp_dicts: List[Dict[str, Any]] = []
    for item in raw_data.get("expenses", []):
        desc = item.get("description", "Expense")
        raw_txt = str(item.get("raw_text", "")).strip()
        
        tot = item.get("total_amount")
        own = item.get("own_amount", 0.0)
        cbox = item.get("cash_box_amount", 0.0)
        
        # If numbers are missing or incomplete, parse using regex parser
        if (tot is None or tot == 0) and raw_txt:
            parsed = parse_expense_text(raw_txt, default_description=desc)
            tot = parsed["total_amount"]
            own = parsed["own_amount"]
            cbox = parsed["cash_box_amount"]
            desc = parsed["description"]

        tot = float(tot or 0.0)
        own = float(own or 0.0)
        cbox = float(cbox or 0.0)
        
        # Enforce consistency: total = own + cash_box
        if abs(tot - (own + cbox)) > 0.01:
            tot = round(own + cbox, 2)
            
        conf = float(item.get("confidence", 1.0))
        needs_rev = item.get("needs_review", False) or (conf < 0.80)
        
        if tot > 0 and not validate_amount_in_raw_text(tot, raw_txt):
            needs_rev = True
            conf = min(conf, 0.4)
            uncertain_list.append(
                UncertainEntry(
                    reason=f"Expense amount {tot} is not confirmed in raw text '{raw_txt}'",
                    raw_text=raw_txt,
                    amount=tot,
                    field="expenses"
                )
            )

        exp_entry = RawExpenseEntry(
            description=desc,
            total_amount=tot,
            own_amount=own,
            cash_box_amount=cbox,
            raw_text=raw_txt,
            confidence=conf,
            needs_review=needs_rev
        )
        exp_entries.append(exp_entry)
        exp_dicts.append({
            "total_amount": tot,
            "own_amount": own,
            "cash_box_amount": cbox
        })

    # Include any model-reported uncertain entries
    for u in raw_data.get("uncertain_entries", []):
        if isinstance(u, dict):
            uncertain_list.append(
                UncertainEntry(
                    reason=u.get("reason", "Unreadable text"),
                    raw_text=u.get("raw_text"),
                    amount=u.get("amount"),
                    field=u.get("field")
                )
            )
        elif isinstance(u, str):
            uncertain_list.append(UncertainEntry(reason=u))

    # Backend strictly calculates totals (LLM is NEVER trusted with calculations)
    totals = calculate_record_totals(cust_amounts, dig_amounts, exp_dicts)
    
    # Parse date strictly (None if unreadable/not present)
    rec_date = parse_date_string(raw_data.get("date"))

    warning_msg = None
    if is_duplicate:
        warning_msg = "Notice: This exact image was previously recorded in this shop. Please review entries carefully before saving."
    elif uncertain_list and (not cust_entries and not dig_entries and not exp_entries):
        warning_msg = "The image could not be read reliably. Please enter values manually."

    return ExtractionResult(
        date=rec_date,
        customer_money=cust_entries,
        digital_entries=dig_entries,
        expenses=exp_entries,
        uncertain_entries=uncertain_list,
        total_customer_money=totals["total_customer_money"],
        total_digital_money=totals["total_digital_money"],
        total_cash_received=totals["total_cash_received"],
        total_expenses=totals["total_expenses"],
        total_own_money=totals["total_own_money"],
        total_cash_box_expenses=totals["total_cash_box_expenses"],
        in_hand_money=totals["in_hand_money"],
        request_id=request_id,
        image_id=image_id,
        image_url=image_url,
        image_hash=image_hash,
        is_duplicate=is_duplicate,
        warning_message=warning_msg
    )
