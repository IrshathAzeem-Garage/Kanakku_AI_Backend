from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
import datetime as dt
from app.utils.timezone import get_today_date


# ==========================================
# Extraction / AI Raw Schemas
# ==========================================
class RawCustomerEntry(BaseModel):
    amount: Optional[float] = None
    raw_text: Optional[str] = ""
    confidence: Optional[float] = 1.0
    needs_review: Optional[bool] = False
    description: Optional[str] = ""


class RawDigitalEntry(BaseModel):
    amount: Optional[float] = None
    raw_text: Optional[str] = ""
    confidence: Optional[float] = 1.0
    needs_review: Optional[bool] = False


class RawExpenseEntry(BaseModel):
    description: str = "Expense"
    total_amount: Optional[float] = 0.0
    own_amount: Optional[float] = 0.0
    cash_box_amount: Optional[float] = 0.0
    raw_text: Optional[str] = ""
    confidence: Optional[float] = 1.0
    needs_review: Optional[bool] = False


class UncertainEntry(BaseModel):
    reason: str
    raw_text: Optional[str] = None
    amount: Optional[float] = None
    field: Optional[str] = None


class ExtractionResult(BaseModel):
    date: Optional[dt.date] = None
    customer_money: List[RawCustomerEntry] = []
    digital_entries: List[RawDigitalEntry] = []
    expenses: List[RawExpenseEntry] = []
    uncertain_entries: List[UncertainEntry] = []
    
    # Calculated previews (strictly backend-computed)
    total_customer_money: float = 0.0
    total_digital_money: float = 0.0
    total_cash_received: float = 0.0
    total_expenses: float = 0.0
    total_own_money: float = 0.0
    total_cash_box_expenses: float = 0.0
    in_hand_money: float = 0.0
    
    # Image & request metadata
    request_id: Optional[str] = None
    image_id: Optional[str] = None
    image_url: Optional[str] = None
    image_hash: Optional[str] = None
    is_duplicate: bool = False
    warning_message: Optional[str] = None



# ==========================================
# Input Schemas for Database Persistence
# ==========================================
class CustomerReceiptCreate(BaseModel):
    amount: float
    payment_type: Optional[str] = "UNKNOWN"
    description: Optional[str] = None
    raw_text: Optional[str] = None
    source_reference: Optional[str] = None


class CustomerReceiptOut(BaseModel):
    id: int
    daily_record_id: int
    amount: float
    payment_type: str
    description: Optional[str] = None
    raw_text: Optional[str] = None
    source_reference: Optional[str] = None
    created_at: Optional[dt.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DigitalEntryCreate(BaseModel):
    amount: float
    raw_text: Optional[str] = None


class DigitalEntryOut(BaseModel):
    id: int
    daily_record_id: int
    amount: float
    raw_text: Optional[str] = None
    created_at: Optional[dt.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    description: str
    total_amount: float
    own_amount: Optional[float] = 0.0
    cash_box_amount: Optional[float] = 0.0
    raw_text: Optional[str] = None

    @field_validator("cash_box_amount", mode="before")
    def validate_cash_box(cls, v, info):
        return v if v is not None else 0.0


class ExpenseOut(BaseModel):
    id: int
    daily_record_id: int
    description: str
    total_amount: float
    own_amount: float
    cash_box_amount: float
    raw_text: Optional[str] = None
    created_at: Optional[dt.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DailyRecordCreate(BaseModel):
    record_date: dt.date = Field(default_factory=get_today_date)
    customer_receipts: List[CustomerReceiptCreate] = []
    digital_entries: List[DigitalEntryCreate] = []
    expenses: List[ExpenseCreate] = []
    image_url: Optional[str] = None
    image_hash: Optional[str] = None
    notes: Optional[str] = None


class DailyRecordUpdate(BaseModel):
    record_date: Optional[dt.date] = None
    customer_receipts: Optional[List[CustomerReceiptCreate]] = None
    digital_entries: Optional[List[DigitalEntryCreate]] = None
    expenses: Optional[List[ExpenseCreate]] = None
    notes: Optional[str] = None


class DailyRecordOut(BaseModel):
    id: int
    shop_id: int
    user_id: int
    record_date: dt.date
    
    total_customer_money: float
    total_digital_money: float
    total_cash_received: float
    
    total_expenses: float
    total_own_money: float
    total_cash_box_expenses: float
    
    in_hand_money: float
    
    image_url: Optional[str] = None
    image_hash: Optional[str] = None
    notes: Optional[str] = None

    # Delivery & PDF metadata
    pdf_generated_at: Optional[dt.datetime] = None
    pdf_file_name: Optional[str] = None
    whatsapp_status: Optional[str] = "not_sent"
    whatsapp_message_id: Optional[str] = None
    whatsapp_sent_at: Optional[dt.datetime] = None
    whatsapp_error: Optional[str] = None
    email_status: Optional[str] = "not_sent"
    email_sent_at: Optional[dt.datetime] = None
    email_error: Optional[str] = None
    
    customer_receipts: List[CustomerReceiptOut] = []
    digital_entries: List[DigitalEntryOut] = []
    expenses: List[ExpenseOut] = []
    
    created_at: Optional[dt.datetime] = None
    updated_at: Optional[dt.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DailyRecordSummary(BaseModel):
    id: int
    record_date: dt.date
    total_customer_money: float
    total_digital_money: float
    total_cash_received: float
    total_expenses: float
    total_own_money: float
    total_cash_box_expenses: float
    in_hand_money: float
    pdf_generated_at: Optional[dt.datetime] = None
    pdf_file_name: Optional[str] = None
    whatsapp_status: Optional[str] = "not_sent"
    email_status: Optional[str] = "not_sent"
    created_at: Optional[dt.datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DailyRecordCreateResponse(DailyRecordOut):
    success: bool = True
    record_id: int
    pdf_generated: bool = False
    pdf_file_name: Optional[str] = None
    email_sent: bool = False
    email_status: str = "not_sent"
    email_error: Optional[str] = None
    whatsapp_sent: bool = False
    whatsapp_status: str = "not_sent"
    whatsapp_error: Optional[str] = None


class DeliveryStatusOut(BaseModel):
    record_id: int
    pdf_generated: bool = False
    pdf_generated_at: Optional[dt.datetime] = None
    pdf_file_name: Optional[str] = None
    email_sent: bool = False
    email_status: str = "not_sent"
    email_error: Optional[str] = None
    recipient_email: Optional[str] = None
    whatsapp_status: str = "not_sent"
    whatsapp_message_id: Optional[str] = None
    whatsapp_sent_at: Optional[dt.datetime] = None
    whatsapp_error: Optional[str] = None
    whatsapp_number: Optional[str] = None


class EmailSendResponse(BaseModel):
    success: bool
    message: str
    record_id: Optional[int] = None
    email_sent: bool = False
    email_status: str = "not_sent"
    recipient: Optional[str] = None
    attachment_filename: Optional[str] = None
    # Backwards-compatible aliases
    whatsapp_sent: bool = False
    whatsapp_status: str = "not_sent"
    whatsapp_error: Optional[str] = None


class WhatsAppSendResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    record_id: int
    whatsapp_sent: bool
    whatsapp_status: str
    whatsapp_message_id: Optional[str] = None
    whatsapp_error: Optional[str] = None
    email_sent: Optional[bool] = None


class PDFGenerateResponse(BaseModel):
    success: bool
    record_id: int
    pdf_generated: bool
    pdf_file_name: str
    pdf_generated_at: Optional[dt.datetime] = None

