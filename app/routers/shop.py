from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.schemas.auth import ShopOut, ShopUpdate
from app.services.auth_service import get_current_user, get_current_user_shop

router = APIRouter(prefix="/shop", tags=["Shop"])


@router.get("", response_model=ShopOut)
def get_shop_details(
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop)
):
    """Retrieves current authenticated user's shop profile from database."""
    return shop


@router.put("", response_model=ShopOut)
def update_shop_details(
    shop_data: ShopUpdate,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Updates shop details (name, currency, timezone, phone, address, email)."""
    if shop_data.name is not None and shop_data.name.strip():
        shop.name = shop_data.name.strip()
    if shop_data.currency is not None and shop_data.currency.strip():
        shop.currency = shop_data.currency.strip().upper()
    if shop_data.timezone is not None and shop_data.timezone.strip():
        shop.timezone = shop_data.timezone.strip()
    if shop_data.phone is not None:
        shop.phone = shop_data.phone.strip()
    if shop_data.email is not None:
        shop.email = shop_data.email.strip()
    if shop_data.address is not None:
        shop.address = shop_data.address.strip()

    db.commit()
    db.refresh(shop)
    return shop
