"""One entry point to Gemma: Gemini API first, OpenRouter if Google fails, is slow, or
answers in the wrong script.

"Live" = a caller is waiting (lightweight Gemma 26B A4B, thinking off).
"Background" = nobody is waiting (Gemma 31B, thinking on — its reasoning is shown).
"""

import logging
from typing import Literal

from app.llm import gemini, openrouter
from app.llm.types import LLMError, LLMReply, Msg, ToolSpec
from app.settings import get_settings

log = logging.getLogger(__name__)

# Unicode blocks for scripts Gemma sometimes slips into. Kannada (0C80–0CFF),
# Devanagari (0900–097F) and Latin are what our callers use.
_SCRIPTS = {
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "te": (0x0C00, 0x0C7F),  # Telugu
    "ml": (0x0D00, 0x0D7F),  # Malayalam
    "bn": (0x0980, 0x09FF),  # Bengali / Assamese
    "gu": (0x0A80, 0x0AFF),  # Gujarati
    "pa": (0x0A00, 0x0A7F),  # Gurmukhi
    "or": (0x0B00, 0x0B7F),  # Odia
}


def foreign_script(text: str, caller_language: str | None = None) -> str | None:
    """The first script in `text` that the caller isn't using, e.g. "ta". None if clean."""
    allowed = (caller_language or "").split("-")[0]
    for ch in text:
        cp = ord(ch)
        for code, (lo, hi) in _SCRIPTS.items():
            if lo <= cp <= hi and code != allowed:
                return code
    return None


def generate(
    *,
    system: str,
    messages: list[Msg],
    tools: list[ToolSpec],
    mode: Literal["live", "background"] = "live",
    caller_language: str | None = None,
    max_tokens: int = 400,
) -> LLMReply:
    s = get_settings()
    live = mode == "live"
    attempts = []
    if s.gemini_api_key:
        attempts.append(("gemini", s.llm_live_model if live else s.llm_background_model))
    if s.openrouter_api_key:
        attempts.append(("openrouter", "google/" + (s.llm_live_model if live else s.llm_background_model)))
    if not attempts:
        raise LLMError("no LLM provider configured")

    errors = []
    for provider, model in attempts:
        # Each provider gets one retry if it replies in the wrong script.
        for _ in range(2):
            try:
                if provider == "gemini":
                    reply = gemini.generate(
                        api_key=s.gemini_api_key, model=model, system=system, messages=messages, tools=tools,
                        thinking="minimal" if live else "high", max_tokens=max_tokens if live else max_tokens * 4,
                        timeout_s=s.llm_primary_timeout_s if live else 60,
                    )
                else:
                    reply = openrouter.generate(
                        api_key=s.openrouter_api_key, model=model, system=system, messages=messages, tools=tools,
                        max_tokens=max_tokens, timeout_s=10 if live else 60,
                    )
            except LLMError as e:
                errors.append(str(e))
                log.warning("LLM %s/%s failed: %s", provider, model, e)
                break  # next provider
            bad = foreign_script(reply.text, caller_language)
            if bad:
                errors.append(f"{provider} replied with {bad} script")
                log.warning("LLM %s replied with %s script; retrying", provider, bad)
                continue
            return reply
    raise LLMError("; ".join(errors) or "all providers failed")
