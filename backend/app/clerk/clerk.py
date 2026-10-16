"""One conversation with the clerk. Knows nothing about phones or browsers:
every channel hands it the caller's words and speaks back what it returns."""

import json
import logging
import time
from dataclasses import dataclass, field

from app import events
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
    "ta": "மன்னிக்கவும், ஒரு சிறிய technical problem. மீண்டும் சொல்ல முடியுமா?",
    "te": "క్షమించండి, చిన్న technical problem. మళ్ళీ చెప్పగలరా?",
}
# Said right after a successful filing: fixed wording, so the tracking ID is always read
# correctly and the caller doesn't wait for another model call.
FILED = {
    "kn": "ಸರಿ, ನಿಮ್ಮ complaint register ಆಗಿದೆ. ನಿಮ್ಮ tracking ID... {sid}. ಇನ್ನೊಂದ್ಸಲ ಹೇಳ್ತೀನಿ... {sid}. "
          "Call ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು.",
    "hi": "ठीक है, आपकी complaint register हो गई है। आपका tracking ID... {sid}. एक बार फिर... {sid}. "
          "Call करने के लिए धन्यवाद।",
    "en": "Okay, your complaint is registered. Your tracking ID is... {sid}. Once more... {sid}. "
          "Thank you for calling.",
    "ta": "உங்கள் complaint பதிவு செய்யப்பட்டது. Tracking ID {sid}. மீண்டும்: {sid}. நன்றி.",
    "te": "మీ complaint నమోదు అయింది. Tracking ID {sid}. మళ్ళీ: {sid}. ధన్యవాదాలు.",
}
# Said when the caller's report was added to a problem others already reported.
ADDED = {
    "kn": "ಈ problem ಅನ್ನು ಈಗಾಗಲೇ report ಮಾಡಲಾಗಿದೆ. ನೀವು {n}ನೇ ವ್ಯಕ್ತಿ.{raised} Tracking ID {sid}. ಮತ್ತೊಮ್ಮೆ: {sid}. ಧನ್ಯವಾದಗಳು.",
    "hi": "यह problem पहले से report हो चुकी है। आप {n}वें व्यक्ति हैं।{raised} Tracking ID {sid}. फिर से: {sid}. धन्यवाद।",
    "en": "This problem was already reported. You are person number {n} to report it.{raised} Tracking ID {sid}. "
          "Once more: {sid}. Thank you.",
    "ta": "இந்த problem ஏற்கனவே report செய்யப்பட்டுள்ளது. நீங்கள் {n}-வது நபர்.{raised} Tracking ID {sid}. "
          "மீண்டும்: {sid}. நன்றி.",
    "te": "ఈ problem ఇప్పటికే report అయింది. మీరు {n}వ వ్యక్తి.{raised} Tracking ID {sid}. మళ్ళీ: {sid}. ధన్యవాదాలు.",
}
RAISED = {"kn": " ಇದರ priority ಹೆಚ್ಚಿಸಲಾಗಿದೆ.", "hi": " इसकी priority बढ़ा दी गई है।",
          "en": " Its priority has been raised.", "ta": " இதன் priority உயர்த்தப்பட்டது.",
          "te": " దీని priority పెంచబడింది."}
GOODBYE = {
    "kn": "ಈ call ತುಂಬಾ ಉದ್ದ ಆಯ್ತು. ದಯವಿಟ್ಟು ಮತ್ತೆ call ಮಾಡಿ. ಧನ್ಯವಾದಗಳು.",
    "hi": "यह call बहुत लंबी हो गई। कृपया फिर से call करें। धन्यवाद।",
    "en": "This conversation has gone on long. Please call again. Thank you.",
    "ta": "இந்த உரையாடல் நீண்டுவிட்டது. மீண்டும் call செய்யுங்கள். நன்றி.",
    "te": "ఈ సంభాషణ చాలా సేపు అయింది. దయచేసి మళ్ళీ call చేయండి. ధన్యవాదాలు.",
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
    _raised: bool = False

    def turn(self, caller_text: str, language: str | None = None) -> TurnResult:
        """One caller turn; the dashboard hears about it as it finishes."""
        result = self._turn(caller_text, language)
        events.publish("turn", call_id=self.call_id, channel=self.channel, caller=caller_text,
                       reply=result.reply, language=result.language, steps=result.events,
                       complaint=result.complaint)
        return result

    def _turn(self, caller_text: str, language: str | None = None) -> TurnResult:
        if language:
            # Sarvam can hear Urdu but not speak it; spoken Hindi and Urdu are mutually
            # understood, so an Urdu caller is answered in spoken Hindi.
            self.language = "hi-IN" if language.startswith("ur") else language
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
                if call.name == "file_complaint" and result.get("added_to_existing"):
                    self._raised = bool(result.get("priority_raised"))
                events.append(_event("tool_result", tool=call.name, result=result))
                self.messages.append(Msg("tool", tool_call_id=call.id, tool_name=call.name, tool_result=result))

            if filed_before is None and self.state.filed is not None:
                sid = tools.spoken_id(self.state.filed.tracking_number)
                if self.state.report_count:
                    raised = RAISED.get(lang, RAISED["en"]) if self._raised else ""
                    text = ADDED.get(lang, ADDED["en"]).format(sid=sid, n=self.state.report_count, raised=raised)
                else:
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
                out = tools.find_place(self.state, str(args.get("query", "")), args.get("area"), args.get("road"))
            elif name == "file_complaint":
                info = {"language": self.language, "caller_hash": self.caller_hash,
                        "caller_last4": self.caller_last4, "channel": self.channel}
                out = tools.file_complaint(self.state, self.repo, info, **args)
            elif name == "get_complaint_status":
                out = tools.get_complaint_status(self.repo, args.get("tracking_id"), self.caller_hash, self.channel)
            elif name == "find_nearby_complaints":
                out = tools.find_nearby_complaints(self.state, self.repo, str(args.get("place_id", "")),
                                                   str(args.get("category", "")))
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
