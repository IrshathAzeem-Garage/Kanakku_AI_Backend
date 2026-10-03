import time
import uuid
from typing import List, Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.models.record import DailyRecord, CustomerReceipt, DigitalEntry, Expense
from app.schemas.record import (
    DailyRecordCreate,
    DailyRecordUpdate,
    DailyRecordOut,
    DailyRecordSummary,
    ExtractionResult
)
from app.services.auth_service import get_current_user, get_current_user_shop
from app.services.image_service import process_and_save_upload
from app.services.ai_service import analyze_kanakku_image
from app.services.calculation_service import calculate_record_totals
from app.utils.logger import log_image_analysis, logger

router = APIRouter(prefix="/records", tags=["Records"])


@router.post("/analyze", response_model=ExtractionResult)
async def analyze_record_image(
    response: Response,
    image: UploadFile = File(...),
    request_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """
    Analyzes an uploaded handwritten paper image.
    1. Generates unique UUID and saves newly uploaded file (never reuses old file paths).
    2. Computes SHA-256 hash to detect duplicate uploads in user's shop.
    3. Sends exact image bytes to AI / Vision extraction pipeline.
    4. Backend strictly calculates four-section totals and returns preview for user review.
    5. Cache-Control: no-store enforced to prevent stale cached responses.
    """
    # Enforce no caching on backend
    response.headers["Cache-Control"] = "no-store"
    
    start_time = time.time()
    analysis_started_at = datetime.now(timezone.utc).isoformat()
    req_id = request_id or str(uuid.uuid4())
    
    # Process image with strict UUID + extension
    img_res = process_and_save_upload(image, request_id=req_id)
    
    # Check if exact same image was previously recorded in this shop
    existing_duplicate = db.query(DailyRecord).filter(
        DailyRecord.shop_id == shop.id,
        DailyRecord.image_hash == img_res.sha256_hash
    ).first()
    is_duplicate = existing_duplicate is not None

    # Run extraction pipeline with exact image bytes & metadata
    result = analyze_kanakku_image(
        image_path=img_res.file_path,
        image_url=img_res.relative_url,
        image_hash=img_res.sha256_hash,
        request_id=req_id,
        image_id=img_res.image_id,
        content_type=img_res.content_type,
        is_duplicate=is_duplicate
    )

    duration_ms = (time.time() - start_time) * 1000
    analysis_completed_at = datetime.now(timezone.utc).isoformat()

    log_image_analysis(
        request_id=req_id,
        user_id=current_user.id,
        original_filename=img_res.original_filename,
        image_id=img_res.image_id,
        file_size_bytes=img_res.file_size_bytes,
        content_type=img_res.content_type,
        sha256_hash=img_res.sha256_hash,
        analysis_started_at=analysis_started_at,
        analysis_completed_at=analysis_completed_at,
        status="SUCCESS",
        duration_ms=duration_ms,
        extra_info=f"shop_id={shop.id} | is_duplicate={is_duplicate}"
    )

    return result



@router.post("", response_model=DailyRecordOut, status_code=status.HTTP_201_CREATED)
def create_daily_record(
    record_data: DailyRecordCreate,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """
    Saves a confirmed daily record to PostgreSQL belonging to the authenticated shop.
    CRITICAL: Totals are strictly computed on the backend - frontend totals are NOT trusted.
    """
    cust_amounts = [item.amount for item in record_data.customer_receipts]
    dig_amounts = [item.amount for item in record_data.digital_entries]
    exp_dicts = [
        {
            "total_amount": item.total_amount,
            "own_amount": item.own_amount,
            "cash_box_amount": item.cash_box_amount
        }
        for item in record_data.expenses
    ]

    totals = calculate_record_totals(cust_amounts, dig_amounts, exp_dicts)

    new_record = DailyRecord(
        shop_id=shop.id,
        user_id=current_user.id,
        record_date=record_data.record_date,
        total_customer_money=totals["total_customer_money"],
        total_digital_money=totals["total_digital_money"],
        total_cash_received=totals["total_cash_received"],
        total_expenses=totals["total_expenses"],
        total_own_money=totals["total_own_money"],
        total_cash_box_expenses=totals["total_cash_box_expenses"],
        in_hand_money=totals["in_hand_money"],
        image_url=record_data.image_url,
        image_hash=record_data.image_hash,
        notes=record_data.notes
    )

    db.add(new_record)
    db.flush()

    for item in record_data.customer_receipts:
        db.add(CustomerReceipt(
            daily_record_id=new_record.id,
            amount=item.amount,
            payment_type=item.payment_type or "UNKNOWN",
            description=item.description,
            raw_text=item.raw_text,
            source_reference=item.source_reference
        ))

    for item in record_data.digital_entries:
        db.add(DigitalEntry(
            daily_record_id=new_record.id,
            amount=item.amount,
            raw_text=item.raw_text
        ))

    for item in record_data.expenses:
        db.add(Expense(
            daily_record_id=new_record.id,
            description=item.description,
            total_amount=item.total_amount,
            own_amount=item.own_amount or 0.0,
            cash_box_amount=item.cash_box_amount or 0.0,
            raw_text=item.raw_text
        ))

    db.commit()
    db.refresh(new_record)
    return new_record


@router.get("", response_model=List[DailyRecordSummary])
def get_daily_records(
    record_date: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Lists daily records strictly isolated to the user's shop."""
    query = db.query(DailyRecord).filter(DailyRecord.shop_id == shop.id)
    if record_date:
        query = query.filter(DailyRecord.record_date == record_date)
    return query.order_by(desc(DailyRecord.record_date), desc(DailyRecord.id)).offset(offset).limit(limit).all()


@router.get("/{record_id}", response_model=DailyRecordOut)
def get_daily_record_by_id(
    record_id: int,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Retrieves single daily record with complete line-item breakdown for the user's shop."""
    record = db.query(DailyRecord).filter(
        DailyRecord.id == record_id,
        DailyRecord.shop_id == shop.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Daily record not found or access denied")
    return record


@router.put("/{record_id}", response_model=DailyRecordOut)
def update_daily_record(
    record_id: int,
    update_data: DailyRecordUpdate,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Updates record line-items and recomputes all four-section totals within user's shop."""
    record = db.query(DailyRecord).filter(
        DailyRecord.id == record_id,
        DailyRecord.shop_id == shop.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Daily record not found or access denied")

    if update_data.record_date:
        record.record_date = update_data.record_date
    if update_data.notes is not None:
        record.notes = update_data.notes

    if update_data.customer_receipts is not None:
        db.query(CustomerReceipt).filter(CustomerReceipt.daily_record_id == record.id).delete()
        for item in update_data.customer_receipts:
            db.add(CustomerReceipt(
                daily_record_id=record.id,
                amount=item.amount,
                payment_type=item.payment_type or "UNKNOWN",
                description=item.description,
                raw_text=item.raw_text,
                source_reference=item.source_reference
            ))

    if update_data.digital_entries is not None:
        db.query(DigitalEntry).filter(DigitalEntry.daily_record_id == record.id).delete()
        for item in update_data.digital_entries:
            db.add(DigitalEntry(
                daily_record_id=record.id,
                amount=item.amount,
                raw_text=item.raw_text
            ))

    if update_data.expenses is not None:
        db.query(Expense).filter(Expense.daily_record_id == record.id).delete()
        for item in update_data.expenses:
            db.add(Expense(
                daily_record_id=record.id,
                description=item.description,
                total_amount=item.total_amount,
                own_amount=item.own_amount or 0.0,
                cash_box_amount=item.cash_box_amount or 0.0,
                raw_text=item.raw_text
            ))

    db.flush()

    # Recalculate totals
    cust_amounts = [r.amount for r in record.customer_receipts]
    dig_amounts = [d.amount for d in record.digital_entries]
    exp_dicts = [
        {"total_amount": e.total_amount, "own_amount": e.own_amount, "cash_box_amount": e.cash_box_amount}
        for e in record.expenses
    ]

    totals = calculate_record_totals(cust_amounts, dig_amounts, exp_dicts)
    record.total_customer_money = totals["total_customer_money"]
    record.total_digital_money = totals["total_digital_money"]
    record.total_cash_received = totals["total_cash_received"]
    record.total_expenses = totals["total_expenses"]
    record.total_own_money = totals["total_own_money"]
    record.total_cash_box_expenses = totals["total_cash_box_expenses"]
    record.in_hand_money = totals["in_hand_money"]

    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daily_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Deletes a daily record strictly isolated to the user's shop."""
    record = db.query(DailyRecord).filter(
        DailyRecord.id == record_id,
        DailyRecord.shop_id == shop.id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Daily record not found or access denied")
    
    db.delete(record)
    db.commit()
    return None
