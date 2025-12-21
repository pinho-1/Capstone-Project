"""
Chatbot AI Service with Function Calling (NEW SDK)
- Uses google-genai client from gemini_client.py
- Uses client.chats.create() so SDK manages history
- Model chooses tools itself (function calling)
- Supports tool_result -> function_response -> final answer loop
"""

from typing import Dict, Any, Optional
import json
from langfuse import observe
import asyncio
from backend.services.ai.gemini_client import get_client, get_types

def _is_overloaded_error(e: Exception) -> bool:
    msg = str(e)
    return ("503" in msg) or ("UNAVAILABLE" in msg) or ("overloaded" in msg.lower())

client = get_client()
types = get_types()

MODEL_NAME = "gemini-2.5-flash-lite"

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

FUNCTION_DECLARATIONS = [
    {
        "name": "track_application",
        "description": "Track a new job application with company, role, and date.",
        "parameters": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "The company name"},
                "role": {"type": "string", "description": "The job title/role"},
                "applied_date": {"type": "string", "description": "When they applied (e.g., 'today', '2024-12-19')"},
                "job_url": {"type": "string", "description": "URL to the job posting if mentioned"},
                "notes": {"type": "string", "description": "Additional notes"},
            },
            "required": ["company", "role"],
        },
    },
    {
        "name": "list_applications",
        "description": "Show all tracked job applications for the user.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "update_application_status",
        "description": "Update the status of a job application.",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer", "description": "The application ID"},
                "new_status": {
                    "type": "string",
                    "enum": ["applied", "interview", "rejected", "offer", "accepted"],
                    "description": "The new status",
                },
            },
            "required": ["application_id", "new_status"],
        },
    },
    {
        "name": "set_follow_up_reminder",
        "description": "Set a follow-up reminder for a job application.",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer", "description": "The application ID"},
                "days_from_now": {"type": "integer", "description": "How many days from now to follow up (default 14)"},
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for information about companies, salaries, interview processes, etc.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "generate_cover_letter",
        "description": "Generate a cover letter based on the user's CV and a job description.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string", "description": "The job description or key requirements"},
                "tone": {"type": "string", "enum": ["professional", "enthusiastic", "conversational"]},
            },
            "required": ["job_description"],
        },
    },
    {
        "name": "generate_linkedin_summary",
        "description": "Generate a LinkedIn summary/about section based on the user's CV.",
        "parameters": {"type": "object", "properties": {"focus": {"type": "string"}}},
    },
]


def build_system_prompt(user_cv_text: Optional[str], user_context: Optional[dict]) -> str:
    parts = [CHATBOT_SYSTEM_PROMPT]

    if user_context:
        parts.append("\n\nUser Profile & Onboarding Context (trusted):\n" + json.dumps(user_context, indent=2))

    if user_cv_text:
        parts.append("\n\nUser CV Extract (trusted):\n" + user_cv_text[:2000])

    return "\n".join(parts)


# In-memory session cache
_CHAT_SESSIONS: Dict[int, Any] = {}
_CHAT_SYSTEM_HASH: Dict[int, str] = {}


def _get_or_create_chat(user_id: int, system_prompt: str):
    """
    Creates a stateful chat per user.
    Recreates the chat if the system prompt changes (e.g., CV updated).
    """
    sys_hash = str(hash(system_prompt))
    if _CHAT_SESSIONS.get(user_id) is None or _CHAT_SYSTEM_HASH.get(user_id) != sys_hash:
        chat = client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
                temperature=0.4,
            ),
        )
        _CHAT_SESSIONS[user_id] = chat
        _CHAT_SYSTEM_HASH[user_id] = sys_hash

    return _CHAT_SESSIONS[user_id]


@observe()
async def get_chatbot_response(
    user_id: int,
    user_message: str,
    user_cv_text: Optional[str] = None,
    user_context: Optional[Dict] = None,
    tool_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    system_prompt = build_system_prompt(user_cv_text, user_context)
    chat = _get_or_create_chat(user_id, system_prompt)

    try:
        for attempt in range(3):
            try:
                # If we have tool results, send them as a function_response "turn"
                if tool_result:
                    resp = chat.send_message([
                        {
                            "function_response": {
                                "name": tool_result["name"],
                                "response": tool_result["response"],
                            }
                        }
                    ])
                else:
                    resp = chat.send_message(user_message)

                # Function calling: new SDK exposes function_calls on the response
                function_calls = getattr(resp, "function_calls", None)
                if function_calls:
                    fc0 = function_calls[0]
                    return {
                        "response": None,
                        "function_call": {"name": fc0.name, "args": dict(fc0.args)},
                        "tool_name": fc0.name,
                    }

                return {"response": resp.text, "function_call": None, "tool_name": None}
            
            except Exception as e:
                if attempt < 2 and _is_overloaded_error(e):
                    await asyncio.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s, 1.5s
                    continue
                raise

    except Exception as e:
        print(f"Chatbot error: {e}")
        # IMPORTANT: return a user-friendly message for overload
        if _is_overloaded_error(e):
            return {
                "response": "The AI is overloaded right now. Try again in a moment.",
                "function_call": None,
                "tool_name": None,
            }
        return {
            "response": "I hit an error while answering. Try again with a shorter message.",
            "function_call": None,
            "tool_name": None,
        }

# ---- Content generators (use new client too) ----

async def generate_cover_letter_content(cv_text: str, job_description: str, tone: str = "professional") -> str:
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

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6),
    )
    return resp.text


async def generate_linkedin_summary_content(cv_text: str, focus: Optional[str] = None) -> str:
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

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.6),
    )
    return resp.text