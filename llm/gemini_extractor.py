import os
from typing import Optional

import warnings
import time

# The google.generativeai package is deprecated upstream and emits a FutureWarning
# on import. The project requirement is to use google.generativeai, so we silence
# the warning to keep CLI output readable.
warnings.simplefilter("ignore", FutureWarning)

import google.generativeai as genai


STRICT_JSON_PROMPT_TEMPLATE = """
You are a meeting intelligence assistant.

From the given transcript, extract:

1. Summary (max 5 lines)
2. Action Items:

   * task
   * owner
   * deadline
   * priority (High/Medium/Low)
3. Key Decisions
4. Open Questions

Rules:

* If owner not mentioned, use "Unassigned"
* If deadline not mentioned, use "None"
* Infer priority from words like urgent, ASAP
* Return ONLY valid JSON

Format:
{
"summary": "...",
"action_items": [
{
"task": "...",
"owner": "...",
"deadline": "...",
"priority": "..."
}
],
"decisions": [],
"open_questions": []
}

Transcript:
"""


def list_models() -> list[str]:
    """Return model names that support generateContent."""
    _configure_genai_from_env()
    models = []
    for m in genai.list_models():
        supported = set(getattr(m, "supported_generation_methods", []) or [])
        if "generateContent" in supported:
            name = getattr(m, "name", None)
            if name:
                models.append(str(name))
    return sorted(set(models))


def _get_api_key() -> Optional[str]:
    # Support both names: we document GEMINI_API_KEY, while the SDK also recognizes GOOGLE_API_KEY.
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _configure_genai_from_env() -> None:
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "Missing GEMINI_API_KEY (or GOOGLE_API_KEY). Put it in your .env file, e.g.\n"
            "GEMINI_API_KEY=YOUR_KEY"
        )
    genai.configure(api_key=api_key)


def _choose_default_model_name(available: list[str]) -> Optional[str]:
    """Pick a reasonable default model from an available list."""
    if not available:
        return None

    # Prefer stable aliases when available.
    preferred = [
        "models/gemini-flash-latest",
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
    ]
    for name in preferred:
        if name in available:
            return name

    # Prefer stable, newer Flash models. Avoid preview/image/tts variants by default.
    def score(name: str) -> tuple:
        low = name.lower()

        is_gemini = "gemini" in low
        is_flash = "flash" in low
        is_lite = "lite" in low
        is_preview = "preview" in low
        is_image = "image" in low
        is_tts = "tts" in low

        # Extract a numeric version if present, e.g. gemini-2.5-flash -> 2.5
        version = 0.0
        import re

        m = re.search(r"gemini-(\d+(?:\.\d+)?)", low)
        if m:
            try:
                version = float(m.group(1))
            except Exception:
                version = 0.0

        # Rank tuple: higher is better.
        return (
            1 if is_gemini else 0,
            1 if is_flash else 0,
            0 if is_preview else 1,
            0 if (is_image or is_tts) else 1,
            0 if is_lite else 1,
            version,
            name,
        )

    return sorted(available, key=score, reverse=True)[0]


def extract_with_gemini(transcript: str, *, model_name: Optional[str] = None) -> str:
    """Send transcript to Gemini and return raw model output (expected to be JSON)."""
    _configure_genai_from_env()

    env_model = os.environ.get("GEMINI_MODEL")
    explicit_model = model_name or env_model

    # Auto-select a model if none explicitly requested.
    chosen_model = explicit_model
    if not chosen_model:
        available = list_models()
        chosen_model = _choose_default_model_name(available)
        if not chosen_model:
            raise RuntimeError(
                "No Gemini models available for generateContent. "
                "Double-check your API key and permissions."
            )

    model = genai.GenerativeModel(chosen_model)

    prompt = STRICT_JSON_PROMPT_TEMPLATE + "\n" + transcript.strip()

    # Simple delay to reduce accidental rapid runs and 429s.
    try:
        delay = float(os.environ.get("GEMINI_DELAY_SECONDS", "1.0"))
    except Exception:
        delay = 1.0
    if delay > 0:
        time.sleep(delay)

    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0},
        )
    except Exception as e:
        # If the explicitly chosen model is unavailable (common when model names change),
        # provide a helpful error with supported models.
        msg = str(e)
        if "is not found" in msg or "NOT_FOUND" in msg or "404" in msg:
            available = list_models()
            hint = "\n".join(["Available models:"] + [f"- {m}" for m in available[:50]])
            raise RuntimeError(
                f"Gemini model '{chosen_model}' is not available for this API key.\n{hint}\n\n"
                "Tip: set GEMINI_MODEL in .env to one of the available model names, "
                "or pass --gemini-model on the CLI."
            ) from e
        raise

    # google-generativeai returns text in response.text in typical usage.
    text = getattr(response, "text", None)
    if not text:
        # Fallback: try to stringify the whole response.
        text = str(response)

    return text
