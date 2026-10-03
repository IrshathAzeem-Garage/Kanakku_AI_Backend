from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.timezone import get_current_time


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    fullname = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    whatsapp_number = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="owner", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)

    # Relationships
    shops = relationship("Shop", back_populates="owner", cascade="all, delete-orphan")
    records = relationship("DailyRecord", back_populates="user", cascade="all, delete-orphan")
