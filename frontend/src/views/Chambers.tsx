import {
  Boxes,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Layers3,
  Search,
  Wrench,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useApi } from "../api";
import { ExportInventory } from "../ExportInventory";
import { asItems, date, label, matches, toUTC } from "../utils";

import { Badge, ComponentTable, Notice, Panel, State } from "../components";
export function Chambers({
  hierarchy,
  chamberId,
  setChamber,
  onPart,
}: {
  hierarchy: any;
  chamberId: string;
  setChamber: (id: string) => void;
  onPart: (id: string) => void;
}) {
  const sites = hierarchy?.sites || [],
    tools = sites.flatMap((s: any) => s.tools || []),
    currentTool =
      tools.find((t: any) =>
        t.chambers?.some((c: any) => c.id === chamberId),
      ) || tools[0];
  const [toolId, setToolId] = useState(""),
    [query, setQuery] = useState(""),
    [subsystem, setSubsystem] = useState("all"),
    [assembly, setAssembly] = useState("all"),
    [status, setStatus] = useState("all"),
    [historical, setHistorical] = useState(""),
    [at, setAt] = useState("");
  useEffect(() => {
    if (currentTool) setToolId(currentTool.id);
  }, [currentTool?.id]);
  useEffect(() => {
    setAssembly("all");
  }, [chamberId, subsystem]);
  const selectedTool = tools.find((t: any) => t.id === toolId) || currentTool,
    selectedSite =
      sites.find((site: any) =>
        site.tools?.some((tool: any) => tool.id === selectedTool?.id),
      ) || sites[0],
    selectedChamber = selectedTool?.chambers?.find(
      (c: any) => c.id === chamberId,
    );
  const api = useApi(
      chamberId
        ? `/api/inventory?chamber_id=${encodeURIComponent(chamberId)}${at ? `&at=${encodeURIComponent(at)}` : ""}`
        : "/api/inventory",
    ),
    items = asItems(api.data),
    subsystems = [...new Set(items.map((i) => i.subsystem))],
    assemblies = [
      ...new Set(
        items
          .filter((i) => subsystem === "all" || i.subsystem === subsystem)
          .map((i) => i.assembly),
      ),
    ];
  const filtered = items.filter(
    (i) =>
      matches(i, query) &&
      (subsystem === "all" || i.subsystem === subsystem) &&
      (assembly === "all" || i.assembly === assembly) &&
      (status === "all" || i.pm?.status === status),
  );
  return (
    <>
      <div className="equipment-selector">
        <div className="selector-group">
          <label htmlFor="site-select">Fab / site</label>
          <select
            id="site-select"
            value={selectedSite?.id || ""}
            onChange={(e) => {
              const site = sites.find((s: any) => s.id === e.target.value);
              if (site?.tools?.[0]) {
                setToolId(site.tools[0].id);
                setChamber(site.tools[0].chambers[0]?.id || "");
                setSubsystem("all");
                setAssembly("all");
              }
            }}
          >
            {sites.map((s: any) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <ChevronRight size={18} />
        <div className="selector-group">
          <label htmlFor="tool-select">Tool</label>
          <select
            id="tool-select"
            value={selectedTool?.id || ""}
            onChange={(e) => {
              setToolId(e.target.value);
              const t = tools.find((t: any) => t.id === e.target.value);
              setChamber(t?.chambers?.[0]?.id || "");
              setSubsystem("all");
            }}
          >
            {(selectedSite?.tools || []).map((t: any) => (
              <option value={t.id} key={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <ChevronRight size={18} />
        <div className="selector-group">
          <label htmlFor="chamber-select">Chamber</label>
          <select
            id="chamber-select"
            value={chamberId}
            onChange={(e) => {
              setChamber(e.target.value);
              setSubsystem("all");
            }}
          >
            {(selectedTool?.chambers || []).map((c: any) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="selection-status">
          <Badge value={selectedChamber?.status} />
        </div>
      </div>
      <div className="inventory-layout">
        <aside className="hierarchy-panel">
          <div className="hierarchy-title">
            <Layers3 size={16} /> Configuration tree
          </div>
          <button
            className={`tree-root ${subsystem === "all" ? "selected" : ""}`}
            onClick={() => setSubsystem("all")}
          >
            <ChevronDown size={15} />
            <Boxes size={16} />
            {selectedChamber?.name || "All components"}
            <span>{items.length}</span>
          </button>
          {subsystems.map((s: any) => (
            <button
              className={`tree-node ${subsystem === s ? "selected" : ""}`}
              onClick={() => setSubsystem(s)}
              key={s}
            >
              <span className="tree-line" />
              <Wrench size={14} />
              <span>{label(s)}</span>
              <span className="count">
                {items.filter((i) => i.subsystem === s).length}
              </span>
            </button>
          ))}
          <div className="hierarchy-note">
            <CircleHelp size={16} />
            <p>
              Configurable component tree. This is not an OEM chamber schematic.
            </p>
          </div>
        </aside>
        <div className="inventory-main">
          <Panel
            title="Installed component register"
            description={`${selectedTool?.name || "Fleet"} / ${selectedChamber?.name || "All chambers"} · ${at ? "Historical inventory" : "Current physical installation state"}`}
            action={<ExportInventory />}
          >
            <div className="assembly-toolbar">
              <label htmlFor="subsystem-select">
                Subsystem
                <select
                  id="subsystem-select"
                  value={subsystem}
                  onChange={(e) => setSubsystem(e.target.value)}
                >
                  <option value="all">All subsystems</option>
                  {subsystems.map((item: any) => (
                    <option key={item} value={item}>
                      {label(item)}
                    </option>
                  ))}
                </select>
              </label>
              <ChevronRight size={14} />
              <label htmlFor="assembly-select">
                Assembly
                <select
                  id="assembly-select"
                  value={assembly}
                  onChange={(e) => setAssembly(e.target.value)}
                >
                  <option value="all">All assemblies</option>
                  {assemblies.map((item: any) => (
                    <option key={item} value={item}>
                      {label(item)}
                    </option>
                  ))}
                </select>
              </label>
              <span>Configuration-specific physical positions</span>
            </div>
            <div className="table-toolbar">
              <label className="search-box">
                <Search size={16} />
                <input
                  aria-label="Search components"
                  placeholder="Part, serial, revision, or subsystem…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <select
                aria-label="Filter maintenance condition"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="all">All PM conditions</option>
                <option value="overdue">Overdue</option>
                <option value="upcoming">Upcoming</option>
                <option value="ok">Within interval</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
            <div className="historical-toolbar">
              <Clock3 size={15} />
              <label htmlFor="historical-at">Inventory as of (UTC)</label>
              <input
                id="historical-at"
                type="datetime-local"
                value={historical}
                onChange={(e) => setHistorical(e.target.value)}
              />
              <button
                className="button small"
                onClick={() => setAt(toUTC(historical))}
              >
                Apply timestamp
              </button>
              {at && (
                <button
                  className="text-link"
                  onClick={() => {
                    setAt("");
                    setHistorical("");
                  }}
                >
                  Return to current
                </button>
              )}
            </div>
            {at && (
              <Notice>
                Historical view at {date(at)}. Exposure is clipped to the
                selected timestamp.
              </Notice>
            )}
            <State {...api}>
              <ComponentTable
                items={filtered}
                onPart={onPart}
                showLocation={false}
              />
              <div className="table-footer">
                <span>
                  {filtered.length} of {items.length} components
                </span>
                <span>Effective-dated · all times UTC</span>
              </div>
            </State>
          </Panel>
          <Notice>
            All part numbers, serials, and PM policies are fictional. Unverified
            technical specifications remain <strong>unknown</strong>.
          </Notice>
        </div>
      </div>
    </>
  );
}
