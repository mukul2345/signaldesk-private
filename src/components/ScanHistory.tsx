import { useState } from "react";
import { dashboardApi } from "../api/client";
import { useScanHistory } from "../app/useScanHistory";
import { useSchedulerStatus } from "../app/useSchedulerStatus";
import { formatMoney } from "../config/dashboard";
import { Icon } from "./Icons";

export function ScanHistory() {
  const { data, status, message, refresh } = useScanHistory();
  const { data: scheduler, refresh: refreshScheduler } = useSchedulerStatus();
  const [archiving, setArchiving] = useState(false);
  const [outcome, setOutcome] = useState<string>();

  const archive = async () => {
    setArchiving(true);
    try {
      const run = await dashboardApi.archiveCurrentScan();
      setOutcome(`${run.candidates.length} eligible setups archived · retry-safe slot ${run.slotKey}`);
      await refresh();
      await refreshScheduler();
    } catch (error) {
      setOutcome(error instanceof Error ? error.message : "Snapshot could not be archived");
    } finally {
      setArchiving(false);
    }
  };

  if (status === "loading") return <section className="history-page empty-panel">Loading scan history…</section>;
  if (!data) return <section className="history-page empty-panel"><b>Scan history unavailable</b><p>{message}</p></section>;

  return <section className="history-page">
    <div className="history-hero">
      <div><span className="eyebrow">DURABLE RESEARCH RECORD</span><h1>Completed scan history</h1><p>Only fully evaluated snapshots can enter this {data.retentionDays}-day evidence trail.</p></div>
      <button className="primary-action" disabled={archiving} onClick={archive}><Icon name="scan"/>{archiving ? "Archiving…" : "Archive current scan"}</button>
    </div>
    <div className="history-policy">
      <div><span>Configured slot</span><b>{data.scheduleSlots.join(", ")} · {data.timezone}</b></div>
      <div><span>Per-snapshot maximum</span><b>Top {data.archiveLimit} eligible setups</b></div>
      <div><span>Publication rule</span><b>Complete coverage only</b></div>
    </div>
    {scheduler && <div className="scheduler-panel">
      <div className="scheduler-state"><span className={scheduler.enabled ? "armed" : "off"}/><div><small>AUTOMATIC SCANNER</small><b>{scheduler.enabled ? "Armed for configured sessions" : "Disabled"}</b></div></div>
      <div><small>NEXT AUTOMATIC RUN</small><b>{scheduler.nextRunAt ? new Date(scheduler.nextRunAt).toLocaleString("en-IN", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: scheduler.timezone }) : "No run scheduled"}</b></div>
      <div><small>ACTIVE DAYS</small><b>{scheduler.activeWeekdays.map(day => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day]).join(" · ")}</b></div>
      <div><small>LAST JOB</small><b>{scheduler.jobs[0] ? `${scheduler.jobs[0].status} · attempt ${scheduler.jobs[0].attempts}` : "Awaiting first slot"}</b></div>
    </div>}
    {outcome && <div className="scan-outcome"><span/><p>{outcome}</p></div>}
    {data.runs.length === 0 ? <div className="empty-panel"><b>No completed snapshots yet</b><p>Archive the current illustrative scan to create the first retry-safe record.</p></div> :
      <div className="history-list">{data.runs.map(run => <article className="history-run" key={run.id}>
        <header><div><span className="state ready"><i/>COMPLETE</span><h2>{new Date(run.as_of).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })} research snapshot</h2><p>{run.strategyVersion} · {run.universeVersion}</p></div><div className="coverage-ring"><b>{Math.round(run.coverageRatio * 100)}%</b><span>coverage</span></div></header>
        <div className="run-meta"><span>{run.evaluatedCount} evaluated</span><span>{run.excludedCount} excluded</span><span>{run.candidates.length} archived</span><span>{run.source.replaceAll("_", " ")}</span></div>
        <div className="archived-grid">{run.candidates.map(candidate => <div className="archived-card" key={candidate.id}>
          <div><span>#{candidate.rank}</span><b>{candidate.symbol}</b><em className={candidate.state.toLowerCase()}>{candidate.state}</em></div>
          <p>{candidate.setup}</p><footer><span>{formatMoney(candidate.price)}</span><b>{candidate.score}<small>/100</small></b></footer>
        </div>)}</div>
      </article>)}</div>}
  </section>;
}
