from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
from datetime import datetime


class ShopOut(BaseModel):
    id: int
    name: str
    owner_user_id: int
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ShopUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None


class UserLogin(BaseModel):
    username: str = Field(..., description="Username or mobile number")
    password: str = Field(..., min_length=4)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3)
    fullname: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    role: Optional[str] = "owner"


class UserUpdateProfile(BaseModel):
    fullname: Optional[str] = None
    email: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    fullname: str
    email: str
    role: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    shop: Optional[ShopOut] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    shop: Optional[ShopOut] = None


class TokenData(BaseModel):
    username: Optional[str] = None
