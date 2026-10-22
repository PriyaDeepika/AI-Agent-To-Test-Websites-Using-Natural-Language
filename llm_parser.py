"""Optional LLM planner (Gemini). Returns a *validated* plan or raises; the caller falls back to rules.
The model only emits JSON for the whitelisted action schema – nothing it writes is ever executed as code."""
from __future__ import annotations
import json, re
import config
from actions import ACTION_SPECS, validate_plan

SYSTEM_PROMPT = f"""You convert a natural-language web-testing instruction into a JSON plan for a browser agent.
Return ONLY a JSON array. Each item: {{"action": str, "target": str|null, "value": str|null, "description": str}}.

Allowed actions: {', '.join(ACTION_SPECS)}.
- open: target = full URL. search: value = the query. click: target = short description of the element.
- type: target = field description, value = text. select_option: target = control ("size"), value = option or null if the user did not say.
- select_result: target = product|video|article|result (pick a relevant search result).
- login: value = "username\\npassword" (empty strings if not given; never invent credentials).
- add_to_cart, verify_cart, verify_video, verify_page need no target. verify_text/verify_url: value = expected text.
- apply_filter: target = "price" or a filter label, value = amount/label or null.
Rules: keep the user's order; never invent values the user did not give; never add purchase/payment/checkout steps
unless explicitly requested; end with verification steps that match what the user wants verified. No prose, no markdown."""


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def parse_instruction_llm(instruction: str, start_url: str | None = None):
    if not available():
        raise RuntimeError("GEMINI_API_KEY is not configured")
    import google.generativeai as genai  # lazy: optional dependency
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)
    prompt = f"{SYSTEM_PROMPT}\n\nTarget URL (may be empty): {start_url or ''}\nInstruction: {instruction}"
    text = model.generate_content(prompt).text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return validate_plan(json.loads(text))
