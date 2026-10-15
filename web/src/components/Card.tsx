import type { ReactNode } from "react";

type Props = {
  title?: string;
  children: ReactNode;
};

export function Card({ title, children }: Props) {
  return (
    <section className="card" aria-label={title}>
      {title && <h2 className="card__title">{title}</h2>}
      {children}
    </section>
  );
}
