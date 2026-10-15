import type { ReactNode } from "react";

type Props = {
  /** Shown on the right: status, primary action. */
  children?: ReactNode;
};

export function AppHeader({ children }: Props) {
  return (
    <header className="page__header">
      <a className="brand" href="/">
        <img src="/favicon.svg" alt="" width={32} height={32} />
        <div>
          <h1 className="brand__name">Citizen's Voice</h1>
          <p className="brand__tagline">Report civic problems by phone, in your own language</p>
        </div>
      </a>
      {children && <div className="page__header-actions">{children}</div>}
    </header>
  );
}
