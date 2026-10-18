"""The officer's note reaches each chat citizen in their own language (18 Oct: officers mostly write
English; a Kannada reporter got it as typed). Sarvam translates; if it can't, the note goes as written.
Fake Sarvam, fake database, fake Telegram. No network."""

import httpx
import pytest
from cryptography.fernet import Fernet

from app import followup
from app.contact import seal
from app.settings import get_settings
from app.speech import sarvam

REAL_TRANSLATE = sarvam.translate  # conftest swaps it for a fake in every test; the unit tests need the real one
NOTE = "Crew sent, work starts Monday"
KN_NOTE = "ಸಿಬ್ಬಂದಿ ಕಳಿಸಲಾಗಿದೆ, ಸೋಮವಾರ ಕೆಲಸ ಶುರು"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setattr(get_settings(), "contact_encryption_key", Fernet.generate_key().decode())


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setitem(followup._chat_notifiers, "telegram", lambda chat_id, text: out.append((chat_id, text)))
    return out


def fake_translate(monkeypatch, result=KN_NOTE):
    """Replace Sarvam; returns the list of (text, target language) it was asked for."""
    calls = []
    monkeypatch.setattr(sarvam, "translate", lambda text, lang: calls.append((text, lang)) or result)
    return calls


def reporters(monkeypatch, *people):
    monkeypatch.setattr(followup.repo, "reporter_contacts", lambda n: list(people))


def test_a_kannada_reporter_gets_the_note_in_kannada_with_the_officers_own_words(monkeypatch, sent):
    calls = fake_translate(monkeypatch)
    reporters(monkeypatch, (seal("telegram", "222"), True, "kn-IN"))
    followup.notify_update(1013, "in_progress", NOTE)
    assert calls == [(NOTE, "kn-IN")]
    assert sent == [("222", f"CV-1013 ಬಗ್ಗೆ update: ನಿಮ್ಮ complaint ಮೇಲೆ ಕೆಲಸ ಶುರು ಆಗಿದೆ. "
                            f"Officer note: {KN_NOTE} (Officer wrote: {NOTE})")]


def test_an_english_reporter_needs_no_translation(monkeypatch, sent):
    calls = fake_translate(monkeypatch)
    reporters(monkeypatch, (seal("telegram", "111"), True, "en-IN"), (seal("telegram", "333"), False, None))
    followup.notify_update(1013, "in_progress", NOTE)
    assert calls == []
    assert all(text.endswith(f"Officer's note: {NOTE}") for _, text in sent) and len(sent) == 2


def test_two_kannada_reporters_mean_one_translation(monkeypatch, sent):
    calls = fake_translate(monkeypatch)
    reporters(monkeypatch, (seal("telegram", "222"), True, "kn-IN"), (seal("telegram", "444"), False, "kn-IN"),
              (seal("telegram", "555"), False, "hi-IN"))
    followup.notify_update(1013, "reopened", NOTE)
    assert calls == [(NOTE, "kn-IN"), (NOTE, "hi-IN")]
    assert len(sent) == 3


def test_if_sarvam_cannot_translate_the_note_goes_as_written(monkeypatch, sent):
    fake_translate(monkeypatch, result=None)
    reporters(monkeypatch, (seal("telegram", "222"), True, "kn-IN"))
    followup.notify_update(1013, "in_progress", NOTE)
    assert sent[0][1].endswith(f"Officer note: {NOTE}") and "Officer wrote" not in sent[0][1]


def test_no_note_means_no_translation(monkeypatch, sent):
    calls = fake_translate(monkeypatch)
    reporters(monkeypatch, (seal("telegram", "222"), True, "kn-IN"))
    followup.notify_update(1013, "in_progress", "   ")
    followup.notify_update(1013, "reopened")
    assert calls == [] and len(sent) == 2


def test_a_long_note_is_capped_on_both_sides():
    text = followup.update_text("in_progress", 1013, "kn-IN", "a" * 500, translated="ಅ" * 500)
    assert "ಅ" * 300 in text and "ಅ" * 301 not in text
    assert f"(Officer wrote: {'a' * 300})" in text and "a" * 301 not in text


# ---- sarvam.translate itself, against a fake HTTP reply ----

class Reply:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def fake_http(monkeypatch, reply=None, error=None):
    calls = []

    def post(url, **kw):
        calls.append((url, kw))
        if error:
            raise error
        return reply

    monkeypatch.setattr(sarvam.get_settings(), "sarvam_api_key", "test")  # never depend on the real .env
    monkeypatch.setattr(sarvam.httpx, "post", post)
    return calls


def test_translate_sends_the_note_and_reads_the_translation(monkeypatch):
    calls = fake_http(monkeypatch, Reply(200, {"translated_text": f"  {KN_NOTE} ", "source_language_code": "en-IN"}))
    assert REAL_TRANSLATE(NOTE, "kn-IN") == KN_NOTE
    url, kw = calls[0]
    assert url == sarvam.TRANSLATE_URL and kw["headers"] == {"api-subscription-key": "test"}
    assert kw["json"] == {"input": NOTE, "source_language_code": "auto", "target_language_code": "kn-IN",
                          "model": "mayura:v1"}
    assert kw["timeout"] == sarvam.TRANSLATE_TIMEOUT_S


@pytest.mark.parametrize("reply, error", [
    (Reply(429, {"error": "rate limited"}), None),
    (Reply(200, {"something_else": "x"}), None),
    (Reply(200, {"translated_text": "  "}), None),
    (Reply(200, ["not", "an", "object"]), None),
    (Reply(200, ValueError("not JSON")), None),
    (None, httpx.ReadTimeout("slow")),
])
def test_translate_gives_none_on_any_failure(monkeypatch, reply, error):
    fake_http(monkeypatch, reply, error)
    assert REAL_TRANSLATE(NOTE, "kn-IN") is None


def test_translate_without_a_key_never_calls_sarvam(monkeypatch):
    calls = fake_http(monkeypatch, Reply(200, {"translated_text": KN_NOTE}))
    monkeypatch.setattr(sarvam.get_settings(), "sarvam_api_key", "")
    assert REAL_TRANSLATE(NOTE, "kn-IN") is None and calls == []
