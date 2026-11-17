from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")
    database_url: str = "postgresql+psycopg://thesis:thesis@localhost:5432/thesis"
    database_url_unpooled: str = ""
    sec_user_agent: str = ""
    alphavantage_api_key: str = ""
    calendar_refresh_hours: int = Field(default=24, ge=1)
    financial_refresh_hours: int = Field(default=1, ge=1)
    unknown_earnings_refresh_hours: int = Field(default=168, ge=24)
    earnings_lead_days: int = Field(default=0, ge=0, le=30)
    earnings_followup_days: int = Field(default=30, ge=1, le=90)
    refresh_seconds: int = Field(default=3600, ge=300)
    lease_seconds: int = Field(default=180, ge=30)
    max_attempts: int = Field(default=3, ge=1, le=10)
    openai_api_key: str = ""
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    production: bool = False
    app_origin: str = ""
    owner_password: str = ""
    resend_api_key: str = ""
    email_from: str = ""
    alert_email: str = ""
    llm_model: str = "gpt-4.1-mini"


settings = Settings()
