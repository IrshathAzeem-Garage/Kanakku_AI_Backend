from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.shop import Shop
from app.schemas.auth import UserLogin, Token, UserOut, UserUpdateProfile, ShopOut
from app.services.auth_service import (
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_shop
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username.strip()).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Fetch user's primary shop
    shop = db.query(Shop).filter(Shop.owner_user_id == user.id).first()
    
    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "shop": shop
    }


@router.get("/me", response_model=UserOut)
def read_current_user(
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop)
):
    """Returns authenticated user and associated shop from database."""
    user_out = UserOut.model_validate(current_user)
    user_out.shop = ShopOut.model_validate(shop) if shop else None
    return user_out


@router.put("/profile", response_model=UserOut)
def update_profile(
    profile_data: UserUpdateProfile,
    current_user: User = Depends(get_current_user),
    shop: Shop = Depends(get_current_user_shop),
    db: Session = Depends(get_db)
):
    """Updates user profile (fullname, email) in PostgreSQL database."""
    if profile_data.fullname is not None and profile_data.fullname.strip():
        current_user.fullname = profile_data.fullname.strip()
    
    if profile_data.email is not None and profile_data.email.strip():
        # Check if email is already taken by another user
        existing = db.query(User).filter(
            User.email == profile_data.email.strip(),
            User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already in use by another account."
            )
        current_user.email = profile_data.email.strip()

    if profile_data.whatsapp_number is not None:
        clean_num = profile_data.whatsapp_number.strip()
        current_user.whatsapp_number = clean_num if clean_num else None

    db.commit()
    db.refresh(current_user)
    
    user_out = UserOut.model_validate(current_user)
    user_out.shop = ShopOut.model_validate(shop) if shop else None
    return user_out

