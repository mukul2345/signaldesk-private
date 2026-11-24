import { formatMoney } from "../config/dashboard";
import type { Candidate } from "../domain/types";
import { Icon } from "./Icons";

interface Props {
  candidate: Candidate;
  onClose: () => void;
  onCreatePaperOrder: () => void;
  orderState: { status: "idle" | "submitting" | "success" | "error"; message?: string; label?: string };
}

export function TradePlan({ candidate, onClose, onCreatePaperOrder, orderState }: Props) {
  const risk = candidate.entry - candidate.stop;
  return <aside className="trade-plan" aria-label={`${candidate.symbol} trade plan`}>
    <div className="plan-top"><div><span className="state ready"><i/>{candidate.state}</span><h2>{candidate.symbol}</h2><p>{candidate.company}</p></div><button className="icon-button" onClick={onClose} aria-label="Close trade plan"><Icon name="close"/></button></div>
    <div className="price-row"><div><span>Illustrative price</span><strong>{formatMoney(candidate.price)}</strong></div><b className={candidate.changePercent >= 0 ? "positive" : "negative"}>{candidate.changePercent > 0 ? "+" : ""}{candidate.changePercent.toFixed(2)}%</b></div>
    <div className="plan-chart"><div className="chart-grid"/><svg viewBox="0 0 360 124" preserveAspectRatio="none"><path d="M0 103 C30 98 45 91 70 94 S110 82 134 87 S173 64 196 68 S220 46 244 51 S280 30 305 37 S334 20 360 13" fill="none" stroke="#6bf0b3" strokeWidth="2"/><path d="M0 103 C30 98 45 91 70 94 S110 82 134 87 S173 64 196 68 S220 46 244 51 S280 30 305 37 S334 20 360 13 L360 124 L0 124Z" fill="url(#area)"/><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#64efaf" stopOpacity=".2"/><stop offset="1" stopColor="#64efaf" stopOpacity="0"/></linearGradient></defs></svg><span>20 sessions · illustrative</span></div>
    <div className="levels"><div><span>ENTRY ABOVE</span><b>{formatMoney(candidate.entry)}</b></div><div className="stop"><span>INITIAL STOP</span><b>{formatMoney(candidate.stop)}</b></div><div><span>TARGET 1</span><b>{formatMoney(candidate.targetOne)}</b></div><div><span>TARGET 2</span><b>{formatMoney(candidate.targetTwo)}</b></div></div>
    <div className="risk-summary"><div><span>Risk / share</span><b>{formatMoney(risk)}</b></div><div><span>Reward : risk</span><b>{((candidate.targetTwo - candidate.entry) / risk).toFixed(1)}R</b></div><div><span>Observed frequency</span><b>{candidate.probability ? `${candidate.probability}%` : "Hidden"}</b></div></div>
    <div className="evidence"><h3><Icon name="spark"/> Why it ranks</h3>{candidate.reasons.map(reason => <p key={reason}><i/> {reason}</p>)}{candidate.contradictions.map(reason => <p className="warning" key={reason}><i/> {reason}</p>)}</div>
    <div className="plan-actions">
      <button className="primary-button" disabled={candidate.state !== "READY" || orderState.status === "submitting" || orderState.status === "success"} onClick={onCreatePaperOrder}>{candidate.state !== "READY" ? "Await READY signal" : orderState.status === "submitting" ? "Creating pending order…" : orderState.status === "success" ? orderState.label ?? "Paper trade active" : "Create paper order"} <Icon name="arrow"/></button>
      {orderState.message && <div className={`order-notice ${orderState.status}`}>{orderState.message}</div>}
      <button className="secondary-button">Add to watchlist</button><small><Icon name="shield"/> Simulation only · no broker order will be sent</small>
    </div>
  </aside>;
}
