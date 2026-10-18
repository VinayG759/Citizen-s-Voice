import { useEffect, useRef, useState } from "react";
import { ClipboardList, Building2, Map as MapIcon, Menu, Mic, Newspaper, Radio, Siren, TrendingUp, X, type LucideIcon } from "lucide-react";
import { OfficerSignIn } from "./OfficerSignIn";
import { SystemStatus } from "./SystemStatus";
import { TrackBox } from "./TrackBox";
import { Link, useLocation } from "../lib/router";
import { useShell } from "../ShellContext";

export const NAV: { group: string; items: { to: string; label: string; icon: LucideIcon }[] }[] = [
  {
    group: "Work",
    items: [
      { to: "/", label: "Live desk", icon: Radio },
      { to: "/complaints", label: "Complaints", icon: ClipboardList },
      { to: "/emergencies", label: "Emergencies", icon: Siren },
      { to: "/map", label: "Map", icon: MapIcon },
    ],
  },
  {
    group: "Insight",
    items: [
      { to: "/offices", label: "Offices", icon: Building2 },
      { to: "/emerging", label: "Emerging issues", icon: TrendingUp },
      { to: "/brief", label: "Morning brief", icon: Newspaper },
    ],
  },
];

export function currentPage(pathname: string) {
  return NAV.flatMap((g) => g.items).find((i) => i.to === pathname);
}

function Brand() {
  return (
    <Link to="/" className="brand">
      <img src="/favicon.svg" alt="" width={28} height={28} />
      <span className="brand__name brand__name--sm">Citizen's Voice</span>
    </Link>
  );
}

/** The navigation and footer, shared by the desktop sidebar and the phone drawer. */
function NavContent() {
  const { pathname } = useLocation();
  const { status, recheck, live } = useShell();
  return (
    <>
      <nav aria-label="Main" className="nav">
        {NAV.map((g) => (
          <div key={g.group} className="nav__group">
            <p className="nav__heading">{g.group}</p>
            {g.items.map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to} className="nav__link" aria-current={to === pathname ? "page" : undefined}>
                <Icon size={16} aria-hidden="true" />
                {label}
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="nav__footer">
        <a className="btn btn--primary" href="/try">
          <Mic size={16} aria-hidden="true" /> Try it in your browser
        </a>
        <TrackBox />
        <SystemStatus status={status} onRetry={recheck} live={live} />
        <OfficerSignIn />
      </div>
    </>
  );
}

/** Desktop and tablet: a fixed sidebar. */
export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Sidebar">
      <Brand />
      <NavContent />
    </aside>
  );
}

/** Phones: a slim top bar, and a menu that slides in over the page. Escape closes it; focus moves in and back out. */
export function MobileBar() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  // Picking a page closes the menu.
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    setOpen(false);
  }

  // While open: Escape closes it, the page behind does not scroll, focus goes into the menu and back out.
  useEffect(() => {
    if (!open) return;
    const button = menuButton.current;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      button?.focus();
    };
  }, [open]);

  return (
    <>
      <header className="topbar">
        <Brand />
        <div className="topbar__right">
          <span className="topbar__page">{currentPage(pathname)?.label}</span>
          <button
            ref={menuButton}
            type="button"
            className="topbar__menu"
            onClick={() => setOpen(true)}
            aria-expanded={open}
            aria-controls="mobile-menu"
          >
            <Menu size={20} aria-hidden="true" />
            <span className="visually-hidden">Open menu</span>
          </button>
        </div>
      </header>
      {open && (
        <div className="drawer">
          <div className="drawer__scrim" onClick={() => setOpen(false)} />
          <div id="mobile-menu" className="drawer__panel" role="dialog" aria-modal="true" aria-label="Menu">
            <div className="drawer__head">
              <Brand />
              <button ref={closeButton} type="button" className="topbar__menu" onClick={() => setOpen(false)}>
                <X size={20} aria-hidden="true" />
                <span className="visually-hidden">Close menu</span>
              </button>
            </div>
            <NavContent />
          </div>
        </div>
      )}
    </>
  );
}
