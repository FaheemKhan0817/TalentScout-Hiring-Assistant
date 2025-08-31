import logging
import logging.handlers
import os
import sys
from .config import settings

def setup_logger():
    """Configure application logging with rotation and formatting."""
    logger = logging.getLogger("talentscout")
    logger.setLevel(getattr(logging, settings.log_level))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    # Set encoding to UTF-8 to handle Unicode characters
    if hasattr(console_handler, 'setEncoding'):
        console_handler.setEncoding('utf-8')
    logger.addHandler(console_handler)
    
    # File handler (if specified and not in cloud mode)
    if settings.log_file and not settings.is_cloud:
        os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file, maxBytes=10485760, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# Initialize logger
logger = setup_logger()