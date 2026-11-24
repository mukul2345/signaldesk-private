import { useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import { formatDateTime, formatMoney } from "../config/dashboard";
import type { DailyBriefPayload, PerformanceValidationPayload } from "../domain/types";
import { Icon } from "./Icons";

export function DailyBriefPanel({ onClose }: { onClose: () => void }) {
  const [brief, setBrief] = useState<DailyBriefPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<PerformanceValidationPayload | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [nextBrief, nextValidation] = await Promise.all([
        dashboardApi.dailyBrief(),
        dashboardApi.performanceValidation()
      ]);
      setBrief(nextBrief);
      setValidation(nextValidation);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Daily brief is unavailable"); }
  };

  useEffect(() => { void load(); }, []);

  const run = async () => {
    setBusy(true); setError(null);
    try { setBrief(await dashboardApi.runDailyAnalysis()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Daily analysis failed"); }
    finally { setBusy(false); }
  };

  return <aside className="brief-drawer" aria-label="Daily analysis alerts">
    <header><div><span className="eyebrow">DAILY MVP BRIEF</span><h2>Signals &amp; portfolio</h2><p>{brief ? formatDateTime(brief.generatedAt) : "Loading latest completed analysis…"}</p></div><button className="icon-button" aria-label="Close daily brief" onClick={onClose}><Icon name="close"/></button></header>
    {error && <div className="brief-error"><b>Analysis notice</b><p>{error}</p></div>}
    {brief && <>
      <div className={`portfolio-health ${brief.portfolio.health.toLowerCase()}`}><span>PORTFOLIO</span><b>{brief.portfolio.health.replaceAll("_", " ")}</b><p>{brief.portfolio.openPositions} open · {formatMoney(brief.portfolio.unrealizedPnl)} unrealized · {formatMoney(brief.portfolio.reservedRisk)} risk</p></div>
      <section className="brief-section"><div className="brief-title"><div><span>LATEST COMPLETE SCAN</span><h3>Top {brief.topSetups.length || 0} actionable setups</h3></div>{brief.scan && <small>{formatDateTime(brief.scan.as_of)}</small>}</div>
        {brief.topSetups.length ? <div className="brief-setups">{brief.topSetups.map(setup => <article key={setup.id}><div><span className={`state ${setup.state.toLowerCase()}`}><i/>{setup.state}</span><b>{setup.symbol}</b><small>{setup.setup}</small></div><dl><div><dt>Entry</dt><dd>{formatMoney(setup.entry)}</dd></div><div><dt>SL</dt><dd className="negative">{formatMoney(setup.stop)}</dd></div><div><dt>TP1</dt><dd>{formatMoney(setup.targetOne)}</dd></div><div><dt>TP2</dt><dd>{formatMoney(setup.targetTwo)}</dd></div></dl></article>)}</div> : <div className="brief-empty"><b>No actionable setup today</b><p>The engine will not manufacture a trade when READY/WATCH criteria are not met.</p></div>}
      </section>
      <section className="brief-section"><div className="brief-title"><div><span>DAILY PORTFOLIO CHECK</span><h3>Capital and protection</h3></div></div><div className="brief-metrics"><div><span>Market value</span><b>{formatMoney(brief.portfolio.marketValue)}</b></div><div><span>Realized P&amp;L</span><b>{formatMoney(brief.portfolio.realizedPnl)}</b></div><div><span>Concentration</span><b>{brief.portfolio.largestPositionPercent.toFixed(1)}%</b></div></div><ul>{brief.portfolio.observations.map(item => <li key={item}>{item}</li>)}</ul></section>
      {validation && <section className="brief-section validation-section"><div className="brief-title"><div><span>FORWARD PAPER EVIDENCE</span><h3>{validation.status.replaceAll("_", " ")}</h3></div><small>{validation.closedTrades}/{validation.minimumRequiredTrades} trades</small></div><div className="brief-metrics"><div><span>Win rate</span><b>{validation.winRatePercent.toFixed(1)}%</b></div><div><span>30-day return</span><b>{validation.last30DayReturnPercent.toFixed(2)}%</b></div><div><span>Max drawdown</span><b>{validation.maximumDrawdownPercent.toFixed(2)}%</b></div></div><div className="validation-track" aria-label={`${Math.round(Math.min(validation.closedTrades / validation.minimumRequiredTrades * 100, 100))}% evidence sample complete`}><span style={{width:`${Math.min(validation.closedTrades / validation.minimumRequiredTrades * 100, 100)}%`}}/></div><ul>{validation.warnings.map(item => <li key={item}>{item}</li>)}</ul></section>}
    </>}
    <footer><button className="primary-button" disabled={busy} onClick={() => void run()}>{busy ? "Running analysis…" : "Run daily analysis now"}</button><small>Completed NSE daily candles · paper research only</small></footer>
  </aside>;
}
