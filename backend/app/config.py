from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://thesis:thesis@localhost:5432/thesis"
    sec_user_agent: str = ""
    refresh_seconds: int = Field(default=3600, ge=300)
    lease_seconds: int = Field(default=180, ge=30)
    max_attempts: int = Field(default=3, ge=1, le=10)
    openai_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"


settings = Settings()
