import hashlib
import re
import time
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from .config import settings

class RateLimiter:
    """Simple in-memory rate limiter for API calls."""
    def __init__(self):
        self.requests: Dict[str, float] = {}
    
    def check_rate_limit(self, identifier: str) -> bool:
        """Check if the identifier has exceeded the rate limit."""
        if not settings.enable_rate_limiting:
            return True
            
        current_time = time.time()
        window_start = current_time - settings.rate_limit_period
        
        # Clean old entries
        self.requests = {k: v for k, v in self.requests.items() if v > window_start}
        
        # Check current count
        request_times = [t for t in self.requests.values() if t > window_start]
        if len(request_times) >= settings.rate_limit_requests:
            return False
            
        # Record this request
        self.requests[identifier] = current_time
        return True

# Global rate limiter instance
rate_limiter = RateLimiter()

def redact_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive information from data before logging."""
    redacted = data.copy()
    sensitive_fields = ["email", "phone", "full_name"]
    
    for field in sensitive_fields:
        if field in redacted:
            if field == "email":
                redacted[field] = "***@***"
            elif field == "phone":
                redacted[field] = "***-***-****"
            elif field == "full_name":
                name_parts = redacted[field].split()
                if len(name_parts) > 1:
                    redacted[field] = f"{name_parts[0]} {'*' * len(name_parts[-1])}"
                else:
                    redacted[field] = "***"
    
    return redacted

def validate_input(input_str: str, input_type: str) -> bool:
    """Validate user input based on type."""
    if not input_str or not input_str.strip():
        return False
        
    if input_type == "email":
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, input_str) is not None
    elif input_type == "phone":
        pattern = r'^[\d\s\-\+\(\)]{10,}$'
        return re.match(pattern, input_str) is not None
    elif input_type == "name":
        return len(input_str.strip()) >= 2
    elif input_type == "experience":
        try:
            return float(input_str) >= 0
        except ValueError:
            return False
    
    return True