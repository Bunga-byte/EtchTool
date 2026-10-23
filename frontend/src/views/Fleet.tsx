import {
  ArrowRight,
  Boxes,
  CalendarClock,
  ChevronRight,
  FileSearch,
  Layers3,
} from "lucide-react";
import { useApi } from "../api";
import { asItems, date, label, formatNumber as num } from "../utils";

import {
  Badge,
  BarChart,
  ComponentTable,
  Metric,
  Panel,
  Progress,
  State,
} from "../components";
import type { View } from "../types";
export function Fleet({
  onChamber,
  onPart,
  onCase,
  onNavigate,
}: {
  onChamber: (id: string) => void;
  onPart: (id: string) => void;
  onCase: (id: string) => void;
  onNavigate: (v: View) => void;
}) {
  const api = useApi("/api/fleet"),
    pm = useApi("/api/pm");
  const d = api.data,
    m = d?.metrics || {};
  return (
    <State {...api}>
      <div className="metrics-grid">
        <Metric
          label="Tools in scope"
          value={m.tools}
          unit="tools"
          icon={Boxes}
          note={`${m.chambers ?? "Unknown"} chambers in synthetic fleet`}
        />
        <Metric
          label="Installed components"
          value={m.installed_components}
          icon={Layers3}
          note="Serialized, with effective-dated history"
        />
        <Metric
          label="Maintenance attention"
          value={m.pm_due}
          icon={CalendarClock}
          note="Upcoming and overdue policies"
          tone="amber"
        />
        <Metric
          label="Open investigations"
          value={m.open_investigations}
          icon={FileSearch}
          note={`${num(m.downtime_hours)} h recorded tool downtime`}
          tone="blue"
        />
      </div>
      <div className="section-heading">
        <div>
          <h2>Equipment at a glance</h2>
          <p>Select a chamber to inspect its installed components.</p>
        </div>
        <span className="eyebrow">SYNTHETIC FLEET</span>
      </div>
      <div className="tool-grid">
        {(d?.tools || []).map((tool: any) => (
          <article className="tool-card" key={tool.id}>
            <div className="tool-header">
              <div className="tool-symbol">
                <Boxes size={22} />
              </div>
              <div>
                <h3>{tool.name}</h3>
                <p>{tool.variant || "Fictional Flex-family configuration"}</p>
              </div>
              <Badge value={tool.status} />
            </div>
            <div className="tool-chambers">
              {(tool.chambers || []).map((ch: any) => (
                <button
                  key={ch.id}
                  className="chamber-chip"
                  onClick={() => onChamber(ch.id)}
                >
                  <span className={`status-light ${ch.status}`} />
                  <span>{ch.name}</span>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
            <div className="tool-footer">
              <span>{tool.chambers?.length || 0} chambers</span>
              <span>Configuration-specific inventory</span>
            </div>
          </article>
        ))}
      </div>
      <div className="two-column">
        <Panel
          title="Maintenance watchlist"
          description="Usage-based thresholds need engineering review"
          action={
            <button className="text-link" onClick={() => onNavigate("pm")}>
              View planner <ArrowRight size={14} />
            </button>
          }
        >
          <ComponentTable
            items={asItems(pm.data)
              .filter((i) => ["upcoming", "overdue"].includes(i.pm?.status))
              .slice(0, 4)}
            onPart={onPart}
            showLocation={false}
          />
          {pm.error && <p className="inline-error">{pm.error}</p>}
        </Panel>
        <Panel
          title="Downtime by subsystem"
          description="Unioned intervals · no duplicate event counting"
        >
          <BarChart items={d?.downtime_by_subsystem || []} />
          <div className="panel-footnote">
            Attribution reflects synthetic engineering decisions, not alarm
            count.
          </div>
        </Panel>
      </div>
      <div className="two-column">
        <Panel
          title="Recent reliability cases"
          description="Symptoms remain separate from confirmed hardware failures"
          action={
            <button
              className="text-link"
              onClick={() => onNavigate("investigations")}
            >
              All cases <ArrowRight size={14} />
            </button>
          }
        >
          <div className="case-list">
            {(d?.recent_failures || []).map((item: any) => (
              <button
                className="case-row"
                key={item.id}
                onClick={() => onCase(item.id)}
              >
                <span className="case-icon">
                  <FileSearch size={18} />
                </span>
                <span>
                  <strong>{item.title}</strong>
                  <small>
                    {item.tool_name} / {item.chamber_name} ·{" "}
                    {date(item.started_at)}
                  </small>
                </span>
                <Badge value={item.status} />
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </Panel>
        <Panel
          title="Data confidence"
          description="Visibility into the evidence behind the numbers"
        >
          <div className="quality-score">
            <span>
              {num(
                typeof d?.data_quality?.completeness === "number"
                  ? d.data_quality.completeness * 100
                  : null,
                0,
              )}
              <small>%</small>
            </span>
            <div>
              <strong>Exposure data completeness</strong>
              <p>{label(d?.data_quality?.issues)} quality observations</p>
            </div>
          </div>
          <Progress
            value={
              typeof d?.data_quality?.completeness === "number"
                ? d.data_quality.completeness * 100
                : null
            }
          />
          <p className="panel-footnote">
            Last synchronization: {date(d?.data_quality?.last_sync)}
          </p>
          <button
            className="text-link panel-inline-action"
            onClick={() => onNavigate("integrations")}
          >
            Inspect source quality <ArrowRight size={14} />
          </button>
        </Panel>
      </div>
    </State>
  );
}
