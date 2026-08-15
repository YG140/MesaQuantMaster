export function LoadingState({ label = "Carregando..." }: { label?: string }) {
  return <div className="state loading-state" role="status"><div className="loading-orbit" /><span>{label}</span><div className="skeleton-lines"><i /><i /><i /></div></div>;
}
