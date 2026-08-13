import type { CSSProperties } from "react";
import { toNumber } from "../../utils/formatters";

export function ScoreGauge({ label, value }: { label: string; value: string | number | null }) {
  const numeric = toNumber(value);
  const safeValue = numeric === null ? 0 : Math.min(100, Math.max(0, numeric));
  return (
    <div className="score-gauge" aria-label={`${label}: ${numeric === null ? "Indisponível" : `${safeValue}%`}`}>
      <div className="score-ring" style={{ "--score": `${safeValue * 3.6}deg` } as CSSProperties}>
        <strong>{numeric === null ? "—" : Math.round(safeValue)}</strong>
        <span>{numeric === null ? "Sem dados" : "/ 100"}</span>
      </div>
      <span>{label}</span>
    </div>
  );
}
