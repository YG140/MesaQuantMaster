import type { ReactNode } from "react";

export function Card({ children, title, className = "" }: { children: ReactNode; title?: string; className?: string }) {
  return (
    <section className={`card quantum-card ${className}`.trim()}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}
