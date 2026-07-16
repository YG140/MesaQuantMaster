import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatPercentBR } from "../../utils/formatters";

type AllocationItem = {
  name: string;
  value: number;
};

const COLORS = ["#2dd4bf", "#60a5fa", "#f59e0b", "#a78bfa", "#34d399", "#f87171"];

export function AllocationChart({ data }: { data: AllocationItem[] }) {
  const validData = data.filter((item) => item.name.trim() && Number.isFinite(item.value) && item.value > 0);
  if (!validData.length) {
    return null;
  }
  return (
    <div className="chart-box" aria-label="Grafico de alocacao">
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie data={validData} dataKey="value" nameKey="name" outerRadius={96} label>
            {validData.map((entry, index) => (
              <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => formatPercentBR(typeof value === "number" || typeof value === "string" ? value : null)} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
