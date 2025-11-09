import os
import json
import google.generativeai as genai

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment")

genai.configure(api_key=API_KEY)

def _model(system_prompt: str):
    return genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=system_prompt
    )

async def generate_json(system_prompt: str, user_payload: dict) -> dict:
    try:
        model = _model(system_prompt)
        resp = model.generate_content(
            json.dumps(user_payload),
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(resp.text)
    except Exception as e:
        print("Gemini error:", e)
        return {"error": str(e)}