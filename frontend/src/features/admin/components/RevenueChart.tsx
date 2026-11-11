// frontend/src/features/admin/components/RevenueChart.tsx
/**
 * SVG line chart для revenue по дням. Без библиотек (ARCHITECTURE.md:
 * zero new runtime dependencies). Tooltip — нативный <title> в <circle>.
 */
import type { DailySeriesItem } from "../../../types/admin";

interface Props {
  items: DailySeriesItem[];
}

const W = 800;
const H = 240;
const PAD_LEFT = 60;
const PAD_RIGHT = 20;
const PAD_TOP = 20;
const PAD_BOTTOM = 40;
const INNER_W = W - PAD_LEFT - PAD_RIGHT;
const INNER_H = H - PAD_TOP - PAD_BOTTOM;

function shortMoney(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(0);
}

function shortDate(isoDate: string): string {
  // isoDate = YYYY-MM-DD → MM-DD
  return isoDate.slice(5);
}

export function RevenueChart({ items }: Props) {
  if (items.length === 0) {
    return <p style={{ color: "#6b6375", padding: "1rem 0" }}>Нет данных</p>;
  }

  const values = items.map((it) => Number(it.revenue_gross));
  const maxVal = Math.max(1, ...values);
  const n = items.length;
  const stepX = n > 1 ? INNER_W / (n - 1) : 0;

  const points = items.map((it, i) => {
    const value = Number(it.revenue_gross);
    const x = PAD_LEFT + stepX * i;
    const y = PAD_TOP + INNER_H - (value / maxVal) * INNER_H;
    return { x, y, value, date: it.date, orders: it.orders_count };
  });

  const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  // Y-ticks: 0, 25%, 50%, 75%, 100% от maxVal
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((frac) => ({
    y: PAD_TOP + INNER_H - frac * INNER_H,
    label: shortMoney(maxVal * frac),
  }));

  // X-labels: все, если n<=7; иначе каждый ceil(n/7)-й
  const labelEvery = n <= 7 ? 1 : Math.ceil(n / 7);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ display: "block", maxWidth: "100%" }}
      role="img"
      aria-label="График выручки по дням"
    >
      {/* Y-grid + labels */}
      {yTicks.map((t, i) => (
        <g key={`y-${i}`}>
          <line
            x1={PAD_LEFT}
            x2={W - PAD_RIGHT}
            y1={t.y}
            y2={t.y}
            stroke="#e5e4e7"
            strokeDasharray={i === 0 ? "0" : "3 3"}
          />
          <text
            x={PAD_LEFT - 8}
            y={t.y + 4}
            textAnchor="end"
            fontSize="11"
            fill="#6b6375"
          >
            {t.label}
          </text>
        </g>
      ))}

      {/* X-labels */}
      {points.map((p, i) =>
        i % labelEvery === 0 ? (
          <text
            key={`x-${i}`}
            x={p.x}
            y={H - PAD_BOTTOM + 18}
            textAnchor="middle"
            fontSize="11"
            fill="#6b6375"
          >
            {shortDate(p.date)}
          </text>
        ) : null
      )}

      {/* Area fill (subtle) */}
      <polygon
        points={`${PAD_LEFT},${PAD_TOP + INNER_H} ${polylinePoints} ${
          PAD_LEFT + INNER_W
        },${PAD_TOP + INNER_H}`}
        fill="rgba(170, 59, 255, 0.12)"
      />

      {/* Line */}
      <polyline
        points={polylinePoints}
        fill="none"
        stroke="#aa3bff"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Points with native tooltip */}
      {points.map((p, i) => (
        <circle
          key={`p-${i}`}
          cx={p.x}
          cy={p.y}
          r={3}
          fill="#aa3bff"
        >
          <title>
            {p.date}: {p.value.toFixed(2)} ₽, {p.orders} заказ(ов)
          </title>
        </circle>
      ))}
    </svg>
  );
}