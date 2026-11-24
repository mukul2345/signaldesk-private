import { usePaperAccount } from "../app/usePaperAccount";
import { formatDateTime, formatMoney } from "../config/dashboard";
import { Icon } from "./Icons";

export function Journal() {
  const { account, loading, error } = usePaperAccount(true);
  return <section className="journal-view">
    <div className="page-heading"><div><span className="eyebrow">IMMUTABLE HISTORY</span><h1>Paper journal</h1><p>Orders and fills remain separate so planned levels are never rewritten as actual execution.</p></div></div>
    {error && <div className="replay-result error"><b>{error}</b></div>}
    <div className="journal-grid">
      <section className="journal-panel"><div className="section-title"><div><span className="eyebrow">ORDERS</span><h2>Plan lifecycle</h2><p>{loading ? "Loading…" : `${account.orders.length} orders`}</p></div></div><div className="timeline">{account.orders.map(order => <article key={order.id}><span className="timeline-mark"/><div><b>{order.symbol} · {order.status.replaceAll("_", " ")}</b><p>{order.quantity} planned · {order.filled_quantity} filled · {formatMoney(order.fees)} fees</p><small>{formatDateTime(order.updated_at ?? order.created_at)} · {order.id.slice(0, 8)}</small></div></article>)}</div></section>
      <section className="journal-panel"><div className="section-title"><div><span className="eyebrow">FILLS</span><h2>Execution evidence</h2><p>{account.fills.length + account.exitFills.length} recorded fills</p></div></div><div className="timeline fills">{account.exitFills.map(fill => <article key={fill.id}><span className="timeline-mark"><Icon name="shield"/></span><div><b>{fill.symbol} · {fill.reason.replaceAll("_", " ")} · {fill.quantity} shares</b><p>Observed {formatMoney(fill.observed_price)} → exited {formatMoney(fill.fill_price)}</p><small>{formatDateTime(fill.filled_at)} · fee {formatMoney(fill.fee)}</small></div></article>)}{account.fills.map(fill => <article key={fill.id}><span className="timeline-mark"><Icon name="shield"/></span><div><b>{fill.symbol} · ENTRY · {fill.quantity} shares</b><p>Observed {formatMoney(fill.observed_price)} → filled {formatMoney(fill.fill_price)}</p><small>{formatDateTime(fill.filled_at)} · fee {formatMoney(fill.fee)}</small></div></article>)}{!account.fills.length && !account.exitFills.length && <div className="empty-journal"><Icon name="book"/><b>No fills recorded</b><p>Advance an active paper replay to create fill evidence.</p></div>}</div></section>
    </div>
  </section>;
}
