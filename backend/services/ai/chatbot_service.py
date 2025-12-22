"""
Agent-based Chatbot AI Service with Function Calling (NEW SDK)
- Uses google-genai client from gemini_client.py
- Uses client.chats.create() so SDK manages history
- Model chooses tools itself (function calling)
- Supports tool_result -> function_response -> final answer loop
- Adds: Router agent + Specialist agents (ALL stateful chats), class-based
- Less restrictive: writing/roadmap/general write directly, tools only where useful
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
# -----------------------------

FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "track_application",
        "description": "Track a new job application with company, role, and date.",
        "parameters": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "applied_date": {"type": "string"},
                "job_url": {"type": "string"},
                "notes": {"type": "string"},
            },
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
                "application_id": {"type": "integer"},
                "new_status": {
                    "type": "string",
                    "enum": ["applied", "interview", "rejected", "offer", "accepted"],
                },
            },
        },
    },
    {
        "name": "set_follow_up_reminder",
        "description": "Set a follow-up reminder for a job application.",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer"},
                "days_from_now": {"type": "integer"},
            },
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for information about companies, salaries, interview processes, etc.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
]

# Router tool
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
            "task": {"type": "string"},
        },
        "required": ["agent_name", "task"],
    },
}


# -----------------------------
# Prompts
# -----------------------------

CHATBOT_SYSTEM_PROMPT = """You are Talentum's AI Career Assistant.

Hard redirects (2–3 sentences, include route):
- CV improvements/ATS/scoring -> /cv
- interview prep/mock interview -> /interviews
- career matching/recommended roles -> /career-match

Guest mode:
- If user_context indicates guest=True, do NOT attempt application tracking tools.
- You may still provide general advice and write drafts, but avoid claiming you saved anything.

Default behavior:
- Be helpful and decisive. If info is missing, make reasonable assumptions and proceed.
- Ask at most ONE follow-up question when it materially improves the output.
- For writing tasks (cover letter, LinkedIn, outreach, roadmap): produce a complete usable draft even if details are missing.
- Use the user's onboarding context when answering questions like experience_years.

Tool usage:
- Only use tools when they create real value (tracking apps, listing apps, updating status, reminders, web research).
- Do not mention tools unless you actually used one.
"""

ROUTER_SYSTEM_PROMPT = """You are an internal router.

Pick one agent:
- redirect: CV improvements -> /cv ; interview prep -> /interviews ; matching -> /career-match
- applications: tracking/listing/updating/reminders
- research: company research/salary/interview process (may use web_search)
- writing: cover letter/LinkedIn/outreach (write directly)
- roadmap: 4-week plan (write directly)
- general: everything else

You MUST call route_to_agent with agent_name + task.
Task must be a clean instruction for the chosen agent.
"""

def build_system_prompt(user_cv_text: Optional[str], user_context: Optional[dict]) -> str:
    parts = [CHATBOT_SYSTEM_PROMPT]

    if user_context:
        parts.append("\n\nUser Context (trusted):\n" + json.dumps(user_context, indent=2, ensure_ascii=False))

    if user_cv_text:
        parts.append("\n\nUser CV Extract (trusted, may be partial):\n" + user_cv_text[:2000])

    return "\n".join(parts)


# -----------------------------
# Session manager
# -----------------------------

class ChatSessionManager:
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
            cfg = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            )
            if tool_decls:
                cfg.tools = [types.Tool(function_declarations=tool_decls)]

            chat = client.chats.create(model=MODEL_NAME, config=cfg)
            self._sessions[key] = chat
            self._sys_hash[key] = sys_hash

        return self._sessions[key]


# -----------------------------
# Base agent
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
                if tool_result is not None:
                    pending = self._get_pending(user_id)
                    if not pending:
                        return {"response": "Tool sequencing error (no pending tool).", "function_call": None, "tool_name": None}
                    if tool_result.get("name") != pending:
                        return {"response": f"Tool sequencing error (expected {pending}).", "function_call": None, "tool_name": None}

                    # MUST be a Part, not a list/dict
                    part = types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_result["name"],
                            response=tool_result["response"],
                        )
                    )
                    resp = chat.send_message(part)
                    self._clear_pending(user_id)

                else:
                    if not user_message:
                        return {"response": "Internal error: missing user message.", "function_call": None, "tool_name": None}
                    resp = chat.send_message(user_message)

                function_calls = getattr(resp, "function_calls", None)
                if function_calls:
                    fc0 = function_calls[0]
                    # Only enforce tool_result sequencing for REAL tools
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
        parts = [ROUTER_SYSTEM_PROMPT]
        if user_context:
            parts.append("\n\nUser Context:\n" + json.dumps(user_context, indent=2, ensure_ascii=False))
        return "\n".join(parts)


# -----------------------------
# Specialist agents
# -----------------------------

class GeneralAgent(BaseAgent):
    agent_key = "general"
    def __init__(self, sessions: ChatSessionManager):
        # no tools: general should just answer
        super().__init__(sessions, tool_decls=[], temperature=0.5)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context)


class ApplicationsAgent(BaseAgent):
    agent_key = "applications"
    def __init__(self, sessions: ChatSessionManager):
        # tools only for applications
        super().__init__(sessions, tool_decls=[
            next(t for t in FUNCTION_DECLARATIONS if t["name"] == "track_application"),
            next(t for t in FUNCTION_DECLARATIONS if t["name"] == "list_applications"),
            next(t for t in FUNCTION_DECLARATIONS if t["name"] == "update_application_status"),
            next(t for t in FUNCTION_DECLARATIONS if t["name"] == "set_follow_up_reminder"),
        ], temperature=0.4)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context) + """
You are the Applications specialist.
- Use tools when the user wants to track/list/update/remind.
- Otherwise answer normally.
"""


class ResearchAgent(BaseAgent):
    agent_key = "research"
    def __init__(self, sessions: ChatSessionManager):
        super().__init__(sessions, tool_decls=[
            next(t for t in FUNCTION_DECLARATIONS if t["name"] == "web_search"),
        ], temperature=0.4)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context) + """
You are the Research specialist.
- Use web_search only when the user asks for factual company/salary/interview-process info.
- If web_search is unavailable, provide general guidance without refusing.
"""


class WritingAgent(BaseAgent):
    agent_key = "writing"
    def __init__(self, sessions: ChatSessionManager):
        super().__init__(sessions, tool_decls=[], temperature=0.7)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context) + """
You are the Writing specialist.
- Write content directly (cover letters, LinkedIn, outreach).
- If details are missing, assume sensible defaults and still produce a complete draft.
- Ask at most ONE question, and only after providing a draft.
"""


class RoadmapAgent(BaseAgent):
    agent_key = "roadmap"
    def __init__(self, sessions: ChatSessionManager):
        super().__init__(sessions, tool_decls=[], temperature=0.6)

    def build_system(self, user_cv_text: Optional[str], user_context: Optional[Dict]) -> str:
        return build_system_prompt(user_cv_text, user_context) + """
You are the Roadmap specialist.
- Produce a 4-week plan with bullets and a quick checklist.
- If details are missing, assume a junior data analyst/data scientist target.
"""


# -----------------------------
# Orchestrator
# -----------------------------

class AgentOrchestrator:
    def __init__(self):
        self.sessions = ChatSessionManager()
        self.router = RouterAgent(self.sessions)

        self.agents: Dict[str, BaseAgent] = {
            "general": GeneralAgent(self.sessions),
            "applications": ApplicationsAgent(self.sessions),
            "research": ResearchAgent(self.sessions),
            "writing": WritingAgent(self.sessions),
            "roadmap": RoadmapAgent(self.sessions),
        }
        self._last_agent: Dict[int, str] = {}

    @observe()
    async def route(self, user_id: int, user_message: str, user_context: Optional[Dict]) -> Dict[str, str]:
        routed = await self.router.send(
            user_id=user_id,
            user_message=user_message,
            user_context=user_context,
        )
        fc = routed.get("function_call")
        if not fc or fc["name"] != "route_to_agent":
            return {"agent_name": "general", "task": user_message}

        args = fc.get("args") or {}
        return {"agent_name": args.get("agent_name", "general"), "task": args.get("task", user_message)}

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
            if tool_result is not None:
                agent_name = forced_agent or self._last_agent.get(user_id, "general")
                agent = self.agents.get(agent_name, self.agents["general"])
                out = await agent.send(
                    user_id=user_id,
                    user_message=None,
                    user_cv_text=user_cv_text,
                    user_context=user_context,
                    tool_result=tool_result,
                )
                out["agent_name"] = agent_name
                return out

            routed = await self.route(user_id, user_message, user_context)
            agent_name = forced_agent or routed["agent_name"]
            task = routed["task"]

            if agent_name == "redirect":
                agent_name = "general"

            self._last_agent[user_id] = agent_name
            agent = self.agents.get(agent_name, self.agents["general"])

            out = await agent.send(
                user_id=user_id,
                user_message=task,
                user_cv_text=user_cv_text,
                user_context=user_context,
            )
            out["agent_name"] = agent_name
            return out

        except Exception as e:
            print(f"AgentOrchestrator error: {e}")
            if _is_overloaded_error(e):
                return {"response": "The AI is overloaded right now. Try again in a moment.", "function_call": None, "tool_name": None, "agent_name": "general"}
            return {"response": "I hit an error while answering. Try again with a shorter message.", "function_call": None, "tool_name": None, "agent_name": "general"}


orch = AgentOrchestrator()
