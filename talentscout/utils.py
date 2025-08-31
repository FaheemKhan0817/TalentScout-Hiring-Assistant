import json
import os
import re
import time
import datetime
from typing import Dict, Any, List
from .schema import Candidate, missing_fields

# Updated exit keywords - removed "thank you" and "thanks" to avoid false positives
EXIT_KEYWORDS = {"exit", "quit", "bye", "goodbye", "stop", "end"}

def contains_exit(text: str) -> bool:
    """
    Check if the user wants to exit the conversation.
    More precise detection to avoid false positives.
    """
    t = (text or "").strip().lower()
    
    # Only match whole words, not substrings
    words = re.findall(r'\b\w+\b', t)
    
    # Check for exact matches of exit keywords
    return any(kw in words for kw in EXIT_KEYWORDS)

def extract_years_experience(text: str) -> float:
    """
    Extract years of experience from text using regex patterns.
    Returns a float representing the years of experience.
    """
    # Pattern for explicit years of experience statements
    patterns = [
        r'(\d+(?:\.\d+)?)\s*years?\s*(?:of\s*)?experience',
        r'experience\s*:\s*(\d+(?:\.\d+)?)',
        r'(\d+)\s*\+\s*years',
        r'over\s*(\d+(?:\.\d+)?)\s*years',
        r'more\s*than\s*(\d+(?:\.\d+)?)\s*years',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    
    # If no explicit mention, try to calculate from work history
    # Look for date ranges in work experience
    date_patterns = [
        r'(\d{4})\s*–\s*(\d{4})',  # 2020 – 2023
        r'(\d{4})\s*-\s*(\d{4})',  # 2020-2023
        r'(\d{4})\s*to\s*(\d{4})', # 2020 to 2023
        r'(\w{3}\s*\d{4})\s*–\s*(\w{3}\s*\d{4})',  # Jan 2020 – Dec 2023
        r'(\w{3}\s*\d{4})\s*-\s*(\w{3}\s*\d{4})',  # Jan 2020 - Dec 2023
    ]
    
    total_years = 0
    current_year = datetime.datetime.now().year
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                if len(match) == 2:  # Two dates found
                    start_year = int(re.search(r'\d{4}', match[0]).group())
                    end_year = int(re.search(r'\d{4}', match[1]).group())
                    
                    # If end year is in the future, use current year
                    if end_year > current_year:
                        end_year = current_year
                    
                    years = end_year - start_year
                    if years > 0:
                        total_years += years
            except (ValueError, AttributeError):
                continue
    
    # If we found some years from work history, return it
    if total_years > 0:
        return min(total_years, 50)  # Cap at 50 years to be realistic
    
    return 0.0  # Default if no experience found

def extract_tech_stack(text: str) -> Dict[str, List[str]]:
    """
    Extract tech stack information from text.
    Returns a dictionary with categories: programming_languages, frameworks, databases, tools.
    """
    # Common technologies by category
    programming_languages = [
        'python', 'java', 'javascript', 'typescript', 'c', 'c++', 'c#', 'ruby', 'php', 'swift', 'kotlin',
        'go', 'rust', 'scala', 'r', 'matlab', 'sql', 'html', 'css', 'bash', 'powershell'
    ]
    
    frameworks = [
        'react', 'angular', 'vue', 'django', 'flask', 'spring', 'express', 'node.js', 'asp.net',
        'ruby on rails', 'laravel', 'symfony', 'tensorflow', 'pytorch', 'keras', 'scikit-learn',
        'pandas', 'numpy', 'matplotlib', 'seaborn', 'spark', 'hadoop', 'flink'
    ]
    
    databases = [
        'mysql', 'postgresql', 'mongodb', 'sqlite', 'oracle', 'redis', 'cassandra', 'dynamodb',
        'firebase', 'elasticsearch', 'neo4j', 'influxdb', 'couchdb'
    ]
    
    tools = [
        'git', 'docker', 'kubernetes', 'jenkins', 'aws', 'azure', 'gcp', 'terraform', 'ansible',
        'jira', 'confluence', 'slack', 'ci/cd', 'agile', 'scrum', 'jupyter', 'tableau', 'power bi'
    ]
    
    # Initialize result
    result = {
        'programming_languages': [],
        'frameworks': [],
        'databases': [],
        'tools': []
    }
    
    # Convert text to lowercase for matching
    text_lower = text.lower()
    
    # Extract programming languages
    for lang in programming_languages:
        if re.search(r'\b' + re.escape(lang) + r'\b', text_lower):
            result['programming_languages'].append(lang)
    
    # Extract frameworks
    for framework in frameworks:
        if re.search(r'\b' + re.escape(framework) + r'\b', text_lower):
            result['frameworks'].append(framework)
    
    # Extract databases
    for db in databases:
        if re.search(r'\b' + re.escape(db) + r'\b', text_lower):
            result['databases'].append(db)
    
    # Extract tools
    for tool in tools:
        if re.search(r'\b' + re.escape(tool) + r'\b', text_lower):
            result['tools'].append(tool)
    
    return result

def redact_phone(phone: str | None) -> str | None:
    if not phone: 
        return phone
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 10:
        return f"***-***-{digits[-4:]}"
    return "***"

def safe_store(candidate: Candidate, technical_qas: Dict[str, Any] | None, base_dir: str) -> str | None:
    """
    Store minimal candidate info (with consent) into a jsonl file.
    """
    if not candidate.consent_to_store:
        return None
    os.makedirs(base_dir, exist_ok=True)
    record = {
        "ts": int(time.time()),
        "full_name": candidate.full_name,
        "email": candidate.email,
        "phone": redact_phone(candidate.phone),
        "years_experience": candidate.years_experience,
        "desired_positions": candidate.desired_positions,
        "current_location": candidate.current_location,
        "tech_stack": candidate.tech_stack,
        "questions": technical_qas.get("questions") if technical_qas else None
    }
    path = os.path.join(base_dir, "candidates.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path

def needs_question_generation(cand: Candidate, qas: Dict[str, Any] | None) -> bool:
    if cand.tech_stack and not (qas and qas.get("questions")):
        return True
    return False

def compact_history(history: List[Dict[str, str]], max_chars: int = 3000) -> str:
    text = "\n".join([f"User: {h['user']}\nAssistant: {h['assistant']}" for h in history])
    return text[-max_chars:]