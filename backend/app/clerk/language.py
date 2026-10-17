"""Which language is this call in? Chosen by the caller's first reply, then kept.

The greeting asks callers to simply speak in the language they want. Their first reply sets the
language — either by naming it ("English", "ಕನ್ನಡ") or just by speaking it. After that the language
stays put: a stray English word, or one misheard sentence, does not flip the call (a real call on
16 Oct switched language mid-sentence). It changes only if the caller names another language, or
clearly speaks another language for two turns in a row.

A chat is different: the citizen reads every reply, so a wrong guess costs nothing, while asking
"shall we continue in Hindi?" at every change cost a turn each time (tester's report, 17 Oct). A chat
follows a clear change at once and never asks.
"""

import re
from dataclasses import dataclass

# What a caller might say to choose a language, in any of our scripts.
_NAMED = {
    "kn-IN": ("kannada", "ಕನ್ನಡ", "कन्नड़", "கன்னடம்", "కన్నడ"),
    "hi-IN": ("hindi", "ಹಿಂದಿ", "हिंदी", "हिन्दी", "இந்தி", "హిందీ"),
    "en-IN": ("english", "ಇಂಗ್ಲಿಷ್", "इंग्लिश", "अंग्रेज़ी", "अंग्रेजी", "ஆங்கிலம்", "ఇంగ్లీష్"),
    "ta-IN": ("tamil", "ತಮಿಳು", "तमिल", "தமிழ்", "తమిళం"),
    "te-IN": ("telugu", "ತೆಲುಗು", "तेलुगु", "தெலுங்கு", "తెలుగు"),
}
SWITCH_AFTER = 2  # turns in a row in another language before the call follows
CHAT_SWITCH_MIN_WORDS = 3  # "yes", "ok", "haudu sir": too short to tell a language by
_INDIAN_LETTERS = re.compile(r"[ऀ-෿]")  # Devanagari to Sinhala: every Indian script we hear


def named_language(text: str) -> str | None:
    """'English', 'ಕನ್ನಡದಲ್ಲಿ', 'Hindi please' → that language; None if no language is named."""
    t = text.lower()
    found = {code for code, words in _NAMED.items() if any(w in t for w in words)}
    return found.pop() if len(found) == 1 else None


def spoken_form(code: str | None) -> str | None:
    """Sarvam can hear Urdu but not speak it; spoken Hindi and Urdu are mutually understood."""
    if code and code.startswith("ur"):
        return "hi-IN"
    return code


@dataclass
class LanguageLock:
    language: str = "kn-IN"
    locked: bool = False
    instant: bool = False  # a chat: follow a clear change of language at once, never ask
    _other: str | None = None
    _other_turns: int = 0

    @property
    def pending(self) -> str | None:
        """The caller just spoke ANOTHER language for one turn: ask whether to switch to it."""
        return self._other if self._other_turns == 1 and self._other != self.language else None

    def update(self, heard: str | None, text: str) -> str:
        """Feed one caller turn (the detected language and the words); returns the call's language."""
        named = named_language(text)
        # A short reply that names a language is a choice ("English", "ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡಿ").
        if named and len(re.findall(r"\w+", text)) <= 6:
            self.language, self.locked, self._other_turns = named, True, 0
            return self.language
        heard = spoken_form(heard)
        if heard == "en-IN" and _INDIAN_LETTERS.search(text):
            # "Kadu Malleshwara Temple ಎದುರು": a name said inside Kannada gets labelled English. Someone
            # really speaking English writes no Indian letters, so this turn says nothing about the language.
            heard = None
        if not heard:
            return self.language
        if not self.locked:
            self.language, self.locked = heard, True
        elif self.instant:
            if heard != self.language and len(text.split()) >= CHAT_SWITCH_MIN_WORDS:
                self.language = heard
        elif heard != self.language:
            self._other_turns = self._other_turns + 1 if heard == self._other else 1
            self._other = heard
            if self._other_turns >= SWITCH_AFTER:
                self.language, self._other_turns = heard, 0
        else:
            self._other_turns = 0
        return self.language


# Unicode blocks of the scripts we speak, to tell which language a reply is actually written in.
_SCRIPT_LANG = (("kn-IN", 0x0C80, 0x0CFF), ("hi-IN", 0x0900, 0x097F), ("ta-IN", 0x0B80, 0x0BFF),
                ("te-IN", 0x0C00, 0x0C7F))


def written_in(text: str, default: str) -> str:
    """Which language's voice should read this reply: the script most of its letters are in.
    Latin-only text ("Okay, two weeks...") is English. Falls back to `default` for empty text."""
    counts = {lang: 0 for lang, _, _ in _SCRIPT_LANG}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
        for lang, lo, hi in _SCRIPT_LANG:
            if lo <= cp <= hi:
                counts[lang] += 1
    best = max(counts, key=counts.get)
    if counts[best]:
        return best  # Indian script present: that language (English words inside are normal)
    return "en-IN" if latin else default


def guess_language(text: str) -> str | None:
    """Typed text has no speech detector: judge by script. None keeps the current language."""
    if re.search(r"[ಀ-೿]", text):
        return "kn-IN"
    if re.search(r"[ऀ-ॿ]", text):
        return "hi-IN"
    if re.search(r"[A-Za-z]{3,}", text):
        return "en-IN"
    return None
