import { useEffect, useRef, useState, type FormEvent } from "react";
import { LogIn, LogOut, X } from "lucide-react";
import { Button } from "./Button";
import { ApiError, postJson, userMessage } from "../lib/api";
import { officerToken, setOfficerToken } from "../lib/officer";
import { toast } from "../lib/toast";

/** True while an officer is signed in on this tab; updates when they sign in or out. */
export function useOfficer(): boolean {
  const [signedIn, setSignedIn] = useState(() => !!officerToken());
  useEffect(() => {
    const update = () => setSignedIn(!!officerToken());
    window.addEventListener("cv-officer-change", update);
    return () => window.removeEventListener("cv-officer-change", update);
  }, []);
  return signedIn;
}

/** Header button: "Officer sign-in" opens a small dialog; "Sign out" when signed in. */
export function OfficerSignIn() {
  const signedIn = useOfficer();
  const [open, setOpen] = useState(false);
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function close() {
    setOpen(false);
    setPasscode("");
    setError(null);
    opener.current?.focus(); // focus returns to the button that opened the dialog
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!passcode.trim()) {
      setError("Enter the officer passcode.");
      return;
    }
    setBusy(true);
    try {
      const r = await postJson<{ token: string }>("/api/officer/login", { passcode });
      setOfficerToken(r.token);
      toast.success("Signed in as an officer. You can now update complaints.");
      close();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That passcode is wrong." : userMessage(err, "Couldn't sign in. Try again."));
    } finally {
      setBusy(false);
    }
  }

  if (signedIn)
    return (
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setOfficerToken(null);
          toast.info("Signed out.");
        }}
      >
        <LogOut size={14} aria-hidden="true" /> Sign out (officer)
      </Button>
    );

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)} ref={opener}>
        <LogIn size={14} aria-hidden="true" /> Officer sign-in
      </Button>
      {open && (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="officer-title" onClick={close}>
          <form className="modal__box" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h2 id="officer-title">Officer sign-in</h2>
              <button type="button" className="toast__close" aria-label="Close" onClick={close}>
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <label className="field__label" htmlFor="passcode">
              Passcode
            </label>
            <input
              id="passcode"
              ref={input}
              className="input"
              type="password"
              autoComplete="current-password"
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              aria-invalid={!!error}
              aria-describedby={error ? "passcode-error" : undefined}
            />
            {error && (
              <p id="passcode-error" className="field__error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" loading={busy}>
              Sign in
            </Button>
          </form>
        </div>
      )}
    </>
  );
}
