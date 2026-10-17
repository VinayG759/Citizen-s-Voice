"""One entry point to Gemma: Gemini API first, OpenRouter if Google fails, is slow, or
answers in the wrong script.

"Live" = a caller is waiting (lightweight Gemma 26B A4B, thinking off).
"Background" = nobody is waiting (Gemma 31B, thinking on — its reasoning is shown).
"""

import logging
import unicodedata
from typing import Literal

from app.llm import gemini, openrouter
from app.llm.types import LLMError, LLMReply, Msg, ToolSpec
from app.settings import get_settings

log = logging.getLogger(__name__)

# Scripts our callers use: Kannada, Devanagari (Hindi) and Latin letters. A letter from any
# other script is a slip (seen in testing: Tamil, Telugu, and on a real call a Korean word).
_ALLOWED = ((0x0C80, 0x0CFF), (0x0900, 0x097F))
# If a caller speaks one of these languages, its script is allowed too.
_EXTRA = {"ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F), "ml": (0x0D00, 0x0D7F), "bn": (0x0980, 0x09FF),
          "gu": (0x0A80, 0x0AFF), "pa": (0x0A00, 0x0A7F), "or": (0x0B00, 0x0B7F)}


def foreign_script(text: str, caller_language: str | None = None) -> str | None:
    """The first letter's script that doesn't belong in this reply (e.g. "ta", "HANGUL"). None if clean."""
    allowed = list(_ALLOWED)
    extra = _EXTRA.get((caller_language or "").split("-")[0])
    if extra:
        allowed.append(extra)
    for ch in text:
        cp = ord(ch)
        if cp < 0x250 or not ch.isalpha():  # Latin letters, digits, punctuation, symbols
            continue
        if any(lo <= cp <= hi for lo, hi in allowed):
            continue
        for code, (lo, hi) in _EXTRA.items():
            if lo <= cp <= hi:
                return code
        return unicodedata.name(ch, "UNKNOWN").split()[0]
    return None


def generate(
    *,
    system: str,
    messages: list[Msg],
    tools: list[ToolSpec],
    mode: Literal["live", "background"] = "live",
    caller_language: str | None = None,
    max_tokens: int = 400,
    primary_timeout_s: float | None = None,  # how long to wait for Google before OpenRouter; None: the mode's default
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
        # A reply in the wrong script gets one retry: with the bigger model (whose Kannada was clean in
        # every test) and a one-line reminder. Retrying the same small model the same way tends to
        # slip again (golden run, 16 Oct: Telugu twice in a row).
        sys_prompt, use_model = system, model
        for _ in range(2):
            try:
                reply = _call(provider, use_model, sys_prompt, messages, tools, live, max_tokens, primary_timeout_s)
            except LLMError as e:
                errors.append(str(e))
                log.warning("LLM %s/%s failed: %s", provider, use_model, e)
                break  # next provider
            bad = foreign_script(reply.text, caller_language)
            if not bad:
                return reply
            errors.append(f"{provider}/{use_model} replied with {bad} script")
            log.warning("LLM %s/%s replied with %s script; retrying with the bigger model", provider, use_model, bad)
            use_model = s.llm_background_model if provider == "gemini" else "google/" + s.llm_background_model
            sys_prompt = (system + f"\n\nIMPORTANT: your last reply contained {bad} script. Use only Kannada "
                          "script, Devanagari or English letters.")
    raise LLMError("; ".join(errors) or "all providers failed")


def _call(provider: str, model: str, system: str, messages: list[Msg], tools: list[ToolSpec],
          live: bool, max_tokens: int, primary_timeout_s: float | None = None) -> LLMReply:
    s = get_settings()
    if provider == "gemini":
        return gemini.generate(
            api_key=s.gemini_api_key, model=model, system=system, messages=messages, tools=tools,
            thinking="minimal" if live else "high", max_tokens=max_tokens if live else max_tokens * 4,
            timeout_s=primary_timeout_s or (s.llm_primary_timeout_s if live else 60),
        )
    return openrouter.generate(
        api_key=s.openrouter_api_key, model=model, system=system, messages=messages, tools=tools,
        max_tokens=max_tokens, timeout_s=10 if live else 60,
    )
