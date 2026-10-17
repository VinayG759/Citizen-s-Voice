import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  /** Shows a spinner on this button and disables it (UI rule 3: feedback where the action started). */
  loading?: boolean;
  children: ReactNode;
  ref?: Ref<HTMLButtonElement>;
};

export function Button({ variant = "secondary", size = "md", loading = false, disabled, children, ...rest }: Props) {
  const classes = ["btn", `btn--${variant}`, size === "sm" ? "btn--sm" : ""].filter(Boolean).join(" ");
  return (
    <button type="button" className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
