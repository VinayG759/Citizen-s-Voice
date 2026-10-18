"""Gemma's photo check: whatever Gemma replies (or fails to), people see a clean, honest verdict."""

from app import vision
from app.llm.types import LLMError, LLMReply

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
COMPLAINT = {"summary_en": "Pothole near the bus stop", "category": "road", "place_name": "8th Cross"}


def fake_gemma(monkeypatch, text=None, error=None):
    """Replace the router; returns the list of calls it received."""
    calls = []

    def generate(**kw):
        calls.append(kw)
        if error:
            raise error
        return LLMReply(text, [], "gemini", "gemma-4-31b-it", 900)

    monkeypatch.setattr(vision.router, "generate", generate)
    return calls


def test_the_real_image_type_comes_from_the_bytes_not_the_label():
    assert vision.image_type(JPEG) == "image/jpeg" and vision.image_type(PNG) == "image/png"
    assert vision.image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert vision.image_type(b"\x00\x00\x00\x18ftypheic") == "image/heic"
    assert vision.image_type(b"<!DOCTYPE html><html>") is None and vision.image_type(b"") is None


def test_a_fenced_json_reply_is_read(monkeypatch):
    # Seen live (17 Oct): Gemma wraps its answer in ```json fences.
    calls = fake_gemma(monkeypatch, '```json\n{"looks_fixed": "no", "reason": "The pothole is still there.", '
                                    '"same_place_likely": null}\n```')
    v = vision.check_fix(("text/plain", JPEG), COMPLAINT)
    assert v["looks_fixed"] == "no" and v["reason"] == "The pothole is still there." and v["model"] == "gemma-4-31b-it"
    sent = calls[0]["messages"][0]
    assert sent.images == [("image/jpeg", JPEG)]  # the true type is sent, not the upload's label
    assert calls[0]["mode"] == "background" and "Pothole near the bus stop" in sent.text


def test_json_after_a_sentence_with_braces_is_still_found(monkeypatch):
    fake_gemma(monkeypatch, 'Looking at it {carefully}: {"looks_fixed": "YES", "reason": "Fresh asphalt"} done.')
    assert vision.check_fix(("image/jpeg", JPEG), COMPLAINT)["looks_fixed"] == "yes"


def test_junk_or_empty_replies_give_unclear(monkeypatch):
    for junk in ("I think it is fixed", "", "[1, 2, 3]", '{"looks_fixed": '):
        fake_gemma(monkeypatch, junk)
        v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT)
        assert v["looks_fixed"] == "unclear" and v["reason"] == "Gemma's answer could not be read."


def test_partial_or_odd_answers_are_cleaned(monkeypatch):
    fake_gemma(monkeypatch, '{"looks_fixed": "probably", "same_place_likely": "yes", "secret": "x", '
                            '"reason": "' + "very long " * 100 + '"}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/jpeg", PNG))
    assert v["looks_fixed"] == "unclear" and v["same_place_likely"] is None  # "yes" is not a true/false
    assert "secret" not in v and len(v["reason"]) <= vision.REASON_CHARS
    fake_gemma(monkeypatch, '{"looks_fixed": "no"}')
    assert vision.check_fix(("image/jpeg", JPEG), COMPLAINT)["reason"] == "Gemma gave no reason."


def test_same_place_is_only_judged_against_the_citizens_photo(monkeypatch):
    # Seen live: with no citizen photo, Gemma still answered same_place_likely: false.
    fake_gemma(monkeypatch, '{"looks_fixed": "unclear", "reason": "r", "same_place_likely": false}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT)
    assert v["same_place_likely"] is None and v["compared_with_citizen_photo"] is False
    calls = fake_gemma(monkeypatch, '{"looks_fixed": "no", "reason": "r", "same_place_likely": false}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/png", PNG))
    assert v["same_place_likely"] is False and v["compared_with_citizen_photo"] is True
    assert len(calls[0]["messages"][0].images) == 2 and "SECOND image" in calls[0]["messages"][0].text


def test_what_matches_and_differs_is_kept_short(monkeypatch):
    fake_gemma(monkeypatch, '{"looks_fixed": "yes", "reason": "r", "same_place_likely": true, '
                            '"matching": ["  the same   blue wall ", "", 7, "a tree", "a sign", "road markings", '
                            '"a lamp post", "a gate"], "differences": ["' + "x" * 200 + '"], "confidence": " HIGH "}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/png", PNG))
    assert v["matching"] == ["the same blue wall", "a tree", "a sign", "road markings", "a lamp post"]
    assert v["differences"] == ["x" * vision.ITEM_CHARS] and v["confidence"] == "high"


def test_odd_or_missing_comparison_fields_are_cleaned(monkeypatch):
    fake_gemma(monkeypatch, '{"looks_fixed": "no", "reason": "r", "matching": "a wall", "confidence": "certain"}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/png", PNG))
    assert v["matching"] == [] and v["differences"] == [] and v["confidence"] is None
    fake_gemma(monkeypatch, '{"looks_fixed": "no", "reason": "r"}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/png", PNG))
    assert v["matching"] == [] and v["differences"] == [] and v["confidence"] is None


def test_without_a_citizen_photo_nothing_is_said_to_match(monkeypatch):
    # Nothing to compare with: whatever Gemma lists, it cannot have seen it in both photos.
    fake_gemma(monkeypatch, '{"looks_fixed": "yes", "reason": "r", "matching": ["a wall"], '
                            '"differences": ["new asphalt"], "confidence": "medium"}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT)
    assert v["matching"] == [] and v["differences"] == [] and v["confidence"] == "medium"


def test_provider_failure_is_graceful(monkeypatch):
    fake_gemma(monkeypatch, error=LLMError("gemini ReadTimeout; openrouter HTTP 502"))
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT)
    assert v == {"looks_fixed": "unclear", "reason": "Gemma could not check the photo right now.",
                 "same_place_likely": None, "error": True}


def test_not_an_image_or_too_big_is_never_sent(monkeypatch):
    calls = fake_gemma(monkeypatch, '{"looks_fixed": "yes", "reason": "r"}')
    for bad in (b"<html>not a photo</html>", JPEG + b"\x00" * vision.MAX_IMAGE_BYTES, b""):
        v = vision.check_fix(("image/jpeg", bad), COMPLAINT)
        assert v["looks_fixed"] == "unclear" and v["error"] is True
    assert calls == []


def test_a_bad_citizen_photo_is_skipped_and_the_fix_still_checked(monkeypatch):
    calls = fake_gemma(monkeypatch, '{"looks_fixed": "yes", "reason": "Patched", "same_place_likely": true}')
    v = vision.check_fix(("image/jpeg", JPEG), COMPLAINT, before=("image/jpeg", b"<html>"))
    assert v["looks_fixed"] == "yes" and v["same_place_likely"] is None
    assert len(calls[0]["messages"][0].images) == 1 and "SECOND image" not in calls[0]["messages"][0].text


def test_problem_photo_answer_is_cleaned(monkeypatch):
    cats = ["road", "water"]
    fake_gemma(monkeypatch, '{"is_civic_problem": true, "category": "road", "severity": 4, '
                            '"what_i_see": "A deep pothole", "danger_to_life": false}')
    assert vision.look_at_problem(("image/jpeg", JPEG), cats) == {
        "is_civic_problem": True, "category": "road", "severity": 4, "what_i_see": "A deep pothole",
        "danger_to_life": False, "model": "gemma-4-31b-it"}
    fake_gemma(monkeypatch, '{"is_civic_problem": "maybe", "category": "aliens", "severity": 9, "danger_to_life": true}')
    v = vision.look_at_problem(("image/jpeg", JPEG), cats)
    assert v["is_civic_problem"] is None and v["category"] is None and v["severity"] is None
    fake_gemma(monkeypatch, error=LLMError("down"))
    assert vision.look_at_problem(("image/jpeg", JPEG), cats)["error"] is True
    assert vision.look_at_problem(("image/jpeg", b"GIF89a"), cats)["error"] is True


def test_the_photo_check_waits_less_for_google_than_other_background_jobs(monkeypatch):
    # An officer is waiting after "mark fixed": Google gets a short leash, then OpenRouter (17 Oct: 60 s felt broken).
    calls = fake_gemma(monkeypatch, '{"looks_fixed": "yes", "reason": "Patched."}')
    vision.check_fix(("image/jpeg", JPEG), COMPLAINT)
    assert calls[0]["primary_timeout_s"] == vision.get_settings().photo_check_google_timeout_s < 60


def test_the_router_gives_google_the_timeout_it_is_told(monkeypatch):
    from app.llm import router
    seen = []
    monkeypatch.setattr(router.get_settings(), "gemini_api_key", "test")  # never depend on the real .env
    monkeypatch.setattr(router.gemini, "generate", lambda **kw: seen.append(kw["timeout_s"]) or LLMReply("ok", [], "gemini", "m", 5))
    router.generate(system="s", messages=[], tools=[], mode="background", caller_language="en-IN", primary_timeout_s=20)
    router.generate(system="s", messages=[], tools=[], mode="background", caller_language="en-IN")
    assert seen == [20, 60]  # told: that; not told: the background default
