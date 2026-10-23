import {
  Activity,
  Boxes,
  ChevronRight,
  CircleHelp,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { date, label, formatNumber as num } from "./utils";

export function Badge({
  value,
  children,
}: {
  value?: unknown;
  children?: ReactNode;
}) {
  const text = String(value || "unknown").toLowerCase();
  const severity = /overdue|fail|conflict|error|unconfirmed/.test(text)
    ? "danger"
    : /upcoming|pending|limited|review|incomplete|open/.test(text)
      ? "warning"
      : /ok|operational|complete|confirmed|resolved|active|good|installed/.test(
            text,
          )
        ? "success"
        : "neutral";
  return (
    <span className={`badge ${severity}`}>
      <span className="badge-dot" />
      {children ?? label(value)}
    </span>
  );
}
export function Notice({
  children,
  kind = "info",
}: {
  children: ReactNode;
  kind?: "info" | "warning";
}) {
  return (
    <div className={`notice ${kind}`}>
      {kind === "warning" ? (
        <TriangleAlert size={17} />
      ) : (
        <CircleHelp size={17} />
      )}
      <div>{children}</div>
    </div>
  );
}
export function State({
  loading,
  error,
  reload,
  children,
}: {
  loading: boolean;
  error: string;
  reload: () => void;
  children: ReactNode;
}) {
  if (loading)
    return (
      <div className="state">
        <RefreshCw className="spin" size={24} />
        <p>Loading engineering records…</p>
      </div>
    );
  if (error)
    return (
      <div className="state error">
        <TriangleAlert size={28} />
        <h3>Could not load records</h3>
        <p>{error}</p>
        <button className="button" onClick={reload}>
          Try again
        </button>
      </div>
    );
  return <>{children}</>;
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <Boxes size={28} />
      <p>{children}</p>
    </div>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Metric({
  label: text,
  value,
  unit,
  icon: Icon,
  note,
  tone = "teal",
}: {
  label: string;
  value: unknown;
  unit?: string;
  icon: typeof Activity;
  note?: string;
  tone?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-top">
        <span>{text}</span>
        <span className={`metric-icon ${tone}`}>
          <Icon size={18} />
        </span>
      </div>
      <div className="metric-value">
        {typeof value === "number" ? num(value) : label(value)}
        <small>{unit}</small>
      </div>
      {note && <div className="metric-note">{note}</div>}
    </div>
  );
}
export function Progress({
  value,
  status,
}: {
  value: unknown;
  status?: unknown;
}) {
  return (
    <div
      className={`progress ${String(status || "")}`}
      role="progressbar"
      aria-valuenow={typeof value === "number" ? Math.round(value) : undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="PM interval consumed"
    >
      <div
        style={{
          width: `${typeof value === "number" ? Math.min(100, Math.max(0, value)) : 0}%`,
        }}
      />
    </div>
  );
}
export function Field({ name, value }: { name: string; value: ReactNode }) {
  return (
    <div className="field">
      <dt>{name}</dt>
      <dd>{value ?? "Unknown"}</dd>
    </div>
  );
}
export function BarChart({
  items,
  unit = "h",
}: {
  items: any[];
  unit?: string;
}) {
  const max = Math.max(...items.map((i) => i.hours ?? i.value ?? 0), 1);
  return (
    <div className="bar-chart">
      {items.length ? (
        items.map((item, i) => (
          <div className="bar-row" key={i}>
            <div className="bar-label">
              {label(item.name ?? item.subsystem ?? item.revision)}
            </div>
            <div className="bar-track">
              <div
                style={{
                  width: `${((item.hours ?? item.value ?? 0) / max) * 100}%`,
                }}
              />
            </div>
            <strong>
              {num(item.hours ?? item.value)} <span>{unit}</span>
            </strong>
          </div>
        ))
      ) : (
        <Empty>No attributed downtime recorded.</Empty>
      )}
    </div>
  );
}
export function LineChart({
  points,
  xKey = "time",
  yKey = "survival",
  color = "#168e85",
  percent = false,
  labelText = "Series",
}: {
  points: any[];
  xKey?: string;
  yKey?: string;
  color?: string;
  percent?: boolean;
  labelText?: string;
}) {
  const valid = points.filter(
    (p) => Number.isFinite(Number(p[xKey])) && Number.isFinite(Number(p[yKey])),
  );
  if (!valid.length)
    return <Empty>No eligible observations for this plot.</Empty>;
  const maxX = Math.max(...valid.map((p) => Number(p[xKey])), 1),
    minX = Math.min(...valid.map((p) => Number(p[xKey])), 0),
    ys = valid.map((p) => Number(p[yKey])),
    minY = percent ? 0 : Math.min(...ys) * 0.95,
    maxY = percent ? 1 : Math.max(...ys) * 1.05 || 1;
  const xy = (p: any) => [
    50 + ((Number(p[xKey]) - minX) / (maxX - minX)) * 590,
    20 + (1 - (Number(p[yKey]) - minY) / (maxY - minY)) * 175,
  ];
  const path = valid
    .map((p, i) => {
      const [x, y] = xy(p);
      return i ? (percent ? `H${x}V${y}` : `L${x},${y}`) : `M${x},${y}`;
    })
    .join(" ");
  return (
    <div className="line-chart">
      <svg viewBox="0 0 680 235" role="img" aria-label={labelText}>
        <title>{labelText}</title>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line
              x1="50"
              x2="645"
              y1={20 + t * 175}
              y2={20 + t * 175}
              stroke="#e6ebef"
              strokeDasharray="3 3"
            />
            <text x="40" y={24 + t * 175} textAnchor="end">
              {percent
                ? `${Math.round((1 - t) * 100)}%`
                : num(minY + (1 - t) * (maxY - minY))}
            </text>
          </g>
        ))}
        <path
          d={path}
          fill="none"
          stroke={color}
          strokeWidth="2.8"
          strokeLinejoin="round"
        />
        {valid.map((p, i) => (
          <circle key={i} cx={xy(p)[0]} cy={xy(p)[1]} r="3" fill={color}>
            <title>{`${num(p[xKey])}: ${num(p[yKey], 3)}`}</title>
          </circle>
        ))}
        <text x="50" y="220">
          {num(minX)}
        </text>
        <text x="640" y="220" textAnchor="end">
          {num(maxX)} {percent ? "exposure hours" : "aligned samples"}
        </text>
      </svg>
    </div>
  );
}

export function ComponentTable({
  items,
  onPart,
  showLocation = true,
}: {
  items: any[];
  onPart: (id: string) => void;
  showLocation?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Component / identity</th>
            {showLocation && <th>Location</th>}
            <th>Exposure</th>
            <th>PM interval</th>
            <th>Condition</th>
            <th>
              <span className="sr-only">Open component</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.id}-${item.position}`}>
              <td>
                <button
                  className="text-link component-link"
                  onClick={() => onPart(item.id)}
                >
                  {item.name}
                </button>
                <div className="cell-sub mono">
                  {item.part_number} · {item.serial_number}
                </div>
                {item.exposure?.attribution_status === "disputed" && (
                  <span className="inventory-dispute">
                    <TriangleAlert size={10} /> Identity disputed
                  </span>
                )}
              </td>
              {showLocation && (
                <td>
                  <span className="table-main">
                    {item.tool_name} / {item.chamber_name}
                  </span>
                  <div className="cell-sub">
                    {item.subsystem} · {item.position}
                  </div>
                </td>
              )}
              <td>
                <span className="table-main mono">
                  {num(item.exposure?.hours)}{" "}
                  <small>
                    {item.exposure?.unit ||
                      (item.exposure?.dimension === "rf_hours"
                        ? "RF h"
                        : label(item.exposure?.dimension))}
                  </small>
                </span>
                <div
                  className={`cell-sub ${item.exposure?.completeness < 0.95 ? "amber-text" : ""}`}
                >
                  {item.exposure?.completeness != null
                    ? `${num(item.exposure.completeness * 100, 0)}% coverage`
                    : "Coverage unknown"}
                </div>
              </td>
              <td>
                <div className="pm-cell">
                  <span>{num(item.pm?.percent_consumed, 0)}%</span>
                  <span className="muted">
                    of {num(item.pm?.threshold)} {item.pm?.unit || "h"}
                  </span>
                </div>
                <Progress
                  value={item.pm?.percent_consumed}
                  status={item.pm?.status}
                />
              </td>
              <td>
                <Badge value={item.pm?.status} />
              </td>
              <td>
                <button
                  className="icon-button row-arrow"
                  onClick={() => onPart(item.id)}
                  aria-label={`Open ${item.serial_number}`}
                >
                  <ChevronRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && (
        <Empty>No components match the selected filters.</Empty>
      )}
    </div>
  );
}

export function FdcPlot({ data }: { data: any }) {
  const rows = Array.isArray(data)
    ? data
    : Array.isArray(data?.points)
      ? data.points
      : [];
  if (!rows.length)
    return <Empty>No aligned FDC trace is linked to this record.</Empty>;
  const groups = [
    ...new Set(
      rows.map(
        (r: any) => `${r.state || "state unknown"}|${r.signal || "signal"}`,
      ),
    ),
  ];
  return (
    <>
      {groups.map((group: any) => {
        const selected = rows
          .filter(
            (r: any) =>
              `${r.state || "state unknown"}|${r.signal || "signal"}` === group,
          )
          .map((r: any, i: number) => ({
            ...r,
            x: r.alignment_minutes ?? i,
            y: r.value,
          }));
        const minX = Math.min(...selected.map((r: any) => r.x)),
          maxX = Math.max(...selected.map((r: any) => r.x)),
          minY = Math.min(...selected.map((r: any) => r.y)) * 0.95,
          maxY = Math.max(...selected.map((r: any) => r.y)) * 1.05;
        const cohorts = [
          ...new Set(selected.map((r: any) => r.cohort || "unclassified")),
        ];
        const xy = (r: any) => [
          55 + ((r.x - minX) / (maxX - minX || 1)) * 580,
          20 + (1 - (r.y - minY) / (maxY - minY || 1)) * 170,
        ];
        return (
          <div className="fdc-overlay" key={group}>
            <div className="trace-context">
              <span>{group.split("|")[1]}</span>
              <small>Matched operating state: {group.split("|")[0]}</small>
            </div>
            <svg
              viewBox="0 0 680 240"
              role="img"
              aria-label="Normal versus pre-failure synthetic FDC trace overlay"
            >
              <title>
                Normal versus pre-failure synthetic FDC trace overlay
              </title>
              {[0, 0.25, 0.5, 0.75, 1].map((t) => (
                <g key={t}>
                  <line
                    x1="55"
                    x2="640"
                    y1={20 + t * 170}
                    y2={20 + t * 170}
                    stroke="#e6ebef"
                    strokeDasharray="3 3"
                  />
                  <text x="45" y={24 + t * 170} textAnchor="end">
                    {num(minY + (1 - t) * (maxY - minY), 2)}
                  </text>
                </g>
              ))}
              {cohorts.map((cohort: any, i: number) => {
                const pts = selected
                  .filter((r: any) => (r.cohort || "unclassified") === cohort)
                  .sort((a: any, b: any) => a.x - b.x);
                return (
                  <path
                    key={cohort}
                    d={pts
                      .map(
                        (r: any, j: number) =>
                          `${j ? "L" : "M"}${xy(r).join(",")}`,
                      )
                      .join(" ")}
                    fill="none"
                    stroke={i === 0 ? "#168e85" : "#bb8546"}
                    strokeWidth="2.6"
                  >
                    <title>{label(cohort)}</title>
                  </path>
                );
              })}
              <text x="55" y="213">
                {num(minX)}
              </text>
              <text x="640" y="213" textAnchor="end">
                {num(maxX)}
              </text>
              <text x="345" y="232" textAnchor="middle">
                Minutes from each synthetic trace window's start
              </text>
            </svg>
            <div className="trace-legend">
              {cohorts.map((cohort: any, i: number) => (
                <span key={cohort}>
                  <i style={{ background: i === 0 ? "#168e85" : "#bb8546" }} />
                  {label(cohort)}
                </span>
              ))}
            </div>
          </div>
        );
      })}
      <p className="panel-footnote">
        Synthetic signal ·{" "}
        {label(rows[0]?.unit || data?.unit || "arbitrary units")}. Cohorts are
        compared only within a matched signal and operating state. Correlation
        does not establish root cause.
      </p>
    </>
  );
}

export function RecordList({ items, empty }: { items: any[]; empty: string }) {
  return (
    <div className="record-list">
      {items.length ? (
        items.map((r: any, i: number) => (
          <div className="record" key={i}>
            <span className="record-dot" />
            <div>
              {typeof r === "string" ? (
                <p>{r}</p>
              ) : (
                <>
                  <strong>
                    {r.title ||
                      r.type ||
                      r.name ||
                      r.hypothesis ||
                      r.description ||
                      r.proposal ||
                      r.finding ||
                      `Record ${i + 1}`}
                  </strong>
                  <p>
                    {r.text ||
                      r.detail ||
                      r.note ||
                      r.evidence ||
                      r.observation ||
                      r.summary ||
                      r.mechanism ||
                      ""}
                  </p>
                  {(r.confidence || r.status || r.quality) && (
                    <Badge value={r.confidence || r.status || r.quality} />
                  )}
                  <small>
                    {[
                      r.source || r.provenance?.source_system,
                      r.source_id || r.provenance?.original_source_id,
                      (r.recorded_at || r.provenance?.recorded_at) &&
                        date(r.recorded_at || r.provenance.recorded_at),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </>
              )}
            </div>
          </div>
        ))
      ) : (
        <Empty>{empty}</Empty>
      )}
    </div>
  );
}
export function Timeline({ items }: { items: any[] }) {
  return (
    <div className="timeline">
      {items.length ? (
        items.map((r: any, i: number) => (
          <div className="timeline-item" key={i}>
            <div className="timeline-node" />
            <div className="timeline-date">
              {date(
                r.timestamp ||
                  r.at ||
                  r.started_at ||
                  r.installed_at ||
                  r.effective_at,
              )}
            </div>
            <div>
              <h3>
                {r.title ||
                  r.action ||
                  r.type ||
                  r.event ||
                  r.reason ||
                  r.tool_name ||
                  "Lifecycle record"}
              </h3>
              <p>
                {r.description ||
                  r.note ||
                  r.findings ||
                  r.finding ||
                  r.details ||
                  [r.chamber_name, r.position, r.removal_reason]
                    .filter(Boolean)
                    .join(" · ")}
              </p>
              {r.removed_at && (
                <p>
                  Removed {date(r.removed_at)} ·{" "}
                  {r.removal_reason || "Reason not recorded"}
                </p>
              )}
              {r.exposure_hours != null && (
                <p>
                  {num(r.exposure_hours)} exposure hours attributed to this
                  installation
                </p>
              )}
              <small>
                {[
                  r.source ||
                    r.source_system ||
                    r.provenance?.source_system ||
                    "Synthetic fixture",
                  r.source_id || r.provenance?.original_source_id,
                  r.provenance?.recorded_at && date(r.provenance.recorded_at),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </small>
            </div>
          </div>
        ))
      ) : (
        <Empty>No historical records are linked.</Empty>
      )}
    </div>
  );
}
