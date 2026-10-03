from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.models.record import DailyRecord
from app.services.auth_service import get_current_user, get_current_user_shop
from app.utils.timezone import get_today_date

router = APIRouter(prefix="/reports", tags=["Reports"])


def compute_summary_for_records(records: List[DailyRecord], shop: Shop) -> Dict[str, Any]:
    total_customer_money = round(sum(r.total_customer_money for r in records), 2)
    total_digital_money = round(sum(r.total_digital_money for r in records), 2)
    total_cash_received = round(sum(r.total_cash_received for r in records), 2)
    total_expenses = round(sum(r.total_expenses for r in records), 2)
    total_own_money = round(sum(r.total_own_money for r in records), 2)
    total_cash_box_expenses = round(sum(r.total_cash_box_expenses for r in records), 2)
    total_in_hand_money = round(sum(r.in_hand_money for r in records), 2)

    return {
        "shop_name": shop.name,
        "currency": shop.currency,
        "record_count": len(records),
        "total_customer_money": total_customer_money,
        "total_digital_money": total_digital_money,
        "total_cash_received": total_cash_received,
        "total_expenses": total_expenses,
        "total_own_money": total_own_money,
        "total_cash_box_expenses": total_cash_box_expenses,
        "total_in_hand_money": total_in_hand_money,
        "records": [
            {
                "id": r.id,
                "record_date": r.record_date,
                "total_customer_money": r.total_customer_money,
                "total_digital_money": r.total_digital_money,
                "total_cash_received": r.total_cash_received,
                "total_expenses": r.total_expenses,
                "total_own_money": r.total_own_money,
                "total_cash_box_expenses": r.total_cash_box_expenses,
                "in_hand_money": r.in_hand_money
            }
            for r in records
        ]
    }


@router.get("/daily")
def get_daily_report(
    target_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    selected_date = target_date or get_today_date()
    records = db.query(DailyRecord).filter(
        DailyRecord.shop_id == shop.id,
        DailyRecord.record_date == selected_date
    ).all()
    
    summary = compute_summary_for_records(records, shop)
    summary["report_type"] = "daily"
    summary["period_label"] = selected_date.strftime("%d %b %Y")
    summary["date"] = selected_date
    return summary


@router.get("/weekly")
def get_weekly_report(
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    end = end_date or get_today_date()
    start = end - timedelta(days=6)
    records = db.query(DailyRecord).filter(
        DailyRecord.shop_id == shop.id,
        DailyRecord.record_date >= start,
        DailyRecord.record_date <= end
    ).order_by(desc(DailyRecord.record_date)).all()
    
    summary = compute_summary_for_records(records, shop)
    summary["report_type"] = "weekly"
    summary["period_label"] = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    summary["start_date"] = start
    summary["end_date"] = end
    return summary


@router.get("/monthly")
def get_monthly_report(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    today = get_today_date()
    target_year = year or today.year
    target_month = month or today.month
    
    import calendar
    _, last_day = calendar.monthrange(target_year, target_month)
    start = date(target_year, target_month, 1)
    end = date(target_year, target_month, last_day)

    records = db.query(DailyRecord).filter(
        DailyRecord.shop_id == shop.id,
        DailyRecord.record_date >= start,
        DailyRecord.record_date <= end
    ).order_by(desc(DailyRecord.record_date)).all()

    summary = compute_summary_for_records(records, shop)
    summary["report_type"] = "monthly"
    summary["period_label"] = f"{start.strftime('%B %Y')}"
    summary["year"] = target_year
    summary["month"] = target_month
    summary["start_date"] = start
    summary["end_date"] = end
    return summary
