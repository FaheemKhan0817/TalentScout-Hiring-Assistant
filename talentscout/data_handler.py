import os
import json
import time
from talentscout.logger import logger
import hashlib  # Add this import
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from .schema import Candidate
from .config import settings
from .logger import logger
from .security import redact_sensitive_data

class DataHandler:
    """Handle data storage with privacy and retention policies."""
    
    def __init__(self):
        self.data_dir = settings.data_dir
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _clean_expired_data(self):
        """Remove data older than retention period."""
        try:
            retention_date = datetime.now() - timedelta(days=settings.retention_days)
            for filename in os.listdir(self.data_dir):
                filepath = os.path.join(self.data_dir, filename)
                if os.path.isfile(filepath) and filename.endswith('.jsonl'):
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time < retention_date:
                        os.remove(filepath)
                        logger.info(f"Removed expired data file: {filename}")
        except Exception as e:
            logger.error(f"Error cleaning expired data: {e}")
    
    def store_candidate_data(self, candidate: Candidate, technical_qas: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Store candidate data with consent check and privacy protection."""
        if not candidate.consent_to_store:
            logger.info("Candidate did not consent to data storage")
            return None
            
        try:
            # Clean expired data periodically
            self._clean_expired_data()
            
            # Prepare record with redacted sensitive data
            record = {
                "timestamp": datetime.now().isoformat(),
                "candidate_id": f"candidate_{int(time.time())}",
                "full_name": candidate.full_name,
                "email_hash": self._hash_data(candidate.email) if candidate.email else None,
                "phone_hash": self._hash_data(candidate.phone) if candidate.phone else None,
                "years_experience": candidate.years_experience,
                "desired_positions": candidate.desired_positions,
                "current_location": candidate.current_location,
                "tech_stack": candidate.tech_stack,
                "questions": technical_qas.get("questions") if technical_qas else None
            }
            
            # Log with redacted data
            logger.info(f"Storing candidate data: {redact_sensitive_data(record)}")
            
            # Write to file
            filepath = os.path.join(self.data_dir, "candidates.jsonl")
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
            logger.info(f"Candidate data stored successfully: {record['candidate_id']}")
            return record['candidate_id']
            
        except Exception as e:
            logger.error(f"Failed to store candidate data: {e}")
            return None
    
    def _hash_data(self, data: str) -> str:
        """Hash sensitive data for privacy."""
        return hashlib.sha256(data.encode()).hexdigest()
    
    def load_candidate_data(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Load candidate data by ID."""
        try:
            filepath = os.path.join(self.data_dir, "candidates.jsonl")
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line)
                    if record.get("candidate_id") == candidate_id:
                        return record
            return None
        except Exception as e:
            logger.error(f"Failed to load candidate data: {e}")
            return None

# Global data handler instance
data_handler = DataHandler()