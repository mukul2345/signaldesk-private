import { formatMoney } from "../config/dashboard";
import type { Candidate, SignalState } from "../domain/types";
import { Icon } from "./Icons";

const stateClass: Record<SignalState, string> = { READY: "ready", WATCH: "watch", AVOID: "avoid" };

interface Props { candidates: readonly Candidate[]; selectedId: string; onSelect: (candidate: Candidate) => void; onViewHistory: () => void; }

export function ScannerTable({ candidates, selectedId, onSelect, onViewHistory }: Props) {
  return <section className="scanner-panel">
    <div className="section-title"><div><span className="eyebrow">RANKED OPPORTUNITIES</span><h2>Today’s signal board</h2><p>Evidence-weighted setups aligned with current market conditions.</p></div><button className="text-button" onClick={onViewHistory}>Scan history <Icon name="arrow"/></button></div>
    <div className="table-wrap"><table><thead><tr><th>Rank / Symbol</th><th>Signal</th><th>Setup</th><th>Price</th><th>Flow</th><th>Score</th><th aria-label="Open plan"/></tr></thead>
      <tbody>{candidates.map(item => <tr className={selectedId === item.id ? "selected" : ""} key={item.id} onClick={() => onSelect(item)} tabIndex={0} onKeyDown={event => event.key === "Enter" && onSelect(item)}>
        <td><div className="symbol-cell"><span>{String(item.rank).padStart(2, "0")}</span><div><b>{item.symbol}</b><small>{item.sector}</small></div></div></td>
        <td><span className={`state ${stateClass[item.state]}`}><i/>{item.state}</span></td>
        <td><b className="setup">{item.setup}</b><small>{item.volumeRatio.toFixed(1)}× avg volume</small></td>
        <td><b>{formatMoney(item.price)}</b><small className={item.changePercent >= 0 ? "positive" : "negative"}>{item.changePercent > 0 ? "+" : ""}{item.changePercent.toFixed(2)}%</small></td>
        <td><div className="flow"><span style={{ width: `${Math.min(item.volumeRatio / 2.5 * 100, 100)}%` }}/></div><small>{item.volumeRatio >= 1.5 ? "Strong" : item.volumeRatio >= 1 ? "Moderate" : "Weak"}</small></td>
        <td><div className="score"><span style={{ "--score": `${item.score * 3.6}deg` } as React.CSSProperties}>{item.score}</span><small>/ 100</small></div></td>
        <td><button className="row-arrow" aria-label={`Open ${item.symbol} plan`}><Icon name="chevron"/></button></td>
      </tr>)}</tbody></table></div>
  </section>;
}
