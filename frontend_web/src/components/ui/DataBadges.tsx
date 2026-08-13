export function DataStatusBadge({ status }: { status?: string | null }) {
  const normalized = status?.toLowerCase() ?? "unavailable";
  const label = normalized === "live" ? "Dados atuais" : normalized === "partial" ? "Dados parciais" : "Dados indisponíveis";
  return <span className={`status-badge status-${normalized}`}>{label}</span>;
}
