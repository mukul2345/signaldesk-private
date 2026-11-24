import { useMemo, useState } from "react";
import { dashboardApi } from "../api/client";
import { dashboardConfig, formatDateTime, formatMoney } from "../config/dashboard";
import type { Candidate } from "../domain/types";
import { Icon } from "../components/Icons";
import { MarketPulse } from "../components/MarketPulse";
import { PaperAccount } from "../components/PaperAccount";
import { Journal } from "../components/Journal";
import { ScannerTable } from "../components/ScannerTable";
import { ScanHistory } from "../components/ScanHistory";
import { SettingsHealth } from "../components/SettingsHealth";
import { Sidebar } from "../components/Sidebar";
import { TradePlan } from "../components/TradePlan";
import { DailyBriefPanel } from "../components/DailyBriefPanel";
import { useDashboard } from "./useDashboard";

const filters = ["All setups", "Ready", "Watch", "Avoid"] as const;

export function App() {
  const { data, connection, refresh } = useDashboard();
  const [active, setActive] = useState("Overview");
  const [filter, setFilter] = useState<(typeof filters)[number]>("All setups");
  const [selectedId, setSelectedId] = useState<string>("cdsl");
  const [orderState, setOrderState] = useState<{ status: "idle" | "submitting" | "success" | "error"; message?: string; label?: string }>({ status: "idle" });
  const [briefOpen, setBriefOpen] = useState(false);
  const selected = data.candidates.find(item => item.id === selectedId) ?? null;
  const existingOrder = data.pendingOrders.find(order => order.candidate_id === selectedId);
  const readyCount = data.candidates.filter(item => item.state === "READY").length;
  const filtered = useMemo(() => filter === "All setups" ? data.candidates : data.candidates.filter(item => item.state === filter.toUpperCase()), [data.candidates, filter]);
  const officialNse = data.source === "official_nse_bhavcopy_mcp";
  const resolvedCoverage = data.scanCoverage.evaluatedCount + data.scanCoverage.excludedCount;
  const coveragePercent = Math.round((resolvedCoverage / data.scanCoverage.eligibleCount) * 100);

  const selectCandidate = (candidate: Candidate) => {
    setSelectedId(candidate.id);
    setOrderState({ status: "idle" });
  };

  const createPaperOrder = async () => {
    if (!selected) return;
    setOrderState({ status: "submitting" });
    try {
      const order = await dashboardApi.createPaperOrder(selected.id, crypto.randomUUID());
      setOrderState({ status: "success", label: "Paper order pending", message: `${order.quantity} ${order.symbol} shares queued for paper simulation · ${formatMoney(order.planned_risk)} planned risk` });
      refresh();
    } catch (error) {
      setOrderState({ status: "error", message: error instanceof Error ? error.message : "Paper order could not be created" });
    }
  };

  return <div className="app-shell">
    <Sidebar active={active} candidateCount={data.candidates.length} onNavigate={setActive}/>
    <main>
      <header className="topbar">
          <div><span className={`session-dot ${connection}`}/><b>{data.market_status}</b><span className="divider"/><span>{connection === "connected" ? "Local API connected" : connection === "loading" ? "Connecting to local API…" : "Frontend demo fallback"}</span></div>
        <div className="top-actions"><span className="mode-badge">{dashboardConfig.mode}</span><span className="demo-badge">{officialNse ? "NSE EOD" : dashboardConfig.dataLabel}</span><button className="icon-button" aria-label="Search"><Icon name="search"/></button><button className="icon-button notification" aria-label="Daily analysis alerts" aria-expanded={briefOpen} onClick={() => setBriefOpen(value => !value)}><Icon name="bell"/><i/></button></div>
      </header>

      <div className="content">
        {active === "Paper account" ? <PaperAccount onLedgerChange={() => refresh()}/> : active === "Journal" ? <Journal/> : active === "Scan history" ? <ScanHistory/> : active === "Settings & health" ? <SettingsHealth/> : <>
        <section className="hero">
          <div><span className="eyebrow">PRIVATE RESEARCH TERMINAL</span><h1>Good evening, Mukul.</h1><p>{officialNse ? `Official NSE session ${formatDateTime(data.as_of)}.` : "Illustrative research snapshot."} <b>{readyCount} setups</b> meet the deterministic readiness criteria.</p></div>
          <div className="next-scan"><Icon name="clock"/><div><span>NEXT RESEARCH RUN</span><b>{data.next_scan}</b></div><button aria-label="View schedule"><Icon name="chevron"/></button></div>
        </section>

        <MarketPulse indices={data.indices}/>

        <section className="capital-strip">
          <div><span>Paper capital</span><b>{formatMoney(data.policy.capitalCeiling)}</b></div><div><span>Available cash</span><b>{formatMoney(data.account.availableCash)}</b></div><div><span>Deployed</span><b>{formatMoney(data.account.deployed)}</b></div><div><span>Reserved risk</span><b>{formatMoney(data.account.openRisk)}</b></div><div><span>Proposed risk / trade</span><b>{formatMoney(data.policy.riskPerTrade)}</b><small>Paper hypothesis</small></div>
        </section>

        <div className="filter-row"><div>{filters.map(item => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}{item === "Ready" && <span>{readyCount}</span>}</button>)}</div><p><span/> {officialNse ? "Official NSE EOD scan" : "Demo scan"} · {coveragePercent}% coverage ({resolvedCoverage}/{data.scanCoverage.eligibleCount}) · {data.policy.displayLimit} result limit</p></div>

        <div className={`workspace ${selected ? "with-plan" : ""}`}>
          <ScannerTable candidates={filtered} selectedId={selected?.id ?? ""} onSelect={selectCandidate} onViewHistory={() => setActive("Scan history")}/>
          {selected && (
            <TradePlan candidate={selected} onClose={() => setSelectedId("")} onCreatePaperOrder={createPaperOrder} orderState={existingOrder && orderState.status === "idle" ? { status: "success", label: existingOrder.status === "FILLED" ? "Paper position open" : existingOrder.status === "PARTIALLY_FILLED" ? "Paper entry partial" : "Paper order pending", message: existingOrder.status === "FILLED" ? `${existingOrder.filled_quantity} ${existingOrder.symbol} shares are held in the paper account · ${formatMoney(existingOrder.planned_risk)} initial risk` : `${existingOrder.filled_quantity} / ${existingOrder.quantity} ${existingOrder.symbol} shares filled · ${formatMoney(existingOrder.planned_risk)} reserved risk` } : orderState}/>
          )}
        </div>
        </>}
        <footer><span>SignalDesk research workspace</span><p>{officialNse ? "Official NSE EOD data · Informational, non-commercial research only" : "Illustrative information"} · No investment guarantee</p></footer>
      </div>
      {briefOpen && <DailyBriefPanel onClose={() => setBriefOpen(false)}/>}
    </main>
  </div>;
}
