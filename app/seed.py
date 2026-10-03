from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.shop import Shop
from app.services.auth_service import get_password_hash
from app.utils.logger import logger


def ensure_initial_data():
    """Seeds the initial owner user and business shop if not present in the database."""
    db = SessionLocal()
    try:
        username = settings.INITIAL_ADMIN_USERNAME.strip()
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                fullname=settings.INITIAL_ADMIN_FULLNAME,
                email=settings.INITIAL_ADMIN_EMAIL,
                password_hash=get_password_hash(settings.INITIAL_ADMIN_PASSWORD),
                role="owner",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Initialized owner user in DB: {user.fullname} (@{user.username})")
        else:
            logger.info(f"Owner user '@{username}' already exists in DB.")

        # Ensure shop exists for owner
        shop = db.query(Shop).filter(Shop.owner_user_id == user.id).first()
        if not shop:
            shop = Shop(
                name=settings.INITIAL_SHOP_NAME,
                owner_user_id=user.id,
                currency=settings.INITIAL_SHOP_CURRENCY,
                timezone=settings.INITIAL_SHOP_TIMEZONE,
                email=user.email
            )
            db.add(shop)
            db.commit()
            db.refresh(shop)
            logger.info(f"Initialized shop in DB: '{shop.name}' for user @{user.username}")
        else:
            logger.info(f"Shop '{shop.name}' exists for user @{user.username}.")
            
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Executing standalone database seed...")
    ensure_initial_data()
    logger.info("Database seed completed successfully.")
