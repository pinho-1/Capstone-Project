"""
Agent-based Chatbot AI Service with Function Calling (NEW SDK)
- Uses google-genai client from gemini_client.py
- Uses client.chats.create() so SDK manages history
- Model chooses tools itself (function calling)
- Supports tool_result -> function_response -> final answer loop
- Adds: Router agent + Specialist agents (ALL stateful chats), class-based like professor pattern
"""

from __future__ import annotations

from typing import Dict, Any, Optional, Tuple, List
import json
import asyncio
from langfuse import observe

from backend.services.ai.gemini_client import get_client, get_types


# -----------------------------
# Shared utilities
# -----------------------------

def _is_overloaded_error(e: Exception) -> bool:
    msg = str(e)
    return ("503" in msg) or ("UNAVAILABLE" in msg) or ("overloaded" in msg.lower())


client = get_client()
types = get_types()

MODEL_NAME = "gemini-2.5-flash-lite"


# -----------------------------
# Tool declarations
# Keep YOUR existing tools here
# -----------------------------

FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    # --- your tools exactly as you posted ---
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
    {
        "name": "generate_outreach_message",
        "description": "Generate a short outreach message to a recruiter or hiring manager.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Who the message is for (recruiter, hiring manager, employee)"},
                "company": {"type": "string"},
                "role": {"type": "string"},
                "tone": {"type": "string", "enum": ["professional", "friendly", "confident"]},
            },
            "required": ["target"],
        },
    },
    {
        "name": "generate_career_roadmap",
        "description": "Create a short action plan for the next 4 weeks based on the user's goals.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "timeframe_weeks": {"type": "integer", "description": "Default 4"},
            },
        },
    },
]

# Router tool (new)
ROUTE_TOOL_DECL = {
    "name": "route_to_agent",
    "description": "Route the request to the best internal agent.",
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "enum": ["general", "applications", "research", "writing", "roadmap", "redirect"],
            },
            "task": {"type": "string", "description": "The rewritten task to give the agent."},
        },
        "required": ["agent_name", "task"],
    },
}


# -----------------------------
# Prompt builders
# -----------------------------

CHATBOT_SYSTEM_PROMPT = """You are Talentum's AI Career Assistant, a helpful and friendly job search companion.

Routing rule (must follow):
- If the user asks for CV improvements, CV rewriting, ATS, or CV scoring: DO NOT answer in detail. Reply with a short redirect to the CV Analyzer page and explain it’s the correct tool for structured feedback.
- If the user asks for interview prep, mock interviews, interview questions, interview scoring: DO NOT proceed. Redirect to the Interview Simulator page.
- If the user asks for career matching/job matching/recommended roles: DO NOT proceed. Redirect to the Career Match page.
Keep redirect replies to 2–3 sentences, include the route path.

Your capabilities:
1) Track Job Applications
2) Research Companies
3) Answer Job Search Questions
4) Generate Content (cover letters, LinkedIn summaries, outreach)
5) Create a short 4-week roadmap

Guidelines:
- Be conversational, supportive, and encouraging
- Suggest proactive next steps
- Keep responses concise (2–4 sentences unless needed)
"""

ROUTER_SYSTEM_PROMPT = """You are an internal router agent for Talentum.

Decide which agent should handle the user:
- redirect: if they are asking for CV improvements/ATS/scoring -> redirect to /cv
           if interview prep/mock interviews -> redirect to /interviews
           if career matching/recommended roles -> redirect to /career-match
- applications: tracking, listing, updating application status, follow-up reminders
- research: company research, interview process, salary/culture questions (use web_search)
- writing: cover letter, LinkedIn summary, outreach messages
- roadmap: 4-week action plan / next steps plan
- general: everything else

You MUST call route_to_agent with agent_name + task.
The task must be a clean, complete instruction for the chosen agent.
"""

def build_system_prompt(user_cv_text: Optional[str], user_context: Optional[dict]) -> str:
    parts = [CHATBOT_SYSTEM_PROMPT]

    if user_context:
        parts.append("\n\nUser Profile & Onboarding Context (trusted):\n" + json.dumps(user_context, indent=2))

    if user_cv_text:
        parts.append("\n\nUser CV Extract (trusted):\n" + user_cv_text[:2000])

    return "\n".join(parts)


# -----------------------------
# Session manager (professor-style cache)
# -----------------------------

class ChatSessionManager:
    """
    Creates a stateful chat per (user_id, agent_key).
    Recreates when system prompt changes.
    """
    def __init__(self):
        self._sessions: Dict[Tuple[int, str], Any] = {}
        self._sys_hash: Dict[Tuple[int, str], str] = {}

    def get_or_create(
        self,
        user_id: int,
        agent_key: str,
        system_prompt: str,
        tool_decls: List[Dict[str, Any]],
        temperature: float = 0.4,
    ):
        key = (user_id, agent_key)
        sys_hash = str(hash(system_prompt))

        if self._sessions.get(key) is None or self._sys_hash.get(key) != sys_hash:
            chat = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[types.Tool(function_declarations=tool_decls)] if tool_decls else None,
                    temperature=temperature,
                ),
            )
            self._sessions[key] = chat
            self._sys_hash[key] = sys_hash

        return self._sessions[key]


# -----------------------------
# Base agent (same send loop, class form)
# -----------------------------

class BaseAgent:
    agent_key: str = "base"

    def __init__(
        self,
        sessions: ChatSessionManager,
        tool_decls: List[Dict[str, Any]],
        temperature: float = 0.4,
    ):
        self.sessions = sessions
        self.tool_decls = tool_decls
        self.temperature = temperature

        # Tracks the last function call requested by the model per user
        # Only then we are allowed to send a function_response
        self._pending_tool_name: Dict[int, str] = {}

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return ""

    def _get_chat(self, user_id: int, user_cv_text: Optional[str], user_context: Optional[Dict]):
        system_prompt = self.build_system(user_cv_text, user_context)
        return self.sessions.get_or_create(
            user_id=user_id,
            agent_key=self.agent_key,
            system_prompt=system_prompt,
            tool_decls=self.tool_decls,
            temperature=self.temperature,
        )

    def _set_pending(self, user_id: int, tool_name: str) -> None:
        self._pending_tool_name[user_id] = tool_name

    def _clear_pending(self, user_id: int) -> None:
        self._pending_tool_name.pop(user_id, None)

    def _get_pending(self, user_id: int) -> Optional[str]:
        return self._pending_tool_name.get(user_id)

    async def send(
        self,
        user_id: int,
        user_message: Optional[str] = None,
        user_cv_text: Optional[str] = None,
        user_context: Optional[Dict] = None,
        tool_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        chat = self._get_chat(user_id, user_cv_text, user_context)

        for attempt in range(3):
            try:
                # -----------------------------
                # CONTINUATION: tool_result
                # -----------------------------
                if tool_result is not None:
                    pending = self._get_pending(user_id)

                    # HARD GUARD: Only send function_response if we truly have a pending tool call.
                    if not pending:
                        return {
                            "response": "Tool sequencing error (no pending function call). Try again.",
                            "function_call": None,
                            "tool_name": None,
                        }

                    # Also ensure tool names match
                    if tool_result.get("name") != pending:
                        return {
                            "response": f"Tool sequencing error (expected {pending}, got {tool_result.get('name')}). Try again.",
                            "function_call": None,
                            "tool_name": None,
                        }

                    part = types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_result["name"],
                            response=tool_result["response"],
                        )
                    )
                    resp = chat.send_message(part)

                    # Once we send a function_response, clear pending
                    self._clear_pending(user_id)

                # -----------------------------
                # NORMAL USER TURN
                # -----------------------------
                else:
                    if not user_message:
                        return {
                            "response": "Internal error: missing user message.",
                            "function_call": None,
                            "tool_name": None,
                        }
                    resp = chat.send_message(user_message)

                # -----------------------------
                # FUNCTION CALL HANDLING
                # -----------------------------
                function_calls = getattr(resp, "function_calls", None)
                if function_calls:
                    fc0 = function_calls[0]

                    # Special case: router tool call is NOT a real external tool execution,
                    # so we do NOT want to enforce a function_response for it.
                    if fc0.name != "route_to_agent":
                        self._set_pending(user_id, fc0.name)

                    return {
                        "response": None,
                        "function_call": {"name": fc0.name, "args": dict(fc0.args)},
                        "tool_name": fc0.name,
                    }

                return {"response": resp.text, "function_call": None, "tool_name": None}

            except Exception as e:
                if attempt < 2 and _is_overloaded_error(e):
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise

# -----------------------------
# Router agent
# -----------------------------

class RouterAgent(BaseAgent):
    agent_key = "router"

    def __init__(self, sessions: ChatSessionManager):
        super().__init__(sessions, tool_decls=[ROUTE_TOOL_DECL], temperature=0.2)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        # Router can benefit from context, but keep it small
        parts = [ROUTER_SYSTEM_PROMPT]
        if user_context:
            parts.append("\n\nUser Context:\n" + json.dumps(user_context, indent=2))
        return "\n".join(parts)


# -----------------------------
# Specialist agents
# -----------------------------

class CareerAssistantAgent(BaseAgent):
    agent_key = "general"

    def __init__(self, sessions: ChatSessionManager):
        super().__init__(sessions, tool_decls=FUNCTION_DECLARATIONS, temperature=0.4)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context)


class ApplicationsAgent(CareerAssistantAgent):
    agent_key = "applications"


class ResearchAgent(CareerAssistantAgent):
    agent_key = "research"


class WritingAgent(CareerAssistantAgent):
    agent_key = "writing"


class RoadmapAgent(CareerAssistantAgent):
    agent_key = "roadmap"


# -----------------------------
# Orchestrator (router -> agent -> tool loop)
# -----------------------------

class AgentOrchestrator:
    def __init__(self):
        self.sessions = ChatSessionManager()
        self.router = RouterAgent(self.sessions)

        self.agents: Dict[str, BaseAgent] = {
            "general": CareerAssistantAgent(self.sessions),
            "applications": ApplicationsAgent(self.sessions),
            "research": ResearchAgent(self.sessions),
            "writing": WritingAgent(self.sessions),
            "roadmap": RoadmapAgent(self.sessions),
        }

        self._last_agent: Dict[int, str] = {}

    @observe()
    async def route(
        self,
        user_id: int,
        user_message: str,
        user_context: Optional[Dict],
    ) -> Dict[str, str]:
        routed = await self.router.send(
            user_id=user_id,
            user_message=user_message,
            user_context=user_context,
        )

        fc = routed.get("function_call")
        if not fc or fc["name"] != "route_to_agent":
            return {"agent_name": "general", "task": user_message}

        args = fc.get("args") or {}
        return {
            "agent_name": args.get("agent_name", "general"),
            "task": args.get("task", user_message),
        }

    @observe()
    async def handle(
        self,
        user_id: int,
        user_message: str,
        user_cv_text: Optional[str] = None,
        user_context: Optional[Dict] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        forced_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            # 1) Continuation after tool execution
            if tool_result:
                agent_name = forced_agent or self._last_agent.get(user_id, "general")
                agent = self.agents.get(agent_name, self.agents["general"])

                return await agent.send(
                    user_id=user_id,
                    user_message=None,
                    user_cv_text=user_cv_text,
                    user_context=user_context,
                    tool_result=tool_result,
                )

            # 2) Route fresh user message
            routed = await self.route(user_id, user_message, user_context)
            agent_name = forced_agent or routed["agent_name"]
            task = routed["task"]

            if agent_name == "redirect":
                agent_name = "general"

            self._last_agent[user_id] = agent_name
            agent = self.agents.get(agent_name, self.agents["general"])

            return await agent.send(
                user_id=user_id,
                user_message=task,
                user_cv_text=user_cv_text,
                user_context=user_context,
            )

        except Exception as e:
            print(f"AgentOrchestrator error: {e}")
            if _is_overloaded_error(e):
                return {"response": "The AI is overloaded right now. Try again in a moment.", "function_call": None, "tool_name": None}
            return {"response": "I hit an error while answering. Try again with a shorter message.", "function_call": None, "tool_name": None}


orch = AgentOrchestrator()
