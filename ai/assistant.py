"""Thin, safe wrapper around the optional OpenAI integration.

* Reads the key from the environment (``.env``); never hardcoded, never logged.
* Every AI feature calls ``ask`` which raises ``AIUnavailableError`` when no key is configured,
  so the UI can disable AI actions gracefully while the rest of the app keeps working.
"""
from __future__ import annotations

from config import settings
from utils.helpers import get_logger

log = get_logger("ai")

SETUP_HELP = (
    "AI features are turned off because no OpenAI API key was found. To enable them: copy `.env.example` "
    "to `.env`, set `OPENAI_API_KEY=your-key` (optionally `OPENAI_MODEL=...`), then restart the app. "
    "Everything else in SearchRo works without a key."
)

SYSTEM_BASE = (
    "You are SearchRo, a practical career assistant for job seekers, especially fresh graduates in India "
    "and worldwide. Be concrete and honest. Never invent experience, employers, degrees or skills the "
    "candidate has not stated. If information is missing, say so instead of guessing."
)


class AIUnavailableError(RuntimeError):
    """No API key (or the openai package is missing)."""


class AIError(RuntimeError):
    """The AI request failed. The message is safe to show to the user."""


def is_ai_enabled() -> bool:
    return bool(settings.get_openai_key())


_FRIENDLY_ERRORS = {
    "AuthenticationError": "OpenAI rejected the API key. Check OPENAI_API_KEY in your .env file.",
    "PermissionDeniedError": "Your OpenAI account does not have access to this model.",
    "RateLimitError": "OpenAI rate limit or quota reached. Wait a moment or check your billing/usage.",
    "APITimeoutError": "The AI request timed out. Please try again.",
    "APIConnectionError": "Could not connect to OpenAI. Check your internet connection.",
    "NotFoundError": "The model was not found. Check OPENAI_MODEL in your .env file.",
    "BadRequestError": "OpenAI rejected the request (the input may be too long, or the model name is wrong).",
}


def _client():
    key = settings.get_openai_key()
    if not key:
        raise AIUnavailableError(SETUP_HELP)
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIUnavailableError("The 'openai' package is not installed. Run: pip install -r requirements.txt") from exc
    return OpenAI(api_key=key, timeout=settings.AI_TIMEOUT, max_retries=1)


def ask(user: str | None = None, system: str = SYSTEM_BASE, messages: list[dict] | None = None,
        max_tokens: int = 1500) -> str:
    """Send one request. Pass either ``user`` or a full ``messages`` history."""
    client = _client()
    payload = [{"role": "system", "content": system}]
    payload += messages if messages else [{"role": "user", "content": user or ""}]
    try:
        resp = client.chat.completions.create(
            model=settings.get_openai_model(), messages=payload, max_completion_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 - map every SDK error to a friendly message
        name = type(exc).__name__
        log.warning("AI request failed: %s", name)           # error type only; no prompt, no key
        raise AIError(_FRIENDLY_ERRORS.get(name, "The AI request failed. Please try again.")) from exc
    if not text:
        raise AIError("The AI returned an empty answer. Please try again.")
    return text


def _clip(text: str, limit: int = 9000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def improve_resume(resume_text: str, target_role: str = "", skills: list[str] | None = None) -> str:
    role = target_role or "a junior software / Python / ML role"
    prompt = (
        f"Review this resume for {role}. Use these sections with markdown headings:\n"
        "1. Overall quality (score out of 10 + 3 sentence reasoning)\n"
        "2. Top 5 improvements (most important first)\n"
        "3. Missing technical skills worth adding (only if relevant to the role; say they should be added "
        "only if the candidate truly has them)\n"
        "4. Weak bullet points rewritten (quote the original, then a stronger version using ONLY facts "
        "already in the resume; do not invent numbers)\n"
        "5. Stronger project descriptions (same rule: no invented facts; mark any suggested metric as "
        "'add your real number')\n\n"
        f"Detected skills: {', '.join(skills or []) or 'none detected'}\n\nRESUME:\n{_clip(resume_text)}"
    )
    return ask(prompt, max_tokens=2000)


def chat_reply(history: list[dict], context: str = "") -> str:
    system = SYSTEM_BASE + " Answer questions about job applications, resumes, interview preparation, " \
        "career planning and technical skills. Keep answers focused and actionable."
    if context:
        system += "\n\nContext about the user (may be incomplete):\n" + context
    return ask(system=system, messages=history[-12:], max_tokens=1000)
