import type { ReactNode } from "react";

type Props = {
  icon: ReactNode;
  title: string;
  /** What this place is, and the one action that fills it (UI rule 3). */
  children: ReactNode;
};

export function EmptyState({ icon, title, children }: Props) {
  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden="true">
        {icon}
      </span>
      <h3 className="empty__title">{title}</h3>
      <div>{children}</div>
    </div>
  );
}
