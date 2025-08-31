import os
import json
import logging
import datetime
import streamlit as st
from dotenv import load_dotenv
from talentscout.schema import Candidate, missing_fields
from talentscout.chains import build_parsers_chain, build_qgen_chain, build_assistant_reply_chain, build_sentiment_chain
from talentscout.utils import contains_exit, needs_question_generation, compact_history, extract_years_experience
from talentscout.data_handler import data_handler
from talentscout.security import validate_input, rate_limiter
from talentscout.config import settings
from talentscout.logger import logger

# Load environment variables
load_dotenv(override=True)

# Configure page
st.set_page_config(
    page_title="TalentScout Hiring Assistant", 
    page_icon="🧭", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced UI
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("talentscout/style.css")

# Initialize session state
def init_session_state():
    if "candidate" not in st.session_state:
        st.session_state.candidate = Candidate(consent_to_store=False)
    if "history" not in st.session_state:
        st.session_state.history = []
    if "qas" not in st.session_state:
        st.session_state.qas = None
    if "error_count" not in st.session_state:
        st.session_state.error_count = 0
    if "last_activity" not in st.session_state:
        st.session_state.last_activity = None
    if "conversation_step" not in st.session_state:
        st.session_state.conversation_step = "greeting"
    if "current_question_index" not in st.session_state:
        st.session_state.current_question_index = 0
    if "current_tech_index" not in st.session_state:
        st.session_state.current_tech_index = 0
    if "resume_processed" not in st.session_state:
        st.session_state.resume_processed = False

# Initialize session state
init_session_state()

# Create necessary directories if they don't exist
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Header with logo and title
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    st.image("https://img.icons8.com/color/96/000000/artificial-intelligence--v1.png", width=80)
with col2:
    st.markdown("<h1 style='text-align: center; color: #1E88E5;'>TalentScout Hiring Assistant</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #757575;'>AI-Powered Candidate Screening Platform</p>", unsafe_allow_html=True)
with col3:
    st.empty()

# Progress bar
def get_progress_percentage():
    steps = {
        "greeting": 0,
        "collect_info": 10,
        "collect_experience": 25,
        "collect_positions": 40,
        "collect_location": 55,
        "collect_tech_stack": 70,
        "generate_questions": 85,
        "ask_questions": 95,
        "conclusion": 100
    }
    return steps.get(st.session_state.conversation_step, 0)

progress = get_progress_percentage()
st.markdown(f"""
<div class="progress-container">
    <div class="progress-bar" style="width: {progress}%"></div>
    <div class="progress-text">{progress}% Complete</div>
</div>
""", unsafe_allow_html=True)

# Main content area
main_container = st.container()

# Configuration panel
with st.expander("⚙️ Configuration", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        model = st.text_input("Model", settings.model_name if hasattr(settings, 'model_name') else "openai/gpt-oss-120b")
    with col2:
        consent = st.checkbox("I consent to TalentScout storing my information for recruiting purposes.", value=False)
    st.markdown("""
    <div class="info-box">
        <p><strong>Privacy note:</strong> We minimize storage and mask sensitive fields. You can proceed without consent; your data won't be saved.</p>
    </div>
    """, unsafe_allow_html=True)

# Update consent in candidate record
st.session_state.candidate.consent_to_store = consent

# Build chains with error handling
try:
    parse_chain = build_parsers_chain()
    qgen_chain = build_qgen_chain()
    reply_chain = build_assistant_reply_chain()
    senti_chain = build_sentiment_chain()
    logger.info("Chains initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize chains: {e}")
    st.error("Failed to initialize the application. Please try again later.")
    st.stop()

# Define conversation steps
CONVERSATION_STEPS = {
    "greeting": "Hello! I'm TalentScout's assistant. I'll collect your basic details and tech stack, then ask a few tailored technical questions. You can type 'bye' to finish anytime.",
    "collect_info": "Could you please share your full name, email address, and phone number?",
    "collect_experience": "Thank you! Now, could you please share your years of experience in the industry?",
    "collect_positions": "Great! What position(s) are you interested in?",
    "collect_location": "Thank you! What is your current location?",
    "collect_tech_stack": "Please list your technical stack including programming languages, frameworks, databases, and tools.",
    "generate_questions": "I'm preparing some technical questions based on your tech stack. This will take just a moment.",
    "ask_questions": "I have some technical questions for you. Let's start with the first technology.",
    "conclusion": "Thank you for completing the screening! We'll review your details and reach out about next steps."
}

# Greeting on first load
if len(st.session_state.history) == 0:
    st.session_state.history.append({"user": "", "assistant": CONVERSATION_STEPS["greeting"]})
    st.session_state.conversation_step = "collect_info"

# Chat UI with enhanced styling
chat_container = st.container()
with chat_container:
    st.markdown('<div class="chat-header">Conversation</div>', unsafe_allow_html=True)
    
    # Create a scrollable container for chat messages
    chat_messages = st.container()
    with chat_messages:
        for turn in st.session_state.history:
            if turn["user"]:
                st.markdown(f"""
                <div class="chat-message user-message">
                    <div class="message-content">{turn["user"]}</div>
                    <div class="message-time">{datetime.datetime.now().strftime("%H:%M")}</div>
                </div>
                """, unsafe_allow_html=True)
            if turn["assistant"]:
                st.markdown(f"""
                <div class="chat-message bot-message">
                    <div class="message-content">{turn["assistant"]}</div>
                    <div class="message-time">{datetime.datetime.now().strftime("%H:%M")}</div>
                </div>
                """, unsafe_allow_html=True)

# Input area with enhanced styling
input_container = st.container()
with input_container:
    st.markdown('<div class="input-header">Your Response</div>', unsafe_allow_html=True)
    
    # Create a form for better input handling
    with st.form("input_form", clear_on_submit=True):
        user_input = st.text_area("Type your message here...", height=100, key="user_input")
        submitted = st.form_submit_button("Send")
        
        if submitted and user_input:
            # Update last activity
            st.session_state.last_activity = datetime.datetime.now()
            
            # Append user message
            st.session_state.history.append({"user": user_input, "assistant": ""})
            
            # Exit handling with logging
            exit_detected = contains_exit(user_input)
            logger.info(f"Exit condition check: {exit_detected} for input: '{user_input[:100]}...'")  # Truncate for logging
            
            if exit_detected:
                with st.chat_message("assistant"):
                    st.write(CONVERSATION_STEPS["conclusion"])
                st.session_state.history[-1]["assistant"] = CONVERSATION_STEPS["conclusion"]
                
                # Store candidate data if consented
                try:
                    candidate_id = data_handler.store_candidate_data(
                        st.session_state.candidate, 
                        st.session_state.qas
                    )
                    if candidate_id:
                        st.toast("Candidate record stored securely.", icon="✅")
                        logger.info(f"Conversation ended, candidate ID: {candidate_id}")
                except Exception as e:
                    logger.error(f"Failed to store candidate data: {e}")
                st.rerun()
            
            # Process based on conversation step
            current_step = st.session_state.conversation_step
            logger.info(f"Current conversation step: {current_step}")
            
            # Parse user input with validation
            try:
                # Validate input length - increase limit for technical answers
                max_length = 5000 if current_step == "ask_questions" else 1000
                if len(user_input) > max_length:
                    # For technical answers, just truncate with a warning
                    if current_step == "ask_questions":
                        user_input = user_input[:max_length]
                        st.warning("Your answer was truncated due to length limitations.")
                    else:
                        raise ValueError("Input too long")
                
                parsed = parse_chain.invoke({"message": user_input}) or {}
                logger.info(f"Parsed data: {parsed}")
                
                # Special handling for years of experience
                if current_step == "collect_experience" and not parsed.get("years_experience"):
                    # Try to extract years of experience using regex
                    years = extract_years_experience(user_input)
                    if years > 0:
                        parsed["years_experience"] = years
                        logger.info(f"Extracted years of experience: {years}")
                
                # Validate parsed fields
                if "email" in parsed and not validate_input(parsed["email"], "email"):
                    parsed.pop("email", None)
                    st.warning("Please provide a valid email address.")
                    
                if "phone" in parsed and not validate_input(parsed["phone"], "phone"):
                    parsed.pop("phone", None)
                    st.warning("Please provide a valid phone number.")
                    
                if "full_name" in parsed and not validate_input(parsed["full_name"], "name"):
                    parsed.pop("full_name", None)
                    st.warning("Please provide a valid name.")
                    
                if "years_experience" in parsed and not validate_input(str(parsed["years_experience"]), "experience"):
                    parsed.pop("years_experience", None)
                    st.warning("Please provide a valid number for years of experience.")
                    
            except Exception as e:
                logger.error(f"Failed to parse user input: {e}")
                parsed = {}
                st.session_state.error_count += 1
                
                # Reset conversation if too many errors
                if st.session_state.error_count > 3:
                    st.error("Too many errors. Please start over.")
                    st.session_state.clear()
                    init_session_state()
                    st.rerun()
            
            # Update candidate record with parsed data
            model_cand = st.session_state.candidate.model_dump()
            for k, v in parsed.items():
                if k == "desired_positions" and v and isinstance(v, list):
                    # Ensure we're working with lists
                    current_list = model_cand.get(k, []) or []
                    model_cand[k] = list(set(current_list + v))
                elif k == "tech_stack" and v and isinstance(v, dict):
                    # Handle tech stack dictionary
                    base = model_cand.get("tech_stack") or {}
                    for cat in ["programming_languages","frameworks","databases","tools"]:
                        base.setdefault(cat, [])
                        if v.get(cat) and isinstance(v.get(cat), list):
                            base[cat] = list(set(base[cat] + v[cat]))
                    model_cand[k] = base
                else:
                    model_cand[k] = v if v not in ("", [], {}) else model_cand.get(k)
            
            try:
                st.session_state.candidate = Candidate(**model_cand)
                logger.info(f"Updated candidate: {st.session_state.candidate.model_dump()}")
            except Exception as e:
                logger.error(f"Failed to update candidate: {e}")
                st.session_state.history[-1]["assistant"] = "I'm sorry, I couldn't process that. Please try again."
                st.rerun()
            
            # Determine next step based on current step and collected information
            missing = missing_fields(st.session_state.candidate)
            logger.info(f"Missing fields: {missing}")
            
            # State machine for conversation flow - more explicit step-by-step progression
            if current_step == "collect_info":
                # Check if we have the required information
                has_name = bool(st.session_state.candidate.full_name)
                has_email = bool(st.session_state.candidate.email)
                has_phone = bool(st.session_state.candidate.phone)
                
                if has_name and has_email and has_phone:
                    st.session_state.conversation_step = "collect_experience"
                    reply = CONVERSATION_STEPS["collect_experience"]
                else:
                    # Customized response based on what's missing
                    missing_parts = []
                    if not has_name:
                        missing_parts.append("full name")
                    if not has_email:
                        missing_parts.append("email address")
                    if not has_phone:
                        missing_parts.append("phone number")
                    
                    if len(missing_parts) == 3:
                        reply = CONVERSATION_STEPS["collect_info"]
                    else:
                        reply = f"Thank you! I still need your {', '.join(missing_parts)}. Could you please provide that?"
            
            elif current_step == "collect_experience":
                if st.session_state.candidate.years_experience is not None:
                    st.session_state.conversation_step = "collect_positions"
                    reply = CONVERSATION_STEPS["collect_positions"]
                else:
                    reply = "Could you please share your years of experience in the industry? You can provide a summary of your work history if that's easier."
            
            elif current_step == "collect_positions":
                # Even if positions were parsed from resume, we still need to confirm
                if st.session_state.candidate.desired_positions:
                    st.session_state.conversation_step = "collect_location"
                    reply = CONVERSATION_STEPS["collect_location"]
                else:
                    reply = "What position(s) are you interested in?"
            
            elif current_step == "collect_location":
                # Even if location was parsed from resume, we still need to confirm
                if st.session_state.candidate.current_location:
                    st.session_state.conversation_step = "collect_tech_stack"
                    reply = CONVERSATION_STEPS["collect_tech_stack"]
                else:
                    reply = "What is your current location?"
            
            elif current_step == "collect_tech_stack":
                # Even if tech stack was parsed from resume, we still need to confirm
                if st.session_state.candidate.tech_stack and any(st.session_state.candidate.tech_stack.values()):
                    st.session_state.conversation_step = "generate_questions"
                    reply = CONVERSATION_STEPS["generate_questions"]
                    
                    # Generate technical questions
                    try:
                        st.session_state.qas = qgen_chain.invoke({
                            "tech_stack": json.dumps(st.session_state.candidate.tech_stack, ensure_ascii=False)
                        })
                        logger.info(f"Generated questions for tech stack: {st.session_state.candidate.tech_stack}")
                        
                        # Move to asking questions
                        st.session_state.conversation_step = "ask_questions"
                        st.session_state.current_tech_index = 0
                        st.session_state.current_question_index = 0
                        
                        # Show first question
                        if st.session_state.qas and st.session_state.qas.get("questions"):
                            first_topic = st.session_state.qas["questions"][0].get("topic", "your technology")
                            first_question = st.session_state.qas["questions"][0].get("questions", [""])[0]
                            reply = f"I have prepared some technical questions for you. Let's start with **{first_topic}**: {first_question}"
                    except Exception as e:
                        logger.error(f"Failed to generate questions: {e}")
                        st.session_state.qas = None
                        reply = "I'm having trouble generating questions right now. Let's try again later."
                else:
                    reply = "Please list your technical stack including programming languages, frameworks, databases, and tools."
            
            elif current_step == "ask_questions":
                # Handle question answers
                if st.session_state.qas and st.session_state.qas.get("questions"):
                    # Store the answer (in a real implementation, you would save this)
                    # For now, just move to the next question
                    
                    # Get current question info
                    questions = st.session_state.qas["questions"]
                    current_tech_index = st.session_state.current_tech_index
                    current_question_index = st.session_state.current_question_index
                    
                    # Get the current question for reference
                    current_topic = questions[current_tech_index].get("topic", "your technology")
                    current_question = questions[current_tech_index].get("questions", [""])[current_question_index]
                    
                    # Log the answer (truncated if needed)
                    answer_preview = user_input[:100] + "..." if len(user_input) > 100 else user_input
                    logger.info(f"Answer received for {current_topic} question: {answer_preview}")
                    
                    # Move to next question
                    current_question_index += 1
                    
                    # Check if we need to move to next technology
                    if current_question_index >= len(questions[current_tech_index].get("questions", [])):
                        current_question_index = 0
                        current_tech_index += 1
                        
                        # Check if we've asked all questions
                        if current_tech_index >= len(questions):
                            # All questions asked, conclude
                            st.session_state.conversation_step = "conclusion"
                            reply = CONVERSATION_STEPS["conclusion"]
                        else:
                            # Move to next technology
                            next_topic = questions[current_tech_index].get("topic", "your technology")
                            next_question = questions[current_tech_index].get("questions", [""])[0]
                            reply = f"Thank you for your answer about {current_topic}! Now let's talk about **{next_topic}**: {next_question}"
                    else:
                        # Next question for current technology
                        next_question = questions[current_tech_index].get("questions", [])[current_question_index]
                        reply = f"Thank you! Next question about **{current_topic}**: {next_question}"
                    
                    # Update question indices
                    st.session_state.current_tech_index = current_tech_index
                    st.session_state.current_question_index = current_question_index
                else:
                    reply = "I don't have any questions to ask right now."
            
            else:
                # Default fallback
                reply = "I'm not sure what to do next. Could you please clarify?"
            
            # Update the conversation history
            st.session_state.history[-1]["assistant"] = reply
            st.rerun()

# Sidebar with enhanced styling
with st.sidebar:
    st.markdown('<div class="sidebar-header">Dashboard</div>', unsafe_allow_html=True)
    
    # Candidate info card
    st.markdown('<div class="info-card">Candidate Information</div>', unsafe_allow_html=True)
    
    # Display candidate info
    candidate = st.session_state.candidate
    if candidate.full_name:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Name:</span>
                <span class="field-value">{candidate.full_name}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if candidate.email:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Email:</span>
                <span class="field-value">{candidate.email}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if candidate.phone:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Phone:</span>
                <span class="field-value">{candidate.phone[:3]}***-{candidate.phone[-4:] if len(candidate.phone) >= 4 else candidate.phone}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if candidate.years_experience is not None:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Experience:</span>
                <span class="field-value">{candidate.years_experience} years</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if candidate.desired_positions:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Position:</span>
                <span class="field-value">{', '.join(candidate.desired_positions)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    if candidate.current_location:
        st.markdown(f"""
        <div class="candidate-info">
            <div class="candidate-field">
                <span class="field-label">Location:</span>
                <span class="field-value">{candidate.current_location}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Tech stack display
    if candidate.tech_stack and any(candidate.tech_stack.values()):
        st.markdown('<div class="tech-stack-header">Tech Stack</div>', unsafe_allow_html=True)
        
        for category, techs in candidate.tech_stack.items():
            if techs:
                category_name = category.replace('_', ' ').title()
                st.markdown(f"""
                <div class="tech-category">
                    <div class="category-name">{category_name}</div>
                    <div class="tech-badges">
                        {"".join([f'<span class="tech-badge">{tech}</span>' for tech in techs])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    # Data controls
    st.markdown('<div class="controls-header">Controls</div>', unsafe_allow_html=True)
    
    if st.button("💾 Save Data", key="save_button"):
        try:
            candidate_id = data_handler.store_candidate_data(
                st.session_state.candidate, 
                st.session_state.qas
            )
            if candidate_id:
                st.success(f"Saved to data/candidates.jsonl")
                logger.info(f"Manual save triggered for candidate: {candidate_id}")
            else:
                st.info("Not saved (no consent). Toggle consent to allow storage.")
        except Exception as e:
            logger.error(f"Failed to save candidate record: {e}")
            st.error("Failed to save candidate record.")
    
    if st.button("🔄 Reset Session", key="reset_button"):
        st.session_state.clear()
        init_session_state()
        st.rerun()
    
    # Session info
    st.markdown('<div class="session-header">Session Info</div>', unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="session-info">
        <div class="session-field">
            <span class="field-label">Current Step:</span>
            <span class="field-value">{st.session_state.conversation_step.replace('_', ' ').title()}</span>
        </div>
        <div class="session-field">
            <span class="field-label">Errors:</span>
            <span class="field-value">{st.session_state.error_count}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.last_activity:
        last_activity = st.session_state.last_activity.strftime("%H:%M:%S")
        st.markdown(f"""
        <div class="session-info">
            <div class="session-field">
                <span class="field-label">Last Activity:</span>
                <span class="field-value">{last_activity}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

# Footer
st.markdown("""
<div class="footer">
    <p>© 2025 TalentScout Hiring Assistant. All rights reserved.</p>
    <p>Built with ❤️ using LangChain + Groq</p>
</div>
""", unsafe_allow_html=True)