import { useEffect, useRef, useState, type FormEvent } from "react";
import { BrainCircuit, CheckCircle2, Mic, Send, Square } from "lucide-react";
import { AppHeader } from "./components/AppHeader";
import { Badge } from "./components/Badge";
import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { EmptyState } from "./components/EmptyState";
import { Toaster } from "./components/Toaster";
import { ApiError, postForm, postJson, userMessage } from "./lib/api";
import { microphoneSupported, playBase64Wav, playClerkReply, startRecording, type Recording } from "./lib/recorder";
import { describe, type ClerkEvent } from "./lib/steps";
import { toast } from "./lib/toast";



type TurnResponse = {
  caller_text: string;
  language: string;
  reply: string;
  events: ClerkEvent[];
  complaint: { tracking_id: string } | null;
  ended: boolean;
  timings: { stt_ms: number; llm_ms: number };
};

type Line = { who: "caller" | "clerk"; text: string; language?: string; ms?: number };

type Phase = "not-started" | "starting" | "idle" | "recording" | "thinking" | "speaking" | "ended";

const LANGUAGE_NAMES: Record<string, string> = { kn: "Kannada", hi: "Hindi", en: "English" };

/** After filing: an optional number, so we can call when an officer marks it fixed and ask if it really is.
 * Without it a browser citizen can't be reached (18 Oct). */
function CallbackNumber({ sessionId }: { sessionId: string }) {
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await postJson<{ last4: string }>("/api/try/contact", { session_id: sessionId, phone });
      setSaved(r.last4);
    } catch (err) {
      toast.error(err instanceof ApiError && err.status === 422 ? "Enter a 10-digit mobile number." : userMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (saved) return <p className="callback__done">We'll call the number ending {saved} when it's marked fixed.</p>;
  return (
    <form className="callback" onSubmit={save}>
      <label className="field__label" htmlFor="callback-phone">
        Want a call when it's fixed? Your mobile number (optional)
      </label>
      <div className="callback__row">
        <input
          id="callback-phone"
          className="input"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="98450 12345"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <Button type="submit" loading={busy} disabled={!phone.trim() || busy}>
          Save
        </Button>
      </div>
      <p className="callback__hint">Stored encrypted. Only the last 4 digits are ever shown, and it's deleted once you confirm the fix.</p>
    </form>
  );
}

export function TryPage() {
  const [phase, setPhase] = useState<Phase>("not-started");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [steps, setSteps] = useState<ClerkEvent[]>([]);
  const [complaint, setComplaint] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const stopRef = useRef<null | (() => Promise<Recording>)>(null);
  const micOk = microphoneSupported();
  const busy = phase === "thinking" || phase === "starting";

  async function begin() {
    setPhase("starting");
    try {
      const r = await postForm<{ session_id: string; greeting: string; greeting_audio: string | null }>("/api/try/start");
      setSessionId(r.session_id);
      setLines([{ who: "clerk", text: r.greeting, language: "kn-IN" }]);
      setSteps([]);
      setComplaint(null);
      setPhase("speaking");
      await playBase64Wav(r.greeting_audio);
      setPhase("idle");
    } catch (err) {
      toast.error(userMessage(err, "Couldn't start the conversation. Try again."));
      setPhase("not-started");
    }
  }

  async function send(form: FormData, pendingText?: string) {
    if (!sessionId) return;
    form.append("session_id", sessionId);
    setPhase("thinking");
    if (pendingText) setLines((l) => [...l, { who: "caller", text: pendingText }]);
    try {
      const r = await postForm<TurnResponse>("/api/try/turn", form);
      setLines((l) => {
        const base = pendingText ? l.slice(0, -1) : l;
        return [
          ...base,
          { who: "caller", text: r.caller_text, language: r.language },
          { who: "clerk", text: r.reply, language: r.language, ms: r.timings.stt_ms + r.timings.llm_ms },
        ];
      });
      setSteps((s) => [...s, ...r.events]);
      if (r.complaint) {
        setComplaint(r.complaint.tracking_id);
        toast.success(`Complaint ${r.complaint.tracking_id} filed`);
      }
      setPhase("speaking");
      await playClerkReply(sessionId);
      setPhase(r.ended ? "ended" : "idle");
    } catch (err) {
      if (pendingText) setLines((l) => l.slice(0, -1));
      if (err instanceof ApiError && err.status === 404) {
        toast.error("This conversation timed out. Start a new one.");
        setPhase("not-started");
        return;
      }
      toast.error(userMessage(err));
      setPhase("idle");
    }
  }

  async function toggleMic() {
    if (phase === "recording") {
      const stop = stopRef.current;
      stopRef.current = null;
      if (!stop) return;
      const rec = await stop();
      const form = new FormData();
      form.append("audio", rec.blob, rec.filename);
      await send(form);
      return;
    }
    try {
      stopRef.current = await startRecording(() => void toggleMicRef.current());
      setPhase("recording");
    } catch {
      toast.error("Microphone access was blocked. Allow it in your browser's address bar, or type instead.");
    }
  }
  // The 30-second auto-stop needs the latest toggleMic.
  const toggleMicRef = useRef(toggleMic);
  toggleMicRef.current = toggleMic;

  async function sendTyped(e: FormEvent) {
    e.preventDefault();
    const text = typed.trim();
    if (!text) return;
    setTyped("");
    const form = new FormData();
    form.append("text", text);
    await send(form, text);
  }

  // Keep the newest line in view.
  const endRef = useRef<HTMLDivElement>(null);
  // Braces matter: an effect's return value is called as its clean-up, and newer Chrome
  // returns a Promise from scrollIntoView — returning it crashed the page on the next update.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [lines]);

  return (
    <div className="page">
      <AppHeader>
        <a className="btn btn--secondary" href="/">
          Complaints
        </a>
      </AppHeader>

      <main className="page__main try">
        <section className="try__conversation" aria-label="Conversation">
          <Card title="Talk to the clerk">
            {phase === "not-started" || phase === "starting" ? (
              <EmptyState icon={<Mic size={32} />} title="Report a problem by voice">
                <p className="try__intro">
                  Speak in Kannada, Hindi or English — the way you talk every day. Gemma 4 will ask what it needs and
                  file the complaint.
                </p>
                <Button variant="primary" loading={phase === "starting"} onClick={begin}>
                  Start talking
                </Button>
              </EmptyState>
            ) : (
              <>
                <ol className="chat" aria-live="polite">
                  {lines.map((line, i) => (
                    <li key={i} className={`chat__line chat__line--${line.who}`}>
                      <span className="chat__who">
                        {line.who === "caller" ? "You" : "Clerk (Gemma 4)"}
                        {line.language && <Badge>{LANGUAGE_NAMES[line.language.split("-")[0]] ?? line.language}</Badge>}
                      </span>
                      <p className="chat__text">{line.text}</p>
                      {line.ms ? <span className="chat__meta">{(line.ms / 1000).toFixed(1)} s</span> : null}
                    </li>
                  ))}
                  {phase === "thinking" && (
                    <li className="chat__line chat__line--clerk">
                      <span className="chat__who">Clerk (Gemma 4)</span>
                      <p className="chat__text chat__text--pending">Gemma is thinking…</p>
                    </li>
                  )}
                </ol>
                <div ref={endRef} />

                {complaint && (
                  <div className="filed" role="status">
                    <CheckCircle2 size={20} aria-hidden="true" />
                    <span>
                      Complaint <strong>{complaint}</strong> filed. It now appears on the{" "}
                      <a href="/">complaints page</a>.
                    </span>
                  </div>
                )}
                {complaint && sessionId && <CallbackNumber sessionId={sessionId} />}

                {phase === "ended" ? (
                  <Button variant="primary" onClick={begin}>
                    Start a new conversation
                  </Button>
                ) : (
                  <div className="controls">
                    <Button
                      variant={phase === "recording" ? "danger" : "primary"}
                      onClick={toggleMic}
                      disabled={!micOk || busy || phase === "speaking"}
                      title={micOk ? undefined : "This browser can't record audio. Type instead."}
                      aria-pressed={phase === "recording"}
                    >
                      {phase === "recording" ? (
                        <>
                          <Square size={16} aria-hidden="true" /> Stop and send
                        </>
                      ) : (
                        <>
                          <Mic size={16} aria-hidden="true" /> Speak
                        </>
                      )}
                    </Button>
                    <form className="controls__type" onSubmit={sendTyped}>
                      <label className="visually-hidden" htmlFor="typed">
                        Or type your message
                      </label>
                      <input
                        id="typed"
                        className="input"
                        value={typed}
                        onChange={(e) => setTyped(e.target.value)}
                        placeholder="Or type, e.g. road alli tumba potholes ide"
                        disabled={busy || phase === "recording"}
                        maxLength={1000}
                        autoComplete="off"
                      />
                      <Button type="submit" variant="secondary" disabled={busy || !typed.trim()} aria-label="Send message">
                        <Send size={16} aria-hidden="true" />
                      </Button>
                    </form>
                  </div>
                )}
                {phase === "recording" && <p className="controls__hint">Listening… press Stop when you've finished (30 s max).</p>}
              </>
            )}
          </Card>
        </section>

        <aside className="try__mind" aria-label="Gemma's steps">
          <Card title="Gemma's steps">
            {steps.length === 0 ? (
              <EmptyState icon={<BrainCircuit size={28} />} title="Nothing yet">
                <p>Each look-up, check and decision Gemma makes appears here as it happens.</p>
              </EmptyState>
            ) : (
              <ol className="steps">
                {steps.map((e, i) => (
                  <li key={i} className={`steps__item steps__item--${e.kind}`}>
                    {describe(e)}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </aside>
      </main>
      <Toaster />
    </div>
  );
}
