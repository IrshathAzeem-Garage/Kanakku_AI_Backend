from pydantic import BaseModel, ConfigDict
import datetime as dt
from typing import Optional


class DashboardSummaryOut(BaseModel):
    date: dt.date
    total_customer_money: float = 0.0
    digital_received: float = 0.0
    cash_received: float = 0.0
    total_expenses: float = 0.0
    own_money: float = 0.0
    cash_box_expenses: float = 0.0
    in_hand_money: float = 0.0
    record_count: int = 0
    shop_name: Optional[str] = None
    currency: Optional[str] = "INR"

    model_config = ConfigDict(from_attributes=True)
