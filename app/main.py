import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.database import get_db
from app.routers import auth, shop, dashboard, records, reports
from app.seed import ensure_initial_data
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Attempt seeding if tables already exist via Alembic
    try:
        ensure_initial_data()
    except Exception as e:
        logger.warning(f"Startup seed skipped (run 'alembic upgrade head' first): {e}")

    # Safe validation of Gmail environment variables on startup (never logs secrets)
    required_email_vars = ["GMAIL_USER", "GMAIL_APP_PASSWORD", "REPORT_EMAIL"]
    missing_vars = [key for key in required_email_vars if not (getattr(settings, key, "") or os.getenv(key, "")).strip()]
    if missing_vars:
        logger.warning(
            f"Gmail email service is not configured. Missing environment variable(s): {', '.join(missing_vars)}"
        )
    else:
        logger.info("Gmail SMTP configuration detected and loaded from runtime environment.")

    yield



app = FastAPI(
    title=settings.PROJECT_NAME,
    description="PostgreSQL-backed Digital Accounting / Kanakku AI system",
    version="1.2.0",
    lifespan=lifespan
)

# CORS configuration
origins = settings.CORS_ORIGINS
if isinstance(origins, str):
    origins = [origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images statically
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# Cold-start wake up and database connectivity health endpoint
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint verifying backend liveness and PostgreSQL connectivity.
    Never exposes database credentials in the response.
    """
    db_status = "unavailable"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.warning(f"PostgreSQL connectivity check error: {e}")

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "service": "kanakku-ai",
        "database": db_status
    }


# Include Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(shop.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(records.router, prefix=settings.API_V1_STR)
app.include_router(reports.router, prefix=settings.API_V1_STR)
