import { useState } from "react";
import { dashboardApi } from "../api/client";
import { usePaperAccount } from "../app/usePaperAccount";
import { formatDateTime, formatMoney } from "../config/dashboard";
import type { ExitReplayResult, PaperOrder, PaperPosition, ReplayResult } from "../domain/types";
import { Icon } from "./Icons";

const activeStatuses = new Set<PaperOrder["status"]>(["PENDING_SIMULATION", "PARTIALLY_FILLED"]);
const statusLabel: Record<PaperOrder["status"], string> = {
  PENDING_SIMULATION: "Pending trigger",
  PARTIALLY_FILLED: "Partially filled",
  FILLED: "Entry filled",
  CANCELLED: "Cancelled"
};

export function PaperAccount({ onLedgerChange }: { onLedgerChange: () => void }) {
  const { account, loading, error, refresh } = usePaperAccount(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [result, setResult] = useState<ReplayResult | null>(null);
  const [exitResult, setExitResult] = useState<ExitReplayResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const afterAction = async () => {
    await refresh();
    onLedgerChange();
  };

  const advance = async (order: PaperOrder) => {
    setBusyId(order.id); setActionError(null);
    try {
      setResult(await dashboardApi.advanceReplay(order.id));
      await afterAction();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Replay could not advance");
    } finally { setBusyId(null); }
  };

  const cancel = async (order: PaperOrder) => {
    setBusyId(order.id); setActionError(null);
    try {
      await dashboardApi.cancelPaperOrder(order.id);
      setResult(null);
      await afterAction();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Order could not be cancelled");
    } finally { setBusyId(null); }
  };

  const advanceExit = async (position: PaperPosition) => {
    setBusyId(position.id); setActionError(null);
    try {
      setExitResult(await dashboardApi.advanceExitReplay(position.id));
      setResult(null);
      await afterAction();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Exit replay could not advance");
    } finally { setBusyId(null); }
  };

  return <section className="account-view">
    <div className="page-heading"><div><span className="eyebrow">PAPER EXECUTION</span><h1>Paper account</h1><p>Replay observations are processed after order creation. Nothing here reaches a broker.</p></div><span className="demo-badge">DETERMINISTIC REPLAY</span></div>
    <div className="account-metrics">
      <article><span>Available cash</span><b>{formatMoney(account.availableCash)}</b><small>after fills and reservations</small></article>
      <article><span>Reserved cash</span><b>{formatMoney(account.reservedCash)}</b><small>unfilled entry quantities</small></article>
      <article><span>Deployed value</span><b>{formatMoney(account.deployedValue)}</b><small>fills plus estimated fees</small></article>
      <article><span>Reserved risk</span><b>{formatMoney(account.reservedRisk)}</b><small>initial stop basis</small></article>
    </div>
    {result && <div className={`replay-result ${result.outcome.toLowerCase()}`}><Icon name="spark"/><div><b>{result.message}</b><p>{result.observation.symbol} observed at {formatMoney(result.observation.price)} · {formatDateTime(result.observation.observed_at)}{result.fill ? ` · ${result.fill.quantity} shares filled at ${formatMoney(result.fill.fill_price)}` : ""}</p></div></div>}
    {exitResult && <div className={`replay-result ${exitResult.outcome.toLowerCase()}`}><Icon name="shield"/><div><b>{exitResult.message}</b><p>{exitResult.observation.symbol} observed at {formatMoney(exitResult.observation.price)} · {formatDateTime(exitResult.observation.observed_at)}{exitResult.fill ? ` · ${exitResult.fill.quantity} shares exited at ${formatMoney(exitResult.fill.fill_price)}` : exitResult.position.current_stop !== exitResult.previous_stop ? ` · stop ${formatMoney(exitResult.previous_stop)} → ${formatMoney(exitResult.position.current_stop)}` : ""}</p></div></div>}
    {(error || actionError) && <div className="replay-result error"><div><b>Paper engine notice</b><p>{error ?? actionError}</p></div></div>}
    <div className="positions-panel">
      <div className="section-title"><div><span className="eyebrow">POSITIONS</span><h2>Managed exits</h2><p>TP1, TP2 and protective stops use recorded replay observations.</p></div></div>
      <div className="position-list">{account.positions.map(position => <article className="position-card" key={position.id}>
        <div className="position-name"><span className={`order-status ${position.status.toLowerCase()}`}>{position.status}</span><h3>{position.symbol}</h3><p>{position.trailing_active ? "Trailing protection active" : "Initial protection active"}</p></div>
        <div className="position-stat"><span>Open / closed</span><b>{position.quantity_open} / {position.quantity_closed}</b><small>shares</small></div>
        <div className="position-stat"><span>Average entry</span><b>{formatMoney(position.average_entry_price)}</b><small>highest {formatMoney(position.highest_price)}</small></div>
        <div className="position-stat stop"><span>Current stop</span><b>{formatMoney(position.current_stop)}</b><small>{position.trailing_active ? "confirmed paper trail" : "initial stop"}</small></div>
        <div className="position-stat"><span>TP1 / TP2</span><b>{formatMoney(position.target_one)} / {formatMoney(position.target_two)}</b><small>{position.tp1_filled_quantity} TP1 shares exited</small></div>
        <div className="position-stat"><span>Realized P&amp;L</span><b className={position.realized_pnl >= 0 ? "positive" : "negative"}>{formatMoney(position.realized_pnl)}</b><small>{formatMoney(position.exit_fees)} exit fees</small></div>
        <div className="position-action">{position.status === "OPEN" ? <button className="primary-button" disabled={busyId === position.id} onClick={() => advanceExit(position)}>{busyId === position.id ? "Processing…" : "Advance exit replay"}<Icon name="arrow"/></button> : <span>Position lifecycle complete</span>}</div>
      </article>)}</div>
    </div>
    <div className="orders-panel">
      <div className="section-title"><div><span className="eyebrow">ORDER LEDGER</span><h2>Simulated entries</h2><p>{loading ? "Refreshing ledger…" : `${account.orders.length} recorded order${account.orders.length === 1 ? "" : "s"}`}</p></div></div>
      <div className="order-list">{account.orders.map(order => <article className="order-card" key={order.id}>
        <div className="order-identity"><span className={`order-status ${order.status.toLowerCase()}`}>{statusLabel[order.status]}</span><h3>{order.symbol}</h3><p>{formatDateTime(order.created_at)}</p></div>
        <div className="order-stat"><span>Quantity</span><b>{order.filled_quantity} / {order.quantity}</b><small>filled / planned</small></div>
        <div className="order-stat"><span>Entry</span><b>{formatMoney(order.entry_price)}</b><small>{order.average_fill_price ? `avg ${formatMoney(order.average_fill_price)}` : "not filled"}</small></div>
        <div className="order-stat"><span>Initial stop</span><b>{formatMoney(order.stop_price)}</b><small>{formatMoney(order.planned_risk)} planned risk</small></div>
        <div className="order-stat"><span>Fees</span><b>{formatMoney(order.fees)}</b><small>estimated</small></div>
        <div className="order-actions">{activeStatuses.has(order.status) ? <><button className="primary-button" disabled={busyId === order.id} onClick={() => advance(order)}>{busyId === order.id ? "Processing…" : "Advance replay"}<Icon name="arrow"/></button><button className="secondary-button" disabled={busyId === order.id} onClick={() => cancel(order)}>Cancel remaining</button></> : <span>Lifecycle complete</span>}</div>
      </article>)}</div>
    </div>
  </section>;
}
