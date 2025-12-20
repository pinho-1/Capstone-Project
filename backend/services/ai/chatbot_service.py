"""
Chatbot AI Service with Function Calling
Handles all chatbot AI interactions including:
- Job application tracking
- Company research (web search)
- General job advice
- Content generation (cover letters, LinkedIn summaries)
"""

import google.generativeai as genai
from typing import Dict, List, Any, Optional
import json
import os
from datetime import datetime, timedelta

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# System prompt for the chatbot
CHATBOT_SYSTEM_PROMPT = """You are Talentum's AI Career Assistant, a helpful and friendly job search companion.

Your capabilities:
1. **Track Job Applications**: Help users track their applications, set follow-up reminders
2. **Research Companies**: Search the web for company info, interview processes, salaries, culture
3. **Answer Job Search Questions**: Provide advice on negotiation, etiquette, application strategy
4. **Generate Content**: Create cover letters, LinkedIn summaries, outreach messages based on their CV

Guidelines:
- Be conversational, supportive, and encouraging
- When users ask about their CV or profile, use the context provided
- Suggest proactive next steps
- If you need to use a tool/function, explain what you're doing
- Keep responses concise but helpful (2-4 sentences unless explaining something complex)
- Use emojis sparingly and naturally

When users want to track an application, use the track_application function.
When users ask about companies or need research, use the web_search function.
For content generation, use the appropriate generation functions.
"""

# Available tools/functions
CHATBOT_TOOLS = [
    {
        "name": "track_application",
        "description": "Track a new job application with company, role, and date. Use this when user says they applied to a job or wants to track an application.",
        "parameters": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "The company name"
                },
                "role": {
                    "type": "string",
                    "description": "The job title/role"
                },
                "applied_date": {
                    "type": "string",
                    "description": "When they applied (e.g., 'today', '2024-12-19', 'yesterday')"
                },
                "job_url": {
                    "type": "string",
                    "description": "URL to the job posting if mentioned"
                },
                "notes": {
                    "type": "string",
                    "description": "Any additional notes about the application"
                }
            },
            "required": ["company", "role"]
        }
    },
    {
        "name": "list_applications",
        "description": "Show all tracked job applications for the user",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "update_application_status",
        "description": "Update the status of a job application (e.g., moved to interview, rejected, got offer)",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "The ID of the application to update"
                },
                "new_status": {
                    "type": "string",
                    "enum": ["applied", "interview", "rejected", "offer", "accepted"],
                    "description": "The new status"
                }
            },
            "required": ["application_id", "new_status"]
        }
    },
    {
        "name": "set_follow_up_reminder",
        "description": "Set a follow-up reminder for a job application",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "The ID of the application"
                },
                "days_from_now": {
                    "type": "integer",
                    "description": "How many days from now to follow up (default 14)"
                }
            },
            "required": ["application_id"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for information about companies, salaries, interview processes, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_cover_letter",
        "description": "Generate a cover letter based on the user's CV and a job description",
        "parameters": {
            "type": "object",
            "properties": {
                "job_description": {
                    "type": "string",
                    "description": "The job description or key requirements"
                },
                "tone": {
                    "type": "string",
                    "enum": ["professional", "enthusiastic", "conversational"],
                    "description": "The tone of the cover letter"
                }
            },
            "required": ["job_description"]
        }
    },
    {
        "name": "generate_linkedin_summary",
        "description": "Generate a LinkedIn summary/about section based on the user's CV",
        "parameters": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What to emphasize (e.g., 'data science', 'leadership', 'technical skills')"
                }
            }
        }
    }
]


async def get_chatbot_response(
    user_message: str,
    chat_history: List[Dict[str, str]],
    user_cv_text: Optional[str] = None,
    user_context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Generate a chatbot response using Gemini with function calling.
    
    Args:
        user_message: The user's message
        chat_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
        user_cv_text: Optional CV text for context
        user_context: Optional dict with user info (name, job applications, etc.)
    
    Returns:
        Dict with:
        - response: The assistant's text response
        - function_call: Optional function call dict if the model wants to use a tool
        - tool_name: Name of the tool if function_call exists
    """
    
    # Build context
    context_parts = [CHATBOT_SYSTEM_PROMPT]
    
    if user_cv_text:
        context_parts.append(f"\n\n**User's CV Context:**\n{user_cv_text[:2000]}")  # First 2000 chars
    
    if user_context:
        context_parts.append(f"\n\n**User Context:**\n{json.dumps(user_context, indent=2)}")
    
    system_prompt = "\n".join(context_parts)
    
    # Build conversation history
    messages = []
    
    # Add system context as first message
    messages.append({
        "role": "user",
        "parts": [system_prompt]
    })
    messages.append({
        "role": "model",
        "parts": ["I understand. I'm ready to help as Talentum's Career Assistant!"]
    })
    
    # Add chat history
    for msg in chat_history[-10:]:  # Last 10 messages to avoid token limits
        role = "model" if msg["role"] == "assistant" else "user"
        messages.append({
            "role": role,
            "parts": [msg["content"]]
        })
    
    # Add current message
    messages.append({
        "role": "user",
        "parts": [user_message]
    })
    
    # Create model with function calling
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        tools=CHATBOT_TOOLS
    )
    
    try:
        # Generate response
        response = model.generate_content(messages)
        
        # Check if model wants to call a function
        if response.candidates[0].content.parts[0].function_call:
            function_call = response.candidates[0].content.parts[0].function_call
            return {
                "response": None,
                "function_call": {
                    "name": function_call.name,
                    "args": dict(function_call.args)
                },
                "tool_name": function_call.name
            }
        
        # Regular text response
        return {
            "response": response.text,
            "function_call": None,
            "tool_name": None
        }
        
    except Exception as e:
        print(f"Chatbot error: {e}")
        return {
            "response": "I apologize, but I encountered an error. Could you try rephrasing your question?",
            "function_call": None,
            "tool_name": None
        }


async def generate_cover_letter_content(cv_text: str, job_description: str, tone: str = "professional") -> str:
    """Generate a cover letter based on CV and job description."""
    
    prompt = f"""Generate a {tone} cover letter based on this CV and job description.

CV:
{cv_text[:1500]}

Job Description:
{job_description}

Guidelines:
- Keep it to 3-4 paragraphs
- Highlight relevant experience from the CV
- Show enthusiasm for the role
- Professional but personable tone
- End with a call to action

Generate the cover letter:"""

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text


async def generate_linkedin_summary_content(cv_text: str, focus: Optional[str] = None) -> str:
    """Generate a LinkedIn summary from CV."""
    
    focus_text = f" with emphasis on {focus}" if focus else ""
    
    prompt = f"""Generate a compelling LinkedIn 'About' section based on this CV{focus_text}.

CV:
{cv_text[:1500]}

Guidelines:
- 2-3 paragraphs
- First-person voice
- Highlight key skills and achievements
- Show personality
- End with what you're looking for or open to

Generate the LinkedIn summary:"""

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text