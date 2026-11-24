import { useSystemStatus } from "../app/useSystemStatus";
import { formatDateTime, formatMoney } from "../config/dashboard";
import { Icon } from "./Icons";

const label = (value: string) => value.replaceAll("_", " ");

export function SettingsHealth() {
  const { settings, health, scheduler, warmup, warmupBusy, warmupError, advanceWarmup, promotion, promotionBusy, promotionError, refreshPromotion, preparePromotion, status, refresh } = useSystemStatus();
  const warmupPercent = warmup && warmup.totalSymbols > 0 ? Math.round((warmup.warmedSymbols / warmup.totalSymbols) * 100) : 0;

  if (status === "loading") return <section className="settings-page empty-panel">Checking local services…</section>;
  if (!settings || !health) return <section className="settings-page empty-panel"><b>Health check unavailable</b><p>Confirm the local API is running, then try again.</p><button className="secondary-button" onClick={() => refresh()}>Retry</button></section>;

  return <section className="settings-page">
    <div className="settings-hero">
      <div><span className="eyebrow">LOCAL CONTROL PLANE</span><h1>Settings & health</h1><p>Effective non-secret policy and provider readiness from the running API.</p></div>
      <div className={`safety-seal ${health.overall.toLowerCase()}`}><Icon name="shield"/><div><span>EXECUTION STATE</span><b>{health.overall.replaceAll("_", " ")}</b><small>{health.paperSafetyEnforced ? "Live orders blocked" : "Safety check failed"}</small></div></div>
    </div>

    <div className="health-grid">{health.components.map(component => <article key={component.id}>
      <div><span className={`health-light ${component.status.toLowerCase()}`}/><em>{component.status.replaceAll("_", " ")}</em></div>
      <h3>{component.label}</h3><p>{component.detail}</p>
    </article>)}</div>

    <div className="configuration-grid">
      <article className="config-card"><header><div><span className="eyebrow">CAPITAL GUARDRAILS</span><h2>Paper risk policy</h2></div><span className="config-version">v{settings.schemaVersion}</span></header>
        <div className="config-values"><div><span>Capital ceiling</span><b>{formatMoney(settings.capitalCeiling)}</b></div><div><span>Risk per trade</span><b>{formatMoney(settings.risk.riskPerTrade)}</b></div><div><span>Aggregate risk cap</span><b>{formatMoney(settings.risk.maximumAggregateInitialRisk)}</b></div><div><span>Position value cap</span><b>{formatMoney(settings.risk.maximumPositionValue)}</b></div><div><span>Maximum positions</span><b>{settings.risk.maximumOpenPositions}</b></div><div><span>Entry approval</span><b>{settings.execution.requireIndividualEntryApproval ? "Required" : "Not required"}</b></div></div>
      </article>
      <article className="config-card"><header><div><span className="eyebrow">RESEARCH POLICY</span><h2>Scanner configuration</h2></div><span className="config-version">{settings.scanning.automaticEnabled ? "ARMED" : "OFF"}</span></header>
        <div className="config-values"><div><span>Strategy</span><b>{settings.scanning.strategyVersion}</b></div><div><span>Universe</span><b>{settings.scanning.universeVersion}</b></div><div><span>Schedule</span><b>{settings.scanning.scheduleSlots.join(", ")} {settings.scanning.timezone}</b></div><div><span>Exchange calendar</span><b>{scheduler?.calendarName ?? "Unavailable"}</b></div><div><span>Today</span><b>{scheduler ? scheduler.currentDayIsSession ? "Trading session" : "Exchange closed" : "Unavailable"}</b></div><div><span>Required coverage</span><b>{Math.round(settings.scanning.minimumCoverageRatio * 100)}%</b></div><div><span>History</span><b>{settings.scanning.historyRetentionDays} days</b></div><div><span>Archived states</span><b>{settings.scanning.archivableStates.join(" · ")}</b></div></div>
      </article>
      <article className="config-card warmup-card"><header><div><span className="eyebrow">UNIVERSE EXPANSION</span><h2>Nifty 500 history warm-up</h2></div><span className="config-version">{warmup?.readyToActivate ? "READY" : `${warmupPercent}%`}</span></header>
        {warmup?.available ? <div className="warmup-body">
          <div className="warmup-summary"><div><strong>{warmup.warmedSymbols}</strong><span>Warmed</span></div><div><strong>{warmup.remainingSymbols}</strong><span>Remaining</span></div><div><strong>{warmup.activeUniverseSymbols}</strong><span>Currently active</span></div><div><strong>{warmup.failedSymbols.length}</strong><span>Failed</span></div></div>
          <div className="warmup-track" aria-label={`${warmupPercent}% history warm-up complete`}><span style={{ width: `${warmupPercent}%` }}/></div>
          <div className="warmup-meta"><p><b>{warmup.targetVersion}</b><span>{warmup.lastUpdatedAt ? `Updated ${formatDateTime(warmup.lastUpdatedAt)}` : "No batch run yet"}</span></p><button className="primary-button" disabled={warmupBusy || warmup.readyToActivate} onClick={() => void advanceWarmup()}>{warmupBusy ? "Warming batch…" : warmup.readyToActivate ? "Ready to activate" : `Warm next ${Math.min(warmup.batchSize, warmup.remainingSymbols)} symbols`}</button></div>
          {warmupError && <p className="warmup-error">{warmupError}</p>}
          {warmup.failedSymbols.length > 0 && <p className="warmup-error">Retry queue: {warmup.failedSymbols.join(", ")}</p>}
          <small>The candidate universe stays inactive until every symbol has sufficient completed daily history.</small>
        </div> : <div className="warmup-empty"><b>No validated candidate</b><p>Run npm run sync:nse-universe before warming history.</p></div>}
      </article>
      <article className="config-card promotion-card"><header><div><span className="eyebrow">ACTIVATION GATE</span><h2>Universe promotion safeguards</h2></div><span className={`gate-badge ${promotion?.eligibleToPromote ? "pass" : "pending"}`}>{promotion?.eligibleToPromote ? "ELIGIBLE" : "BLOCKED"}</span></header>
        {promotion?.candidateAvailable ? <div className="promotion-body">
          <div className="promotion-versions"><div><span>Runtime active</span><b>{promotion.runtimeActiveVersion}</b></div><div><span>Candidate</span><b>{promotion.candidateVersion}</b></div><div><span>Prepared</span><b>{promotion.preparedVersion ?? "None"}</b></div><div><span>Corporate evidence</span><b>{promotion.corporateActionsCheckedAt ? formatDateTime(promotion.corporateActionsCheckedAt) : "Not refreshed"}</b></div></div>
          <div className="promotion-checks">{promotion.checks.map(check => <div key={check.id}><i className={check.status.toLowerCase()}/><p><b>{check.label}</b><span>{check.detail}</span></p><em className={check.status.toLowerCase()}>{check.status}</em></div>)}</div>
          <div className="adjustment-summary"><div><strong>{promotion.adjustedActionCount}</strong><span>Auto-adjusted histories</span></div><div><strong>{promotion.blockingActionCount}</strong><span>Need authoritative prices</span></div></div>
          {(promotion.blockingActionCount > 0 || promotion.priceAnomalyCount > 0 || promotion.staleHistoryCount > 0) && <div className="gate-warning"><b>Manual review required</b><p>{promotion.blockingActionCount} unresolved corporate actions · {promotion.priceAnomalyCount} price anomalies · {promotion.staleHistoryCount} stale histories</p>{promotion.blockingActionSymbols.length > 0 && <small>{promotion.blockingActionSymbols.join(" · ")}</small>}</div>}
          {promotion.restartRequired && <div className="gate-warning prepared"><b>Activation package prepared</b><p>Restart the API to load {promotion.preparedVersion} as the active universe.</p></div>}
          {promotionError && <p className="warmup-error">{promotionError}</p>}
          <div className="promotion-actions"><button className="secondary-button" disabled={promotionBusy} onClick={() => void refreshPromotion()}>{promotionBusy ? "Refreshing safeguards…" : "Refresh safeguards"}</button><button className="primary-button" disabled={promotionBusy || !promotion.eligibleToPromote || promotion.restartRequired} onClick={() => { if (window.confirm(`Prepare ${promotion.candidateVersion} for activation? The current universe will be backed up and an API restart will be required.`)) void preparePromotion(); }}>Prepare activation</button></div>
          <small>Bonus and face-value ratios are adjusted deterministically. Rights issues, demergers and unparseable events remain fail-closed. No override path is provided.</small>
        </div> : <div className="warmup-empty"><b>No promotion candidate</b><p>Synchronize the official Nifty 500 constituent file first.</p></div>}
      </article>
    </div>

    <article className="strategy-contract"><header><div><span className="eyebrow">DETERMINISTIC ENGINE</span><h2>Daily breakout contract</h2><p>Completed daily bars only · no AI decision · no unfinished-candle leakage</p></div><span>{settings.strategy.version}</span></header>
      <div className="strategy-flow"><div><small>1 · TREND</small><b>SMA {settings.strategy.fastSmaPeriod} above SMA {settings.strategy.slowSmaPeriod}</b></div><i>→</i><div><small>2 · TRIGGER</small><b>{settings.strategy.breakoutLookback}-session prior high + {settings.strategy.entryBufferBps} bps</b></div><i>→</i><div><small>3 · PARTICIPATION</small><b>Volume ≥ {settings.strategy.minimumVolumeRatio.toFixed(1)}× {settings.strategy.volumeAveragePeriod}-session average</b></div><i>→</i><div><small>4 · RISK</small><b>{settings.strategy.initialStopAtrMultiple}× ATR({settings.strategy.atrPeriod}) stop</b></div></div>
      <div className="contract-rules"><span>Warm-up <b>{settings.strategy.warmupBars} bars</b></span><span>Entry extension <b>≤ {settings.strategy.maximumEntryExtensionBps} bps</b></span><span>Targets <b>{settings.strategy.targetOneR}R / {settings.strategy.targetTwoR}R</b></span><span>Time exit <b>{settings.strategy.maximumHoldingSessions} sessions</b></span></div>
    </article>

    <article className="provider-strip"><div><span>Research</span><b>{label(settings.providers.research)}</b></div><div><span>Market data</span><b>{label(settings.providers.marketData)}</b></div><div><span>Execution</span><b>{label(settings.providers.execution)}</b></div><div><span>Institutional data</span><b>{label(settings.providers.institutionalData)}</b></div></article>
    <div className="config-hash"><Icon name="shield"/><div><span>REPRODUCIBLE CONFIGURATION HASH</span><code>{settings.configurationHash}</code></div><button className="secondary-button" onClick={() => refresh()}>Refresh health</button></div>
  </section>;
}
