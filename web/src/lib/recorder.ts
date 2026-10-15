/** Browser microphone recording. Stops by itself after MAX_MS so a turn stays under Sarvam's limit. */

export const MAX_MS = 30_000;

export type Recording = { blob: Blob; filename: string };

function pickType(): { mime: string; ext: string } {
  const options = [
    { mime: "audio/webm;codecs=opus", ext: "webm" },
    { mime: "audio/webm", ext: "webm" },
    { mime: "audio/mp4", ext: "m4a" }, // Safari
    { mime: "audio/ogg;codecs=opus", ext: "ogg" },
  ];
  return options.find((o) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(o.mime)) ?? options[0];
}

export function microphoneSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
}

/** Starts recording. Call the returned stop() to finish; it resolves with the audio. */
export async function startRecording(onAutoStop: () => void): Promise<() => Promise<Recording>> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const { mime, ext } = pickType();
  const recorder = new MediaRecorder(stream, { mimeType: mime });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise<Recording>((resolve) => {
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop()); // release the mic (the browser's red dot goes away)
      resolve({ blob: new Blob(chunks, { type: mime.split(";")[0] }), filename: `speech.${ext}` });
    };
  });
  recorder.start();
  const timer = window.setTimeout(onAutoStop, MAX_MS);
  return async () => {
    window.clearTimeout(timer);
    if (recorder.state !== "inactive") recorder.stop();
    return done;
  };
}

function play(src: string, cleanup?: () => void): Promise<void> {
  const audio = new Audio(src);
  return new Promise((resolve) => {
    const done = () => {
      cleanup?.();
      resolve();
    };
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(done); // autoplay blocked: the text is on screen anyway
  });
}

export function playBase64Wav(b64: string | null): Promise<void> {
  return b64 ? play(`data:audio/wav;base64,${b64}`) : Promise.resolve();
}

/** Fetch the clerk's latest reply as speech and play it. Silent (text only) if that fails. */
export async function playClerkReply(sessionId: string): Promise<void> {
  const form = new FormData();
  form.append("session_id", sessionId);
  try {
    const r = await fetch("/api/try/speak", { method: "POST", body: form });
    if (!r.ok) return;
    const url = URL.createObjectURL(await r.blob());
    await play(url, () => URL.revokeObjectURL(url));
  } catch {
    // network hiccup: the reply is already on screen
  }
}
