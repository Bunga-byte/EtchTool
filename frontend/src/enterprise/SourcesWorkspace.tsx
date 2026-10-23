import { useEffect, useState } from "react";
import { ArrowRight, Database } from "lucide-react";
import { useApi } from "../api";
import { Badge, Empty, Field, Notice, Panel, State } from "../components";
import { date, label, formatNumber as num } from "../utils";
import { enterprisePath, Metadata } from "./shared";
import { recordItems, scopeLabel } from "./utils";

export function SourcesWorkspace({
  onJob,
}: {
  onJob: (source: string) => void;
}) {
  const api = useApi(`${enterprisePath}/sources`),
    [selected, setSelected] = useState(""),
    sources = recordItems(api.data);
  useEffect(() => {
    if (!selected && sources[0]) setSelected(sources[0].id);
  }, [api.data, selected]);
  const detail = useApi(
      selected
        ? `${enterprisePath}/sources/${encodeURIComponent(selected)}/capabilities`
        : null,
    ),
    source = sources.find((item) => item.id === selected);
  const capabilities = detail.data?.capabilities || detail.data;
  return (
    <State {...api} loading={api.loading && !api.data}>
      <div className="enterprise-section-heading">
        <div>
          <h2>Registered integration sources</h2>
          <p>Capabilities, authorization scopes, and operational evidence.</p>
        </div>
        <span className="eyebrow">{sources.length} REGISTERED SOURCES</span>
      </div>
      <div className="connector-grid enterprise-source-grid">
        {sources.map((item: any) => (
          <article
            className={`panel connector-card enterprise-source ${selected === item.id ? "selected" : ""}`}
            key={item.id}
          >
            <div className="connector-header">
              <span className="connector-icon">
                <Database size={20} />
              </span>
              <Badge
                value={item.status || item.connection_status || "not connected"}
              />
            </div>
            <h2>{item.name || item.id}</h2>
            <p>
              {item.description ||
                item.connector_type ||
                item.kind ||
                "Source-neutral integration registration"}
            </p>
            <dl className="connector-stats">
              <Field
                name="Connection type"
                value={label(
                  item.connection_type || item.transport || item.connector_kind,
                )}
              />
              <Field
                name="Pending approvals"
                value={num(item.pending_approvals, 0)}
              />
              <Field
                name="Processed / rejected"
                value={`${num(item.records_processed ?? item.processed, 0)} / ${num(item.records_rejected ?? item.rejected, 0)}`}
              />
              <Field
                name="Last success"
                value={date(item.last_success_at || item.last_sync)}
              />
            </dl>
            <div className="enterprise-source-actions">
              <button
                className="text-link"
                onClick={() => setSelected(item.id)}
              >
                Inspect source
              </button>
              <button className="text-link" onClick={() => onJob(item.id)}>
                Plan bounded job <ArrowRight size={13} />
              </button>
            </div>
          </article>
        ))}
      </div>
      {!sources.length && (
        <Empty>No source is registered for your authorized scope.</Empty>
      )}
      {source && (
        <Panel
          title={`Source capability contract · ${source.name || source.id}`}
          description="Unsupported operations must remain unavailable to connector clients"
        >
          <Metadata
            record={source}
            fields={[
              ["id", "FRIP source ID"],
              ["connector_kind", "Connector implementation"],
              ["last_success_at", "Last successful sync"],
              ["latest_source_timestamp", "Latest source timestamp"],
              ["records_discovered", "Records discovered"],
              [
                "unresolved_identity_conflicts",
                "Unresolved identity conflicts",
              ],
            ]}
          />
          <div className="source-scopes">
            <Field
              name="Authorized equipment"
              value={scopeLabel(
                source.authorized_equipment ||
                  source.authorized_scope?.equipment_aliases ||
                  source.equipment_scope ||
                  source.scope?.equipment,
              )}
            />
            <Field
              name="Authorized collections"
              value={scopeLabel(
                source.authorized_collections ||
                  source.authorized_scope?.collections ||
                  source.collection_scope ||
                  source.scope?.collections,
              )}
            />
            <Field name="Last error" value={label(source.last_error)} />
          </div>
          <State {...detail} loading={detail.loading && !detail.data}>
            <div className="capability-grid">
              {capabilities && typeof capabilities === "object" ? (
                Object.entries(capabilities).map(([name, value]) => {
                  const supported =
                    typeof value === "boolean"
                      ? value
                      : typeof value === "object" && value !== null
                        ? "supported" in value
                          ? (value as any).supported
                          : null
                        : null;
                  return (
                    <div className="capability-row" key={name}>
                      <strong>{label(name)}</strong>
                      <Badge
                        value={
                          supported === true
                            ? "supported"
                            : supported === false
                              ? "unsupported"
                              : "declared contract"
                        }
                      />
                      {typeof value !== "boolean" && (
                        <small>{label(value)}</small>
                      )}
                    </div>
                  );
                })
              ) : (
                <Empty>No capabilities are declared by this source.</Empty>
              )}
            </div>
          </State>
          <Notice>
            Connection configuration and authentication are provider interfaces.
            Live endpoints, credentials, and internal source schemas must be
            supplied in the approved environment.
          </Notice>
        </Panel>
      )}
    </State>
  );
}
