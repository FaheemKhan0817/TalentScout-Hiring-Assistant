from typing import List, Optional, Dict
from pydantic import BaseModel, EmailStr, Field

class Candidate(BaseModel):
    full_name: Optional[str] = Field(None, description="Candidate's full name")
    email: Optional[EmailStr] = Field(None, description="Candidate's email")
    phone: Optional[str] = Field(None, description="Candidate's phone number")
    years_experience: Optional[float] = Field(None, description="Years of relevant experience")
    desired_positions: Optional[List[str]] = Field(default=None, description="Target roles (e.g., Data Scientist, Backend Engineer)")
    current_location: Optional[str] = Field(None, description="Current city/country")
    tech_stack: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Declared tech stack grouped by categories: programming_languages, frameworks, databases, tools"
    )
    language_preference: Optional[str] = Field(None, description="Preferred language for the chat (e.g., English, Hindi)")
    consent_to_store: bool = Field(default=False, description="Consent flag for storing data")

REQUIRED_FIELDS = ["full_name", "email", "phone", "years_experience", "desired_positions", "current_location", "tech_stack"]

def missing_fields(cand: 'Candidate') -> List[str]:
    missing = []
    for f in REQUIRED_FIELDS:
        if getattr(cand, f) in (None, [], {}):
            missing.append(f)
    return missing
