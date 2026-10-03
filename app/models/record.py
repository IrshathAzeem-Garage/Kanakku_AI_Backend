from sqlalchemy import Column, Integer, Numeric, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from app.utils.timezone import get_current_time


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    record_date = Column(Date, index=True, nullable=False)
    
    # Financial summaries strictly stored as PostgreSQL NUMERIC(12, 2)
    total_customer_money = Column(Numeric(12, 2), default=0.00, nullable=False)
    total_digital_money = Column(Numeric(12, 2), default=0.00, nullable=False)
    total_cash_received = Column(Numeric(12, 2), default=0.00, nullable=False)
    
    total_expenses = Column(Numeric(12, 2), default=0.00, nullable=False)
    total_own_money = Column(Numeric(12, 2), default=0.00, nullable=False)
    total_cash_box_expenses = Column(Numeric(12, 2), default=0.00, nullable=False)
    
    in_hand_money = Column(Numeric(12, 2), default=0.00, nullable=False)
    
    # Audit & Image handling
    image_url = Column(String(500), nullable=True)
    image_hash = Column(String(64), index=True, nullable=True)  # SHA-256
    notes = Column(Text, nullable=True)

    # PDF & WhatsApp Delivery Metadata
    pdf_generated_at = Column(DateTime, nullable=True)
    pdf_file_name = Column(String(255), nullable=True)
    whatsapp_status = Column(String(50), nullable=True, default="not_sent")  # not_sent, pending, sent, delivered, failed
    whatsapp_message_id = Column(String(255), nullable=True)
    whatsapp_sent_at = Column(DateTime, nullable=True)
    whatsapp_error = Column(Text, nullable=True)
    
    # Email Delivery Aliases (Reusing delivery tracking columns without breaking DB schema)
    @property
    def email_status(self):
        return self.whatsapp_status

    @property
    def email_sent_at(self):
        return self.whatsapp_sent_at

    @property
    def email_error(self):
        return self.whatsapp_error
    
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)

    # Relationships
    shop = relationship("Shop", back_populates="records")
    user = relationship("User", back_populates="records")
    customer_receipts = relationship("CustomerReceipt", back_populates="record", cascade="all, delete-orphan", order_by="CustomerReceipt.id")
    digital_entries = relationship("DigitalEntry", back_populates="record", cascade="all, delete-orphan", order_by="DigitalEntry.id")
    expenses = relationship("Expense", back_populates="record", cascade="all, delete-orphan", order_by="Expense.id")


class CustomerReceipt(Base):
    __tablename__ = "customer_receipts"

    id = Column(Integer, primary_key=True, index=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_type = Column(String(20), default="UNKNOWN")  # CASH, DIGITAL, UNKNOWN
    description = Column(String(255), nullable=True)
    raw_text = Column(String(255), nullable=True)
    source_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_current_time)

    record = relationship("DailyRecord", back_populates="customer_receipts")


class DigitalEntry(Base):
    __tablename__ = "digital_entries"

    id = Column(Integer, primary_key=True, index=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    raw_text = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_current_time)

    record = relationship("DailyRecord", back_populates="digital_entries")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    own_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    cash_box_amount = Column(Numeric(12, 2), default=0.00, nullable=False)
    raw_text = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_current_time)

    record = relationship("DailyRecord", back_populates="expenses")
