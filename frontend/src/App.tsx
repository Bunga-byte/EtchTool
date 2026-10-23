import {
  Activity,
  CalendarClock,
  ChevronRight,
  Database,
  FileSearch,
  FlaskConical,
  Layers3,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { AccessDialog } from "./AccessDialog";
import { setApiToken, useApi } from "./api";

import { State } from "./components";
import type { View } from "./types";
import { Analytics } from "./views/Analytics";
import { Chambers } from "./views/Chambers";
import { Fleet } from "./views/Fleet";
import { Integrations } from "./views/Integrations";
import { Investigations } from "./views/Investigations";
import { PartDrawer } from "./views/PartDrawer";
import { PMPlanner } from "./views/PMPlanner";
const navigation: {
  id: View;
  name: string;
  icon: typeof Activity;
  section?: string;
}[] = [
  { id: "fleet", name: "Fleet overview", icon: LayoutDashboard },
  { id: "chambers", name: "Chamber inventory", icon: Layers3 },
  { id: "pm", name: "PM planner", icon: CalendarClock },
  {
    id: "analytics",
    name: "Reliability analytics",
    icon: Activity,
    section: "ENGINEERING",
  },
  { id: "investigations", name: "Investigations", icon: FileSearch },
  {
    id: "integrations",
    name: "Data integrations",
    icon: Database,
    section: "PLATFORM",
  },
];
const titles: Record<View, { title: string; subtitle: string }> = {
  fleet: {
    title: "Fleet overview",
    subtitle: "A connected view of equipment, exposure, and reliability.",
  },
  chambers: {
    title: "Chamber inventory",
    subtitle:
      "Trace every serialized component from installation to disposition.",
  },
  pm: {
    title: "Maintenance planner",
    subtitle:
      "Prioritize upcoming work using explicit, traceable maintenance policies.",
  },
  analytics: {
    title: "Reliability analytics",
    subtitle:
      "Compare failures against operating exposure, with uncertainty in view.",
  },
  investigations: {
    title: "Failure investigations",
    subtitle:
      "Follow the evidence. Separate observed symptoms from confirmed causes.",
  },
  integrations: {
    title: "Data integrations & quality",
    subtitle:
      "Inspect source records, synchronization health, and unresolved conflicts.",
  },
};

export default function App() {
  const [view, setView] = useState<View>("fleet"),
    [chamberId, setChamberId] = useState(""),
    [partId, setPartId] = useState(""),
    [caseId, setCaseId] = useState(""),
    [mobileMenu, setMobileMenu] = useState(false),
    [settings, setSettings] = useState(false),
    [token, setToken] = useState("");
  const hierarchy = useApi("/api/hierarchy"),
    health = useApi("/api/health");
  useEffect(() => {
    if (!chamberId && hierarchy.data?.sites?.[0]?.tools?.[0]?.chambers?.[0])
      setChamberId(hierarchy.data.sites[0].tools[0].chambers[0].id);
  }, [hierarchy.data, chamberId]);
  function navigate(v: View) {
    setView(v);
    setMobileMenu(false);
    window.scrollTo({ top: 0 });
  }
  function openChamber(id: string) {
    setChamberId(id);
    navigate("chambers");
  }
  function openCase(id: string) {
    setPartId("");
    setCaseId(id);
    navigate("investigations");
  }
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <aside className={`sidebar ${mobileMenu ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-icon">
            <Activity size={25} />
          </div>
          <div>
            FRIP<span>RELIABILITY INTELLIGENCE</span>
          </div>
          <button
            className="mobile-close icon-button"
            aria-label="Close navigation"
            onClick={() => setMobileMenu(false)}
          >
            <X />
          </button>
        </div>
        <div className="workspace-label">ENGINEERING WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ id, name, icon: Icon, section }) => (
            <div key={id}>
              {section && <div className="nav-section">{section}</div>}
              <button
                className={`nav-item ${view === id ? "active" : ""}`}
                aria-current={view === id ? "page" : undefined}
                onClick={() => navigate(id)}
              >
                <Icon size={19} />
                <span>{name}</span>
                {view === id && <ChevronRight size={15} />}
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="synthetic-sidebar">
            <FlaskConical size={18} />
            <div>
              <strong>Synthetic environment</strong>
              <p>No enterprise systems connected</p>
            </div>
          </div>
          <button
            className="nav-item"
            onClick={() => {
              setSettings(true);
            }}
          >
            <ShieldCheck size={18} />
            <span>Access settings</span>
          </button>
          <div className="profile">
            <div className="avatar">ER</div>
            <div>
              <strong>Engineering workspace</strong>
              <span>
                {token ? "Access token supplied" : "Read-only viewer"}
              </span>
            </div>
          </div>
          <div className="app-version">
            FRIP foundation <span>v0.1.0</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button menu-button"
              onClick={() => setMobileMenu(!mobileMenu)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{navigation.find((n) => n.id === view)?.name}</strong>
          </div>
          <div className="topbar-right">
            <span className="environment-pill">
              <FlaskConical size={13} /> SYNTHETIC DATA
            </span>
            <span className="api-status">
              <span
                className={`status-light ${health.error ? "error" : "operational"}`}
              />
              {health.error ? "API unavailable" : "Local development"}
            </span>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                FLEX RELIABILITY INTELLIGENCE PLATFORM
              </div>
              <h1>{titles[view].title}</h1>
              <p>{titles[view].subtitle}</p>
            </div>
            <div className="page-heading-actions">
              <span className="scope-label">
                <span className="status-light operational" /> Fictional
                demonstration fleet
              </span>
              <button
                className="button subtle"
                aria-label="Refresh workspace"
                onClick={() => {
                  hierarchy.reload();
                  health.reload();
                  setView((v) => v);
                  window.dispatchEvent(new Event("frip-refresh"));
                }}
              >
                <RefreshCw size={15} />
                <span>Refresh</span>
              </button>
            </div>
          </div>
          <div className="demo-banner">
            <FlaskConical size={17} />
            <span>
              <strong>Synthetic engineering data.</strong> Fictional equipment
              and policies. No OEM specifications or production predictions.
            </span>
            <span className="demo-banner-end">DEVELOPMENT ONLY</span>
          </div>
          {view === "fleet" && (
            <Fleet
              onChamber={openChamber}
              onPart={setPartId}
              onCase={openCase}
              onNavigate={navigate}
            />
          )}{" "}
          {view === "chambers" && (
            <State {...hierarchy}>
              <Chambers
                hierarchy={hierarchy.data}
                chamberId={chamberId}
                setChamber={setChamberId}
                onPart={setPartId}
              />
            </State>
          )}
          {view === "pm" && <PMPlanner onPart={setPartId} />}{" "}
          {view === "analytics" && <Analytics />}
          {view === "investigations" && (
            <Investigations
              selected={caseId}
              setSelected={setCaseId}
              onPart={setPartId}
              token={token}
            />
          )}{" "}
          {view === "integrations" && <Integrations token={token} />}
          <footer className="page-footer">
            <span>FRIP · Engineering evidence before conclusions</span>
            <span>
              <ShieldCheck size={13} /> Synthetic data only · No equipment
              control
            </span>
          </footer>
        </main>
      </div>
      {partId && (
        <PartDrawer
          key={partId}
          id={partId}
          onClose={() => setPartId("")}
          onCase={openCase}
          onPart={setPartId}
        />
      )}{" "}
      {settings && (
        <AccessDialog
          onClose={() => setSettings(false)}
          onToken={(value) => {
            setToken(value);
            setApiToken(value);
          }}
        />
      )}
    </div>
  );
}
