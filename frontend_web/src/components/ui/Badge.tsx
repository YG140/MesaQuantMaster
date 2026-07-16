export function Badge({ children, tone = "neutral" }: { children: string; tone?: "neutral" | "warning" | "success" | "danger" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
