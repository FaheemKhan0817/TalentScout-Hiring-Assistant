import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings, Field

class Settings(BaseSettings):
    # API Configuration
    groq_api_key: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    model_name: str = Field(default="llama3-70b-8192", env="MODEL_NAME")
    model_temperature: float = Field(default=0.2, env="MODEL_TEMPERATURE")
    
    # Data Storage
    data_dir: str = Field(default="data", env="DATA_DIR")
    
    # Security
    enable_rate_limiting: bool = Field(default=True, env="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(default=10, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="RATE_LIMIT_PERIOD")  # seconds
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # Privacy
    retention_days: int = Field(default=90, env="RETENTION_DAYS")
    
    # Streamlit Cloud specific settings
    is_cloud: bool = Field(default=False, env="IS_CLOUD")
    
    class Config:
        env_file = None  # Disable .env file for cloud deployment
        case_sensitive = False
        extra = "allow"  # Allow extra fields for flexibility

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Detect if we're running on Streamlit Cloud
        # This can be set via environment variable in Streamlit Cloud
        if os.getenv("IS_CLOUD", "false").lower() in ("true", "1", "yes"):
            self.is_cloud = True
        
        # For cloud deployment, ensure we have a data directory
        if self.is_cloud:
            os.makedirs(self.data_dir, exist_ok=True)

# Global settings instance
settings = Settings()