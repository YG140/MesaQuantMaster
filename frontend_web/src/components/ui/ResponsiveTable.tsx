import { useLayoutEffect, useRef, type ReactNode } from "react";

/** Retains native table headers while exposing their labels in stacked layouts. */
export function ResponsiveTable({ children, className = "" }: { children: ReactNode; className?: string }) {
  const root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const table = root.current?.querySelector("table");
    if (!table) return;
    const labels = [...table.querySelectorAll("thead th")].map(header => header.textContent?.trim() ?? "");
    table.querySelectorAll("tbody tr").forEach(row => {
      [...row.children].forEach((cell, index) => cell.setAttribute("data-label", labels[index] ?? ""));
    });
  }, [children]);
  return <div ref={root} className={`table-wrap orbita-table ${className}`}>{children}</div>;
}
