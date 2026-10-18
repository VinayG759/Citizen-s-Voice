"""Gemma looks at photos: a citizen's photo of a problem, and an officer's photo of the fix.

Gemma 4 31B (images in, reasoning on). Its answer is ADVICE shown to people — it never closes a
complaint by itself: the citizen's own "yes, it's fixed" decides.

Everything Gemma returns is cleaned by code before anyone sees it: only known fields, only allowed
values, a short reason. A photo that is not really an image, or is too big, is never sent.
"""

import json
import logging

from app.llm import router
from app.llm.types import LLMError, Msg
from app.settings import get_settings

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5_000_000  # same cap as the upload; two of these stay well under Gemini's 20 MB request limit
REASON_CHARS = 300
LIST_ITEMS = 5  # matching / differences: a few short things a person can scan
ITEM_CHARS = 80
CONFIDENCE = ("low", "medium", "high")

FIX_PROMPT = """You check repair work for a city complaints office. The complaint was:
"{summary}" (category: {category}, place: {place}).
The FIRST image is the officer's photo of the finished repair.{before}
Does the photo show this problem fixed? Reply with JSON only:
{{"looks_fixed": "yes" | "no" | "unclear", "reason": "<one short sentence an officer can read>",
  "same_place_likely": true | false | null,
  "matching": ["<things seen in both photos: a wall, a tree, a sign, road markings>"],
  "differences": ["<what changed between the photos>"],
  "confidence": "low" | "medium" | "high"}}"""

PROBLEM_PROMPT = """A citizen sent this photo with a complaint to a city helpline in Bengaluru.
What problem does it show? Reply with JSON only:
{{"is_civic_problem": true | false, "category": "<one of: {categories}>",
  "severity": 1-5, "what_i_see": "<one short sentence>", "danger_to_life": true | false}}"""


def image_type(data: bytes) -> str | None:
    """The real image type from the file's first bytes (the upload's own label can say anything)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
        return "image/heic"
    return None


def _usable(photo: tuple[str, bytes] | None) -> tuple[str, bytes] | None:
    """(real type, bytes) if this is an image we can send, else None."""
    if not photo or not photo[1] or len(photo[1]) > MAX_IMAGE_BYTES:
        return None
    mime = image_type(photo[1])
    return (mime, photo[1]) if mime else None


def read_json(text: str) -> dict | None:
    """The first JSON object in Gemma's reply (it sometimes wraps it in ```json fences or a sentence)."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _bool(v) -> bool | None:
    return v if isinstance(v, bool) else None


def _text(v) -> str:
    return " ".join(v.split())[:REASON_CHARS] if isinstance(v, str) else ""


def _items(v) -> list[str]:
    """At most LIST_ITEMS short, non-empty strings; anything else is dropped."""
    if not isinstance(v, list):
        return []
    items = [" ".join(x.split())[:ITEM_CHARS] for x in v if isinstance(x, str)]
    return [x for x in items if x][:LIST_ITEMS]


def _unclear(reason: str, **extra) -> dict:
    return {"looks_fixed": "unclear", "reason": reason, "same_place_likely": None, **extra}


def check_fix(photo: tuple[str, bytes], complaint: dict, before: tuple[str, bytes] | None = None) -> dict:
    photo = _usable(photo)
    if photo is None:
        return _unclear("Gemma could not read this photo (not a JPEG, PNG, WebP or HEIC image, or over 5 MB).",
                        error=True)
    before = _usable(before)  # a bad citizen photo is skipped: the fix photo is still checked on its own
    images = [photo] + ([before] if before else [])
    prompt = FIX_PROMPT.format(
        summary=complaint.get("summary_en", ""), category=complaint.get("category", ""),
        place=complaint.get("place_name", ""),
        before=" The SECOND image is the citizen's photo of the problem when they reported it." if before else "")
    try:
        reply = router.generate(system="You judge photos carefully and honestly. Never guess beyond what is visible.",
                                messages=[Msg("user", prompt, images=images)], tools=[], mode="background",
                                caller_language="en-IN", max_tokens=500,
                                primary_timeout_s=get_settings().photo_check_google_timeout_s)
    except LLMError as e:
        log.warning("photo check failed: %s", e)
        return _unclear("Gemma could not check the photo right now.", error=True)
    raw = read_json(reply.text)
    if raw is None:
        log.warning("photo check: no JSON in Gemma's reply")
        return _unclear("Gemma's answer could not be read.", model=reply.model)
    looks = str(raw.get("looks_fixed", "")).strip().lower()
    confidence = str(raw.get("confidence", "")).strip().lower()
    return {
        "looks_fixed": looks if looks in ("yes", "no", "unclear") else "unclear",
        "reason": _text(raw.get("reason")) or "Gemma gave no reason.",
        # Without the citizen's photo there is nothing to compare: Gemma cannot know, whatever it says.
        "same_place_likely": _bool(raw.get("same_place_likely")) if before else None,
        "matching": _items(raw.get("matching")) if before else [],
        "differences": _items(raw.get("differences")) if before else [],
        "confidence": confidence if confidence in CONFIDENCE else None,
        "compared_with_citizen_photo": before is not None,
        "model": reply.model,
    }


def look_at_problem(photo: tuple[str, bytes], categories: list[str]) -> dict:
    photo = _usable(photo)
    if photo is None:
        return {"is_civic_problem": None, "what_i_see": "Gemma could not read this photo.", "error": True}
    prompt = PROBLEM_PROMPT.format(categories=", ".join(categories))
    try:
        reply = router.generate(system="You describe photos of civic problems accurately and briefly.",
                                messages=[Msg("user", prompt, images=[photo])], tools=[], mode="background",
                                caller_language="en-IN", max_tokens=300)
    except LLMError as e:
        log.warning("problem photo check failed: %s", e)
        return {"is_civic_problem": None, "what_i_see": "Gemma could not look at the photo right now.", "error": True}
    raw = read_json(reply.text)
    if raw is None:
        return {"is_civic_problem": None, "what_i_see": "Gemma's answer could not be read.", "model": reply.model}
    severity = raw.get("severity")
    return {
        "is_civic_problem": _bool(raw.get("is_civic_problem")),
        "category": raw.get("category") if raw.get("category") in categories else None,
        "severity": severity if type(severity) is int and 1 <= severity <= 5 else None,
        "what_i_see": _text(raw.get("what_i_see")),
        "danger_to_life": _bool(raw.get("danger_to_life")),
        "model": reply.model,
    }
