from datetime import datetime, date
import pytz
from app.config import settings

tz = pytz.timezone(settings.APP_TIMEZONE)


def get_current_time() -> datetime:
    """Returns current localized datetime in Asia/Kolkata."""
    return datetime.now(tz)


def get_today_date() -> date:
    """Returns today's date in Asia/Kolkata timezone."""
    return datetime.now(tz).date()


def format_inr(amount: float) -> str:
    """Format float/int to Indian Rupee currency format (e.g., ₹1,50,000)."""
    if amount is None:
        return "₹0"
    
    val = round(amount, 2)
    is_neg = val < 0
    val = abs(val)
    
    s = f"{val:.2f}"
    int_part, dec_part = s.split(".")
    
    if len(int_part) <= 3:
        formatted = int_part
    else:
        last3 = int_part[-3:]
        remaining = int_part[:-3]
        # In Indian system, subsequent groups are 2 digits
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted = ",".join(groups) + "," + last3

    if dec_part == "00":
        res = f"₹{formatted}"
    else:
        res = f"₹{formatted}.{dec_part}"
    
    return f"-{res}" if is_neg else res
