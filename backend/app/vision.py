"""Gemma looks at photos: a citizen's photo of a problem, and an officer's photo of the fix.

Gemma 4 31B (images in, reasoning on). Its answer is ADVICE shown to people — it never closes a
complaint by itself: the citizen's own "yes, it's fixed" decides.
"""

import json
import logging
import re

from app.llm import router
from app.llm.types import LLMError, Msg

log = logging.getLogger(__name__)

FIX_PROMPT = """You check repair work for a city complaints office. The complaint was:
"{summary}" (category: {category}, place: {place}).
The FIRST image is the officer's photo of the finished repair.{before}
Does the photo show this problem fixed? Reply with JSON only:
{{"looks_fixed": "yes" | "no" | "unclear", "reason": "<one short sentence an officer can read>",
  "same_place_likely": true | false | null}}"""

PROBLEM_PROMPT = """A citizen sent this photo with a complaint to a city helpline in Bengaluru.
What problem does it show? Reply with JSON only:
{{"is_civic_problem": true | false, "category": "<one of: {categories}>",
  "severity": 1-5, "what_i_see": "<one short sentence>", "danger_to_life": true | false}}"""


def _json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def check_fix(photo: tuple[str, bytes], complaint: dict, before: tuple[str, bytes] | None = None) -> dict:
    images = [photo] + ([before] if before else [])
    prompt = FIX_PROMPT.format(
        summary=complaint.get("summary_en", ""), category=complaint.get("category", ""),
        place=complaint.get("place_name", ""),
        before=" The SECOND image is the citizen's photo of the problem when they reported it." if before else "")
    try:
        reply = router.generate(system="You judge photos carefully and honestly. Never guess beyond what is visible.",
                                messages=[Msg("user", prompt, images=images)], tools=[], mode="background",
                                caller_language="en-IN", max_tokens=300)
    except LLMError as e:
        log.warning("photo check failed: %s", e)
        return {"looks_fixed": "unclear", "reason": "Gemma could not check the photo right now.", "error": True}
    verdict = _json(reply.text) or {"looks_fixed": "unclear", "reason": reply.text[:200]}
    if verdict.get("looks_fixed") not in ("yes", "no", "unclear"):
        verdict["looks_fixed"] = "unclear"
    verdict["model"] = reply.model
    return verdict


def look_at_problem(photo: tuple[str, bytes], categories: list[str]) -> dict:
    prompt = PROBLEM_PROMPT.format(categories=", ".join(categories))
    try:
        reply = router.generate(system="You describe photos of civic problems accurately and briefly.",
                                messages=[Msg("user", prompt, images=[photo])], tools=[], mode="background",
                                caller_language="en-IN", max_tokens=300)
    except LLMError as e:
        log.warning("problem photo check failed: %s", e)
        return {"is_civic_problem": None, "what_i_see": "Gemma could not look at the photo right now.", "error": True}
    return _json(reply.text) or {"is_civic_problem": None, "what_i_see": reply.text[:200]}
