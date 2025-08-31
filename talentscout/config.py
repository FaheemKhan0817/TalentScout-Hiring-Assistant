import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # API Configuration
    groq_api_key: Optional[str] = Field(None, env="GROQ_API_KEY")
    model_name: str = Field("llama3-70b-8192", env="MODEL_NAME")
    model_temperature: float = Field(0.2, env="MODEL_TEMPERATURE")
    
    # Data Storage
    data_dir: str = Field("data", env="DATA_DIR")
    
    # Security
    enable_rate_limiting: bool = Field(True, env="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(10, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(60, env="RATE_LIMIT_PERIOD")  # seconds
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE")
    
    # Privacy
    retention_days: int = Field(90, env="RETENTION_DAYS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()