from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from langfuse import observe

from backend.services.ai.gemini_client import get_client, get_types


# -----------------------------
# Shared utilities
# -----------------------------

def _is_overloaded_error(e: Exception) -> bool:
    msg = str(e)
    return "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()


client = get_client()
types = get_types()

MODEL_NAME = "gemini-2.5-flash-lite"


# -----------------------------
# Tool declarations
# -----------------------------

FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "track_application",
        "description": "Track a new job application.",
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
        "description": "List tracked job applications.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "update_application_status",
        "description": "Update job application status.",
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
        "description": "Set a follow-up reminder.",
        "parameters": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer"},
                "days_from_now": {"type": "integer"},
            },
        },
    },
]


ROUTE_TOOL_DECL = {
    "name": "route_to_agent",
    "description": "Route request to the best agent.",
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

Hard redirects:
- CV improvements -> /cv
- Interview prep -> /interviews
- Career matching -> /cm
"""

ROUTER_SYSTEM_PROMPT = """You are an internal router.
Always call route_to_agent.
"""


def build_system_prompt(user_cv_text: Optional[str], user_context: Optional[dict]) -> str:
    parts = [CHATBOT_SYSTEM_PROMPT]

    if user_context:
        parts.append(json.dumps(user_context, indent=2, ensure_ascii=False))

    if user_cv_text:
        parts.append(user_cv_text[:2000])

    return "\n\n".join(parts)


# -----------------------------
# Session manager
# -----------------------------

class ChatSessionManager:
    def __init__(self):
        self._sessions: Dict[Tuple[int, str], Any] = {}
        self._sys_hash: Dict[Tuple[int, str], str] = {}

    def get_or_create(self, user_id: int, agent_key: str, system_prompt: str, tool_decls, temperature=0.4):
        key = (user_id, agent_key)
        sys_hash = str(hash(system_prompt))

        if key not in self._sessions or self._sys_hash.get(key) != sys_hash:
            cfg = types.GenerateContentConfig(system_instruction=system_prompt, temperature=temperature)
            if tool_decls:
                cfg.tools = [types.Tool(function_declarations=tool_decls)]
            self._sessions[key] = client.chats.create(model=MODEL_NAME, config=cfg)
            self._sys_hash[key] = sys_hash

        return self._sessions[key]


# -----------------------------
# Base agent
# -----------------------------

class BaseAgent:
    agent_key = "base"

    def __init__(self, sessions: ChatSessionManager, tool_decls, temperature=0.4):
        self.sessions = sessions
        self.tool_decls = tool_decls
        self.temperature = temperature
        self._pending: Dict[int, str] = {}

    def build_system(self, user_cv_text, user_context):
        return ""

    def _chat(self, user_id, user_cv_text, user_context):
        return self.sessions.get_or_create(
            user_id,
            self.agent_key,
            self.build_system(user_cv_text, user_context),
            self.tool_decls,
            self.temperature,
        )

    async def send(self, user_id, user_message=None, user_cv_text=None, user_context=None, tool_result=None):
        chat = self._chat(user_id, user_cv_text, user_context)

        try:
            if tool_result:
                part = types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_result["name"],
                        response=tool_result["response"],
                    )
                )
                resp = chat.send_message(part)
                self._pending.pop(user_id, None)
            else:
                resp = chat.send_message(user_message)

            fc = getattr(resp, "function_calls", None)
            if fc:
                fc0 = fc[0]
                self._pending[user_id] = fc0.name
                return {"function_call": {"name": fc0.name, "args": dict(fc0.args)}}

            return {"response": resp.text}

        except Exception as e:
            if _is_overloaded_error(e):
                return {"response": "The AI is overloaded. Try again shortly."}
            raise


# -----------------------------
# Agents
# -----------------------------

class RouterAgent(BaseAgent):
    agent_key = "router"

    def __init__(self, sessions):
        super().__init__(sessions, [ROUTE_TOOL_DECL], temperature=0.2)

    def build_system(self, *_):
        return ROUTER_SYSTEM_PROMPT


class GeneralAgent(BaseAgent):
    agent_key = "general"

    def __init__(self, sessions):
        super().__init__(sessions, [], temperature=0.5)

    def build_system(self, user_cv_text, user_context):
        return build_system_prompt(user_cv_text, user_context)


class ApplicationsAgent(GeneralAgent):
    agent_key = "applications"


class ResearchAgent(GeneralAgent):
    agent_key = "research"


class WritingAgent(GeneralAgent):
    agent_key = "writing"


class RoadmapAgent(GeneralAgent):
    agent_key = "roadmap"


# -----------------------------
# Orchestrator
# -----------------------------

class AgentOrchestrator:
    def __init__(self):
        self.sessions = ChatSessionManager()
        self.router = RouterAgent(self.sessions)
        self.agents = {
            "general": GeneralAgent(self.sessions),
            "applications": ApplicationsAgent(self.sessions),
            "research": ResearchAgent(self.sessions),
            "writing": WritingAgent(self.sessions),
            "roadmap": RoadmapAgent(self.sessions),
        }
        self._last_agent: Dict[int, str] = {}

    @observe()
    async def handle(self, user_id, user_message, user_cv_text=None, user_context=None, tool_result=None, forced_agent=None):
        if tool_result:
            agent_name = forced_agent or self._last_agent.get(user_id, "general")
            return await self.agents[agent_name].send(
                user_id, None, user_cv_text, user_context, tool_result
            )

        routed = await self.router.send(user_id, user_message, None, user_context)
        fc = routed.get("function_call")

        if fc:
            agent_name = fc["args"].get("agent_name", "general")
            task = fc["args"].get("task", user_message)
        else:
            agent_name = "general"
            task = user_message

        self._last_agent[user_id] = agent_name
        return await self.agents[agent_name].send(user_id, task, user_cv_text, user_context)


orch = AgentOrchestrator()