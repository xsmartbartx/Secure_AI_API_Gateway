import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Comma-separated list of valid client keys to access this gateway
    GATEWAY_API_KEYS: str = "sk_gateway_local_dev_secret_key"
    
    # Secret Upstream Provider Keys (Kept completely hidden from application clients)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    
    # Rate control config
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def valid_keys(self) -> List[str]:
        return [key.strip() for key in self.GATEWAY_API_KEYS.split(",") if key.strip()]

settings = Settings()