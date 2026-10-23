import {
  Activity,
  CalendarClock,
  CheckCircle2,
  Search,
  ShieldCheck,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { useApi } from "../api";
import { ExportInventory } from "../ExportInventory";
import { asItems, matches } from "../utils";

import { ComponentTable, Metric, Notice, Panel, State } from "../components";
export function PMPlanner({ onPart }: { onPart: (id: string) => void }) {
  const api = useApi("/api/pm"),
    [status, setStatus] = useState("all"),
    [q, setQ] = useState(""),
    [sort, setSort] = useState("remaining");
  const items = asItems(api.data),
    filtered = items
      .filter(
        (i) => (status === "all" || i.pm?.status === status) && matches(i, q),
      )
      .sort((a, b) =>
        sort === "remaining"
          ? (a.pm?.remaining ?? Infinity) - (b.pm?.remaining ?? Infinity)
          : String(a.tool_name).localeCompare(b.tool_name),
      );
  return (
    <State {...api}>
      <div className="metrics-grid three">
        <Metric
          label="Overdue policies"
          value={items.filter((i) => i.pm?.status === "overdue").length}
          icon={TriangleAlert}
          tone="red"
          note="Review coverage before scheduling"
        />
        <Metric
          label="Approaching threshold"
          value={items.filter((i) => i.pm?.status === "upcoming").length}
          icon={CalendarClock}
          tone="amber"
          note="Within configured policy warning band"
        />
        <Metric
          label="Within maintenance interval"
          value={items.filter((i) => i.pm?.status === "ok").length}
          icon={CheckCircle2}
          note="Usage measured against relevant dimension"
        />
      </div>
      <Notice kind="warning">
        These are <strong>synthetic engineer-entered policies</strong>, not OEM
        limits or site-approved requirements. A maintenance replacement does not
        establish that the component failed.
      </Notice>
      <Panel
        title="Fleet maintenance requirements"
        description="Prioritized by remaining interval · units are component-specific"
        action={<ExportInventory label="Export inventory" />}
      >
        <div className="table-toolbar">
          <div className="segmented">
            {[
              ["all", "All"],
              ["overdue", "Overdue"],
              ["upcoming", "Upcoming"],
              ["ok", "Within interval"],
            ].map(([key, text]) => (
              <button
                className={status === key ? "active" : ""}
                key={key}
                onClick={() => setStatus(key)}
              >
                {text}
              </button>
            ))}
          </div>
          <label className="search-box compact">
            <Search size={16} />
            <input
              aria-label="Search PM requirements"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search component or tool…"
            />
          </label>
          <select
            aria-label="Sort maintenance requirements"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="remaining">Remaining interval</option>
            <option value="tool">Tool name</option>
          </select>
        </div>
        <ComponentTable items={filtered} onPart={onPart} />
        <div className="table-footer">
          <span>{filtered.length} policy requirements</span>
          <span>RF, cycle and calendar policies remain separate</span>
        </div>
      </Panel>
      <div className="three-column policy-cards">
        <div>
          <ShieldCheck size={20} />
          <h3>Policy provenance</h3>
          <p>
            Each threshold carries its origin and verification status. OEM
            limits, site policy, recommendations, and statistical estimates are
            separate categories.
          </p>
        </div>
        <div>
          <Activity size={20} />
          <h3>Exposure-aware decisions</h3>
          <p>
            Intervals use only the dimensions relevant to each component. Gaps
            in source data reduce calculation confidence.
          </p>
        </div>
        <div>
          <Wrench size={20} />
          <h3>Engineering execution</h3>
          <p>
            The planner supports engineering review. It cannot send equipment
            commands or execute maintenance.
          </p>
        </div>
      </div>
    </State>
  );
}
