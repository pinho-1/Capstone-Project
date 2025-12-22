import html
import re

def sanitize_text(value: str) -> str:
    """Strip control chars, and collapse spacing."""
    if not value:
        return ""
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()

def sanitize_json(obj):
    """Recursively sanitize text fields in dict/list structures."""
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json(i) for i in obj]
    elif isinstance(obj, str):
        return sanitize_text(obj)
    return obj
