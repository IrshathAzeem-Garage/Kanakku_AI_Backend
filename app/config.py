from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "KANAKKU AI"
    BUSINESS_NAME: str = "Chellam Traders"
    API_V1_STR: str = "/api"
    
    # Security
    JWT_SECRET: str = "supersecret-kanakku-ai-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days session
    
    # Database: PostgreSQL ONLY (Supabase or local PostgreSQL)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/kanakku"
    )
    
    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ]
    
    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v):
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return v

    # AI / Vision Extraction
    AI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    AI_MODEL: str = "gemini-2.5-flash"
    
    # File storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 15
    
    # Timezone
    APP_TIMEZONE: str = "Asia/Kolkata"
    
    # Initial Admin Seed
    INITIAL_ADMIN_FULLNAME: str = "Mohamed Iqbal"
    INITIAL_ADMIN_USERNAME: str = "iqbal"
    INITIAL_ADMIN_EMAIL: str = "iqbal@chellamtraders.com"
    INITIAL_ADMIN_PASSWORD: str = "Chellam@2026"

    # Initial Shop Seed
    INITIAL_SHOP_NAME: str = "Chellam Traders"
    INITIAL_SHOP_CURRENCY: str = "INR"
    INITIAL_SHOP_TIMEZONE: str = "Asia/Kolkata"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def effective_ai_key(self) -> str:
        return self.AI_API_KEY or self.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")


settings = Settings()
