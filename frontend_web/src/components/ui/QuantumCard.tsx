import type { ReactNode } from "react";

export function QuantumCard({
  children,
  className = "",
  glow = false,
}: {
  children: ReactNode;
  className?: string;
  glow?: boolean;
}) {
  return <section className={`quantum-card ${glow ? "quantum-card-glow" : ""} ${className}`}>{children}</section>;
}
