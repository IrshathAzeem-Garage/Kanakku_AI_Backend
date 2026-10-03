from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.models.record import DailyRecord
from app.schemas.dashboard import DashboardSummaryOut
from app.services.auth_service import get_current_user, get_current_user_shop
from app.utils.timezone import get_today_date

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    date_val: Optional[date] = Query(None, alias="date"),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """
    Calculates dynamic accounting summary strictly from PostgreSQL for the user's shop.
    Returns 0s if no records are found (never mock data).
    """
    selected_date = date_val or get_today_date()
    
    # Strictly filter by user's shop_id
    records = db.query(DailyRecord).filter(
        DailyRecord.shop_id == shop.id,
        DailyRecord.record_date == selected_date
    ).all()

    if not records:
        return DashboardSummaryOut(
            date=selected_date,
            total_customer_money=0.0,
            digital_received=0.0,
            cash_received=0.0,
            total_expenses=0.0,
            own_money=0.0,
            cash_box_expenses=0.0,
            in_hand_money=0.0,
            record_count=0,
            shop_name=shop.name,
            currency=shop.currency
        )

    total_customer = round(sum(r.total_customer_money for r in records), 2)
    total_digital = round(sum(r.total_digital_money for r in records), 2)
    total_cash = round(sum(r.total_cash_received for r in records), 2)
    total_expenses = round(sum(r.total_expenses for r in records), 2)
    total_own = round(sum(r.total_own_money for r in records), 2)
    total_cash_box = round(sum(r.total_cash_box_expenses for r in records), 2)
    total_in_hand = round(sum(r.in_hand_money for r in records), 2)

    return DashboardSummaryOut(
        date=selected_date,
        total_customer_money=total_customer,
        digital_received=total_digital,
        cash_received=total_cash,
        total_expenses=total_expenses,
        own_money=total_own,
        cash_box_expenses=total_cash_box,
        in_hand_money=total_in_hand,
        record_count=len(records),
        shop_name=shop.name,
        currency=shop.currency
    )
