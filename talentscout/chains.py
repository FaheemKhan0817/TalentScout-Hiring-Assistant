import os
import json
import re
import logging
from typing import Any, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from .prompts import (
    PARSE_TO_CANDIDATE,
    TECH_QUESTION_PROMPT,
    ASSISTANT_REPLY_PROMPT,
    SENTIMENT_PROMPT,
)
from .config import settings
from .logger import logger
from .security import rate_limiter

# ------------------------------------------------------------------
# Groq LLM Factory with Retry
# ------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=lambda _: logger.warning("Retrying LLM call due to failure")
)
def make_llm(model: Optional[str] = None, temperature: Optional[float] = None) -> ChatGroq:
    """Initialize Groq LLM with retry on failure."""
    try:
        llm = ChatGroq(
            model=model or settings.model_name,
            temperature=temperature if temperature is not None else settings.model_temperature,
            max_tokens=None,
            api_key=settings.groq_api_key,
        )
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        raise

# ------------------------------------------------------------------
# JSON Parser + Safe Fallback
# ------------------------------------------------------------------
def safe_json_parse(text: str) -> Dict[str, Any]:
    """
    Parse JSON with two fallbacks:
    1. Regex extraction of JSON-like block
    2. Return empty dict if still invalid
    """
    # Clean leading/trailing backticks or markdown
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Try to fix common JSON issues
    # Replace single quotes with double quotes
    text = text.replace("'", '"')
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed: {e}. Attempting regex fallback.")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                json_str = match.group()
                # Replace single quotes with double quotes again
                json_str = json_str.replace("'", '"')
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
    logger.error("All JSON parsing attempts failed, returning empty dict.")
    return {}

def json_parser() -> RunnableLambda:
    """Return a runnable that safely parses JSON."""
    return RunnableLambda(safe_json_parse)

# ------------------------------------------------------------------
# Chains with Rate Limiting
# ------------------------------------------------------------------
def build_parsers_chain(llm=None):
    """Build chain for parsing candidate information with rate limiting."""
    llm = llm or make_llm()
    def parse_with_rate_limit(inputs):
        if not rate_limiter.check_rate_limit("parse_chain"):
            raise Exception("Rate limit exceeded for parsing chain")
        message = inputs.get("message", "")
        formatted_inputs = {"message": message}
        try:
            chain = PARSE_TO_CANDIDATE | llm | StrOutputParser() | json_parser()
            return chain.invoke(formatted_inputs)
        except Exception as e:
            logger.error(f"Error in parse chain: {e}")
            return {}
    return RunnableLambda(parse_with_rate_limit)

def build_qgen_chain(llm=None):
    """Generate technical questions with JSON mode & fallback."""
    llm = llm or make_llm()
    def qgen_with_rate_limit(inputs):
        if not rate_limiter.check_rate_limit("qgen_chain"):
            raise Exception("Rate limit exceeded for question generation chain")
        try:
            # Force JSON mode via response_format
            llm_json = ChatGroq(
                model=settings.model_name,
                temperature=0.2,
                max_tokens=1500,
                api_key=settings.groq_api_key,
                response_format={"type": "json_object"}
            )
            # Fix the prompt template issue
            fixed_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a JSON generator. Output **only** valid JSON. No markdown, no explanations."),
                ("user", """
Tech stack JSON:
{tech_stack}
Generate exactly 3 concise questions per technology. Output JSON:
{{"questions":[{{"topic":"<tech>","questions":["q1","q2","q3"]}}]}}
""")
            ])
            chain = fixed_prompt | llm_json | StrOutputParser() | json_parser()
            result = chain.invoke(inputs)
            if result and result.get("questions"):
                return result
            # Fallback: manual template
            return fallback_questions(inputs.get("tech_stack", "{}"))
        except Exception as e:
            logger.error(f"LLM JSON failed, using fallback: {e}")
            return fallback_questions(inputs.get("tech_stack", "{}"))
    return RunnableLambda(qgen_with_rate_limit)

# ------------------------------------------------------------------
# Fallback Question Generator (100% reliable)
# ------------------------------------------------------------------
def fallback_questions(tech_json_str: str) -> Dict[str, Any]:
    """Guaranteed questions even if LLM fails."""
    try:
        tech = json.loads(tech_json_str)
    except:
        tech = {}
    
    questions = []
    
    # Flatten all technologies
    all_techs = []
    for category in ["programming_languages", "frameworks", "databases", "tools"]:
        all_techs.extend(tech.get(category, []))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_techs = [t for t in all_techs if not (t in seen or seen.add(t))]
    
    # Generate questions for each unique technology
    for tech_name in unique_techs[:5]:  # Limit to 5 technologies
        questions.append({
            "topic": tech_name,
            "questions": [
                f"Describe your experience with {tech_name}.",
                f"What are the key features of {tech_name}?",
                f"How do you debug issues in {tech_name}?",
                f"Give an example project using {tech_name}."
            ]
        })
    
    # If no technologies found, provide generic questions
    if not questions:
        questions = [{
            "topic": "Your Experience",
            "questions": [
                "Describe your most challenging project.",
                "How do you approach learning new technologies?",
                "What's your experience with team collaboration?",
                "How do you ensure code quality?"
            ]
        }]
    
    return {"questions": questions}

def build_assistant_reply_chain(llm=None):
    """Build chain for generating assistant replies with rate limiting."""
    llm = llm or make_llm()
    def reply_with_rate_limit(inputs):
        if not rate_limiter.check_rate_limit("reply_chain"):
            raise Exception("Rate limit exceeded for reply chain")
        try:
            chain = ASSISTANT_REPLY_PROMPT | llm | StrOutputParser()
            return chain.invoke(inputs)
        except Exception as e:
            logger.error(f"Error in reply chain: {e}")
            return "I'm sorry, I'm having trouble responding right now. Please try again."
    return RunnableLambda(reply_with_rate_limit)

def build_sentiment_chain(llm=None):
    """Build chain for sentiment analysis with rate limiting."""
    llm = llm or make_llm(temperature=0.0)
    def sentiment_with_rate_limit(inputs):
        if not rate_limiter.check_rate_limit("sentiment_chain"):
            raise Exception("Rate limit exceeded for sentiment chain")
        try:
            chain = SENTIMENT_PROMPT | llm | StrOutputParser()
            result = chain.invoke(inputs).strip().lower()
            return result if result in {"positive", "neutral", "negative"} else "neutral"
        except Exception as e:
            logger.error(f"Error in sentiment chain: {e}")
            return "neutral"
    return RunnableLambda(sentiment_with_rate_limit)