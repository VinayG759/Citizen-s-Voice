"""One conversation with the clerk. Knows nothing about phones or browsers:
every channel hands it the caller's words and speaks back what it returns."""

import json
import logging
import time
from dataclasses import dataclass, field

from app.clerk.prompt import system_prompt
from app.llm import router
from app.llm.types import LLMError, Msg
from app.tools import clerk_tools as tools

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4  # per caller turn; then Gemma must speak
MAX_TURNS = 30  # per conversation

# Said when Gemma cannot be reached at all, per language.
SORRY = {
    "kn": "ಕ್ಷಮಿಸಿ, ಒಂದು ಸಣ್ಣ technical problem. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳ್ತೀರಾ?",
    "hi": "माफ़ कीजिए, एक छोटी technical problem है। क्या आप फिर से बताएंगे?",
    "en": "Sorry, a small technical problem. Could you say that again?",
}
# Said right after a successful filing: fixed wording, so the tracking ID is always read
# correctly and the caller doesn't wait for another model call.
FILED = {
    "kn": "ನಿಮ್ಮ complaint register ಆಗಿದೆ. Tracking ID {sid}. ಮತ್ತೊಮ್ಮೆ: {sid}. ಧನ್ಯವಾದಗಳು.",
    "hi": "आपकी complaint register हो गई है। Tracking ID {sid}. फिर से: {sid}. धन्यवाद।",
    "en": "Your complaint is registered. Tracking ID {sid}. Once more: {sid}. Thank you.",
}
GOODBYE = {
    "kn": "ಈ call ತುಂಬಾ ಉದ್ದ ಆಯ್ತು. ದಯವಿಟ್ಟು ಮತ್ತೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.",
    "hi": "यह call बहुत लंबी हो गई। कृपया फिर से call करें। धन्यवाद।",
    "en": "This conversation has gone on long. Please call again. Thank you.",
}


@dataclass
class TurnResult:
    reply: str
    language: str
    events: list[dict]
    llm_ms: int
    complaint: dict | None = None  # set on the turn the complaint gets filed
    ended: bool = False


@dataclass
class Conversation:
    call_id: int
    repo: object
    channel: str = "web"
    caller_hash: str | None = None
    caller_last4: str | None = None
    language: str = "kn-IN"
    messages: list[Msg] = field(default_factory=list)
    state: tools.ToolState = field(default_factory=tools.ToolState)

    def turn(self, caller_text: str, language: str | None = None) -> TurnResult:
        if language:
            self.language = language
        lang = self.language.split("-")[0]
        self.state.caller_turn += 1
        start = len(self.messages)
        self.messages.append(Msg("user", caller_text))
        events: list[dict] = []
        llm_ms = 0

        if self.state.caller_turn > MAX_TURNS:
            return TurnResult(GOODBYE.get(lang, GOODBYE["en"]), self.language, events, 0, ended=True)

        filed_before = self.state.filed
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            last_round = round_ == MAX_TOOL_ROUNDS
            try:
                reply = router.generate(
                    system=system_prompt(self.state, self.language),
                    messages=self.messages,
                    tools=[] if last_round else tools.SPECS,
                    mode="live",
                    caller_language=self.language,
                )
            except LLMError as e:
                log.error("clerk: no LLM reply: %s", e)
                events.append(_event("decision", text="Gemma unreachable; asked caller to repeat", error=str(e)))
                del self.messages[start:]  # drop this half-finished turn; the caller repeats it cleanly
                self.state.caller_turn -= 1
                return TurnResult(SORRY.get(lang, SORRY["en"]), self.language, events, llm_ms)

            llm_ms += reply.ms
            if reply.thought:
                events.append(_event("thought", text=reply.thought[:600], provider=reply.provider))

            if not reply.tool_calls:
                text = reply.text or SORRY.get(lang, SORRY["en"])
                self.messages.append(Msg("model", text))
                events.append(_event("decision", text="spoke", provider=reply.provider, model=reply.model, ms=reply.ms))
                complaint = None
                if self.state.filed is not None and filed_before is None:
                    complaint = {"tracking_id": self.state.filed.tracking_id}
                return TurnResult(text, self.language, events, llm_ms, complaint)

            self.messages.append(Msg("model", reply.text, tool_calls=reply.tool_calls))
            for call in reply.tool_calls:
                events.append(_event("tool_call", tool=call.name, args=call.args, provider=reply.provider, ms=reply.ms))
                result = self._run_tool(call.name, call.args)
                events.append(_event("tool_result", tool=call.name, result=result))
                self.messages.append(Msg("tool", tool_call_id=call.id, tool_name=call.name, tool_result=result))

            if filed_before is None and self.state.filed is not None:
                sid = tools.spoken_id(self.state.filed.tracking_number)
                text = FILED.get(lang, FILED["en"]).format(sid=sid)
                self.messages.append(Msg("model", text))
                events.append(_event("decision", text="filed; confirmed the tracking ID to the caller"))
                return TurnResult(text, self.language, events, llm_ms,
                                  {"tracking_id": self.state.filed.tracking_id})

        # Unreachable: the last round offers no tools, so Gemma must speak.
        return TurnResult(SORRY.get(lang, SORRY["en"]), self.language, events, llm_ms)

    def _run_tool(self, name: str, args: dict) -> dict:
        t0 = time.perf_counter()
        try:
            if name == "find_place":
                out = tools.find_place(self.state, str(args.get("query", "")), args.get("area"))
            elif name == "file_complaint":
                info = {"language": self.language, "caller_hash": self.caller_hash,
                        "caller_last4": self.caller_last4, "channel": self.channel}
                out = tools.file_complaint(self.state, self.repo, info, **args)
            elif name == "get_complaint_status":
                out = tools.get_complaint_status(self.repo, str(args.get("tracking_id", "")))
            elif name == "raise_emergency":
                out = tools.raise_emergency(self.state, str(args.get("reason", "")))
            else:
                out = {"error": f"unknown tool {name}"}
        except Exception as e:  # a tool bug must not kill the call
            log.exception("tool %s failed", name)
            out = {"error": "tool failed", "detail": type(e).__name__}
        out_size = len(json.dumps(out, ensure_ascii=False))
        log.info("tool %s %.0fms %dB", name, (time.perf_counter() - t0) * 1000, out_size)
        return out


def _event(kind: str, **payload) -> dict:
    return {"kind": kind, "at": time.time(), **payload}
