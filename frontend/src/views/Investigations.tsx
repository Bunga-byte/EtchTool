import { ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { mutate, useApi } from "../api";
import { asItems, date, label, formatNumber as num } from "../utils";

import {
  Badge,
  Empty,
  FdcPlot,
  Field,
  Notice,
  Panel,
  RecordList,
  State,
  Timeline,
} from "../components";
export function Investigations({
  selected,
  setSelected,
  onPart,
  token,
}: {
  selected: string;
  setSelected: (id: string) => void;
  onPart: (id: string) => void;
  token: string;
}) {
  const list = useApi("/api/failures"),
    detail = useApi(
      selected ? `/api/failures/${encodeURIComponent(selected)}` : null,
    ),
    [q, setQ] = useState(""),
    [status, setStatus] = useState("confirmed"),
    [note, setNote] = useState(""),
    [message, setMessage] = useState(""),
    [saving, setSaving] = useState(false);
  const cases = asItems(list.data).filter((i) =>
      [i.title, i.tool_name, i.chamber_name, i.mode].some((v) =>
        String(v || "")
          .toLowerCase()
          .includes(q.toLowerCase()),
      ),
    ),
    d = detail.data;
  useEffect(() => {
    if (!selected && asItems(list.data)[0])
      setSelected(asItems(list.data)[0].id);
  }, [list.data, selected, setSelected]);
  async function adjudicate() {
    setSaving(true);
    setMessage("");
    try {
      await mutate(`/api/failures/${selected}/adjudicate`, token, {
        status,
        note,
      });
      setMessage("Engineering decision recorded in the audit trail.");
      setNote("");
      detail.reload();
      list.reload();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <State {...list}>
      <div className="investigation-layout">
        <Panel
          title="Case register"
          description={`${asItems(list.data).length} synthetic episodes`}
          className="case-register"
        >
          <label className="search-box">
            <Search size={16} />
            <input
              placeholder="Search cases…"
              aria-label="Search investigations"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="case-picker">
            {cases.map((c: any) => (
              <button
                key={c.id}
                className={selected === c.id ? "selected" : ""}
                onClick={() => setSelected(c.id)}
              >
                <div>
                  <span className="case-number">{c.id}</span>
                  <Badge value={c.status} />
                </div>
                <strong>{c.title}</strong>
                <small>
                  {c.tool_name} / {c.chamber_name}
                </small>
                <span className="case-meta">
                  {date(c.started_at)}
                  <ChevronRight size={15} />
                </span>
              </button>
            ))}
          </div>
        </Panel>
        <div className="case-detail">
          <State {...detail}>
            {d ? (
              <>
                <div className="case-detail-heading">
                  <span className="eyebrow">EVIDENCE PACKET · {d.id}</span>
                  <h2>{d.title}</h2>
                  <div className="inline-badges">
                    <Badge value={d.status} />
                    <Badge value={d.attribution_status} />
                    <span>
                      {d.tool_name} / {d.chamber_name}
                    </span>
                  </div>
                </div>
                <Notice kind="warning">
                  An alarm is not a proven hardware failure. Attribution and
                  root-cause status require independent engineering
                  adjudication.
                </Notice>
                <div className="detail-summary">
                  <Field
                    name="Component"
                    value={
                      <button
                        className="text-link"
                        onClick={() => onPart(d.component_id)}
                      >
                        {d.component_name || d.component_id}
                        <ChevronRight size={14} />
                      </button>
                    }
                  />
                  <Field name="Observed mode" value={label(d.mode)} />
                  <Field
                    name="Associated tool downtime"
                    value={`${num(d.downtime_hours)} h`}
                  />
                  <Field name="Review gate" value={label(d.review_status)} />
                </div>
                <div className="two-column">
                  <Panel
                    title="Evidence & findings"
                    description="Source observations preserved independently"
                  >
                    <RecordList
                      items={d.evidence || []}
                      empty="No physical evidence has been recorded."
                    />
                  </Panel>
                  <Panel
                    title="Competing hypotheses"
                    description="Correlation is distinct from physical causality"
                  >
                    <RecordList
                      items={d.hypotheses || []}
                      empty="No engineering hypotheses recorded."
                    />
                  </Panel>
                </div>
                <Panel
                  title="Event chronology"
                  description="Raw alarms may belong to one episode"
                >
                  <Timeline items={d.chronology || d.alarms || []} />
                </Panel>
                <Panel
                  title="FDC signature investigation"
                  description="Aligned synthetic samples linked to the case"
                >
                  <FdcPlot data={d.fdc} />
                </Panel>
                <Panel
                  title="Corrective-action proposal"
                  description="Human-reviewed engineering recommendation"
                >
                  <RecordList
                    items={
                      Array.isArray(d.corrective_action)
                        ? d.corrective_action
                        : []
                    }
                    empty="No corrective-action proposal recorded."
                  />
                </Panel>
                <Panel
                  title="Engineering adjudication"
                  description="Changes require an authorized server-validated engineering role"
                >
                  <div className="review-form">
                    <label>
                      Decision
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        <option value="confirmed">Confirmed</option>
                        <option value="unconfirmed">Unconfirmed</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </label>
                    <label>
                      Evidence-based review note
                      <textarea
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        rows={3}
                        placeholder="Record the physical evidence and reason for the decision…"
                      />
                    </label>
                    <button
                      className="button primary"
                      disabled={!token || note.trim().length < 10 || saving}
                      onClick={adjudicate}
                    >
                      {saving ? "Recording…" : "Record engineering decision"}
                    </button>
                    {!token && (
                      <small className="muted">
                        Viewer mode. Add an authorized local access token in
                        Access settings to submit a review.
                      </small>
                    )}
                    {message && <p role="status">{message}</p>}
                  </div>
                </Panel>
              </>
            ) : (
              <Empty>Select an investigation to inspect its evidence.</Empty>
            )}
          </State>
        </div>
      </div>
    </State>
  );
}
