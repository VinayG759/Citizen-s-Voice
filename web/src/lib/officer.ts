/** The officer's sign-in, kept for this browser tab only (closing the tab signs out). */

const KEY = "cv-officer-token";

export function officerToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null; // storage blocked (private mode, previews): simply not signed in
  }
}

export function setOfficerToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    // ignore: the page still works, the officer just signs in again next time
  }
  window.dispatchEvent(new Event("cv-officer-change"));
}
