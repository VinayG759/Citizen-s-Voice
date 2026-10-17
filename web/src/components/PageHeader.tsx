import type { ReactNode } from "react";

type Props = {
  title: string;
  /** One line saying what this page is for. */
  children?: ReactNode;
  /** Buttons and filters on the right. */
  actions?: ReactNode;
};

export function PageHeader({ title, children, actions }: Props) {
  return (
    <div className="pagehead">
      <div>
        <h1 className="pagehead__title">{title}</h1>
        {children && <p className="pagehead__sub">{children}</p>}
      </div>
      {actions && <div className="pagehead__actions">{actions}</div>}
    </div>
  );
}
