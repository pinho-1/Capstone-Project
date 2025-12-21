import os
import json
from typing import Any, Optional, Dict, List
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment")

client = genai.Client(api_key=API_KEY)

DEFAULT_MODEL = "gemini-2.5-flash-lite"

def get_client():
    return client

def get_types():
    return types

def make_chat(
    system_prompt: str,
    function_declarations: Optional[List[dict]] = None,
    model: str = DEFAULT_MODEL,
):
    """
    Creates a stateful chat session (SDK manages history).
    If function_declarations provided, enables tool use (function calling).
    """
    tools = []
    if function_declarations:
        tools = [types.Tool(function_declarations=function_declarations)]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools if tools else None,
        # keep default AUTO function calling (model decides)
    )

    return client.chats.create(model=model, config=config)


def generate_text(
    system_prompt: str,
    user_text: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.5,
) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=float(temperature),
    )
    resp = client.models.generate_content(model=model, contents=user_text, config=config)
    return resp.text


async def generate_json(
    system_prompt: str,
    user_payload: dict,
    temperature: float = 0.4,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Keeps your existing JSON mode behavior (for consistency with other pages).
    """
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=float(temperature),
            top_p=1.0,
            candidate_count=1,
        )
        resp = client.models.generate_content(
            model=model,
            contents=json.dumps(user_payload),
            config=config,
        )
        return json.loads(resp.text)
    except Exception as e:
        print("Gemini error:", e)
        return {"error": str(e)}