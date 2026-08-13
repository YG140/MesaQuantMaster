export function MetricCard({ label, value, tone, helper }: { label: string; value: string | number; tone?: "good" | "bad"; helper?: string }) {
  return (
    <div className={`metric-card ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </div>
  );
}
