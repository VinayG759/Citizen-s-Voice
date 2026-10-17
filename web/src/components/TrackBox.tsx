import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Button } from "./Button";

/** Anyone with a tracking number can see where their complaint is. */
export function TrackBox() {
  const [value, setValue] = useState("");
  function go(e: FormEvent) {
    e.preventDefault();
    const digits = value.replace(/\D/g, "");
    if (digits) window.location.href = `/c/CV-${digits}`; // a citizen page has no sidebar, so a real page load
  }
  return (
    <form className="track" onSubmit={go} role="search">
      <input
        className="input input--sm"
        aria-label="Tracking number"
        placeholder="Track: CV-1004"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <Button size="sm" type="submit" aria-label="Track complaint">
        <Search size={14} aria-hidden="true" />
      </Button>
    </form>
  );
}
