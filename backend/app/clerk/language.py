"""Which language is this call in? Chosen by the caller's first reply, then kept.

The greeting asks callers to simply speak in the language they want. Their first reply sets the
language — either by naming it ("English", "ಕನ್ನಡ") or just by speaking it. After that the language
stays put: a stray English word, or one misheard sentence, does not flip the call (a real call on
16 Oct switched language mid-sentence). It changes only if the caller names another language, or
clearly speaks another language for two turns in a row.
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
    _other: str | None = None
    _other_turns: int = 0

    def update(self, heard: str | None, text: str) -> str:
        """Feed one caller turn (the detected language and the words); returns the call's language."""
        named = named_language(text)
        # A short reply that names a language is a choice ("English", "ಕನ್ನಡದಲ್ಲಿ ಮಾತಾಡಿ").
        if named and len(re.findall(r"\w+", text)) <= 6:
            self.language, self.locked, self._other_turns = named, True, 0
            return self.language
        heard = spoken_form(heard)
        if not heard:
            return self.language
        if not self.locked:
            self.language, self.locked = heard, True
        elif heard != self.language:
            self._other_turns = self._other_turns + 1 if heard == self._other else 1
            self._other = heard
            if self._other_turns >= SWITCH_AFTER:
                self.language, self._other_turns = heard, 0
        else:
            self._other_turns = 0
        return self.language
