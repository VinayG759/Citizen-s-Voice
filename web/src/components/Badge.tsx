import type { ReactNode } from "react";

type Props = {
  tone?: "neutral" | "success" | "warning" | "danger";
  children: ReactNode;
};

export function Badge({ tone = "neutral", children }: Props) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
