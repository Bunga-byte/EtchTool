import { ArrowDownToLine } from "lucide-react";
import { useState } from "react";
import { downloadInventory } from "./api";
export function ExportInventory({ label = "Export CSV" }: { label?: string }) {
  const [error, setError] = useState("");
  return (
    <div className="export-control">
      <a
        className="button subtle"
        href="/api/export/inventory.csv"
        onClick={async (e) => {
          e.preventDefault();
          setError("");
          try {
            await downloadInventory();
          } catch (reason) {
            setError((reason as Error).message);
          }
        }}
      >
        <ArrowDownToLine size={15} />
        {label}
      </a>
      {error && (
        <span className="inline-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
