import { formatNumber } from "../config/dashboard";
import type { MarketIndex } from "../domain/types";

const sparkline = (points: readonly number[]) => {
  const width = 120, height = 42;
  const min = Math.min(...points), max = Math.max(...points);
  return points.map((p, i) => `${(i / (points.length - 1)) * width},${height - ((p - min) / Math.max(max - min, 1)) * height}`).join(" ");
};

export function MarketPulse({ indices }: { indices: readonly MarketIndex[] }) {
  return <section className="market-grid" aria-label="Market sentiment">
    {indices.map(index => <article className="index-card" key={index.id}>
      <div className="index-head"><span>{index.name}</span><b className={index.direction}>{index.status}</b></div>
      <div className="index-body">
        <div><strong>{formatNumber(index.value)}</strong><p className={index.direction}>{index.changePercent > 0 ? "+" : ""}{index.changePercent.toFixed(2)}% <small>1D</small></p></div>
        <svg viewBox="0 0 120 42" role="img" aria-label={`${index.name} trend`}><defs><linearGradient id={`g-${index.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={index.direction === "down" ? "#ff8b73" : "#64efaf"} stopOpacity=".32"/><stop offset="1" stopColor="#07110e" stopOpacity="0"/></linearGradient></defs><polygon points={`0,42 ${sparkline(index.points)} 120,42`} fill={`url(#g-${index.id})`}/><polyline points={sparkline(index.points)} fill="none" stroke={index.direction === "down" ? "#ff8b73" : "#64efaf"} strokeWidth="2"/></svg>
      </div>
    </article>)}
  </section>;
}
