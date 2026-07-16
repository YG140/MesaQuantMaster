export function LoadingState({ label = "Carregando..." }: { label?: string }) {
  return <div className="state loading-state" role="status">{label}</div>;
}
