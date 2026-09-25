import { formatPercentBR } from "../../utils/formatters";

type AllocationItem = { name: string; value: number };
const COLORS = ["#47deeb", "#a994ff", "#ef80d8", "#6dacf8", "#69d6b7", "#ffc67d"];

/** Each ring has a fixed 0–100% scale; partial data is never renormalized. */
export function AllocationChart({ data }: { data: AllocationItem[] }) {
  const validData = data.filter(item => item.name.trim() && Number.isFinite(item.value) && item.value >= 0 && item.value <= 100);
  if (!validData.length) return <p>Composição não informada.</p>;
  return <figure className="orbita-allocation" aria-label="Gráfico de alocação">
    <svg viewBox="0 0 240 240" role="img" aria-label="Órbitas proporcionais: escala de zero a cem por cento por ativo">
      {validData.slice(0, 6).map((item, index) => <g key={item.name}>
        <circle cx="120" cy="120" r={102 - index * 13} fill="none" stroke="#263754" strokeWidth="7" />
        <circle cx="120" cy="120" r={102 - index * 13} fill="none" stroke={COLORS[index % COLORS.length]} strokeWidth="7" pathLength="100" strokeDasharray={`${item.value} ${100-item.value}`} transform="rotate(-90 120 120)" />
      </g>)}
      <text x="120" y="116" textAnchor="middle" fill="#f2f6ff" fontSize="16">Composição</text>
      <text x="120" y="137" textAnchor="middle" fill="#adbbd5" fontSize="11">percentuais da API</text>
    </svg>
    <figcaption><ul>{validData.map((item,index) => <li key={item.name}><i style={{background:COLORS[index % COLORS.length]}} aria-hidden="true" /><span>{item.name}</span><strong>{formatPercentBR(item.value)}</strong></li>)}</ul><p className="helper">Cada órbita: 0–100%. {validData.length > 6 ? "Seis ativos desenhados; todos os valores estão na legenda." : "Sem redistribuir percentuais ausentes."}</p></figcaption>
  </figure>;
}
