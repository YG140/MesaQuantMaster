import type { ReactNode } from "react";

export function Card({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <section className="card">
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}
