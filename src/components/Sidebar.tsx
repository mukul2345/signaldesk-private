import { Icon } from "./Icons";

const primary = [
  ["Overview", "grid"], ["Scanner", "scan"], ["Scan history", "book"], ["Trade plans", "plan"],
  ["Paper account", "wallet"], ["Journal", "book"]
] as const;

interface Props { active: string; candidateCount: number; onNavigate: (item: string) => void; }

export function Sidebar({ active, candidateCount, onNavigate }: Props) {
  return <aside className="sidebar">
    <button className="brand" onClick={() => onNavigate("Overview")} aria-label="SignalDesk overview">
      <span className="brand-mark"><span /></span>
      <span><strong>SIGNAL</strong><b>DESK</b></span>
    </button>
    <nav aria-label="Primary navigation">
      <p className="nav-label">WORKSPACE</p>
      {primary.map(([label, icon]) => <button className={`nav-item ${active === label ? "active" : ""}`} key={label} onClick={() => onNavigate(label)}><Icon name={icon}/><span>{label}</span>{label === "Scanner" && <em>{candidateCount}</em>}</button>)}
      <p className="nav-label secondary">SYSTEM</p>
      <button className="nav-item" onClick={() => onNavigate("Alerts")}><Icon name="bell"/><span>Alerts</span><i /></button>
      <button className={`nav-item ${active === "Settings & health" ? "active" : ""}`} onClick={() => onNavigate("Settings & health")}><Icon name="settings"/><span>Settings & health</span></button>
    </nav>
    <div className="sidebar-health">
      <div><span className="health-dot"/><b>Research engine</b></div>
      <p>Demo workspace · protected</p>
    </div>
    <div className="profile"><span>MG</span><div><b>Mukul Gupta</b><small>Private workspace</small></div><button aria-label="Profile options">•••</button></div>
  </aside>;
}
