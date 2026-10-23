import { useState } from "react";
import {
  Database,
  FileCheck2,
  FileText,
  GitBranch,
  Radio,
  Workflow,
} from "lucide-react";
import { Notice } from "../components";
import { SourcesWorkspace } from "./SourcesWorkspace";
import { JobsWorkspace } from "./JobsWorkspace";
import { DocumentsWorkspace } from "./DocumentsWorkspace";
import { ProposalsWorkspace } from "./ProposalsWorkspace";
import { IdentityWorkspace } from "./IdentityWorkspace";
import { SensorsWorkspace } from "./SensorsWorkspace";

type Tab =
  | "sources"
  | "jobs"
  | "documents"
  | "proposals"
  | "identity"
  | "sensors";
const tabs: { id: Tab; label: string; icon: typeof Database }[] = [
  { id: "sources", label: "Sources", icon: Database },
  { id: "jobs", label: "Ingestion jobs", icon: Workflow },
  { id: "documents", label: "Original documents", icon: FileText },
  { id: "proposals", label: "Engineering review", icon: FileCheck2 },
  { id: "identity", label: "Identity mappings", icon: GitBranch },
  { id: "sensors", label: "Sensor registry", icon: Radio },
];
export function EnterpriseWorkspace({ token }: { token: string }) {
  const [tab, setTab] = useState<Tab>("sources"),
    [sourceId, setSourceId] = useState(""),
    [documentId, setDocumentId] = useState(""),
    [proposalId, setProposalId] = useState("");
  return (
    <div className="enterprise-workspace">
      <Notice>
        <strong>Enterprise handoff · synthetic connectors only.</strong>{" "}
        Original records enter staging before engineering review. No live
        connection, external AI processing, or equipment control is available.
      </Notice>
      <nav
        className="enterprise-tabs"
        aria-label="Enterprise integration workspace"
      >
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => setTab(id)}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </nav>
      {tab === "sources" && (
        <SourcesWorkspace
          onJob={(id) => {
            setSourceId(id);
            setTab("jobs");
          }}
        />
      )}
      {tab === "jobs" && (
        <JobsWorkspace
          token={token}
          selectedSource={sourceId}
          onDocuments={() => setTab("documents")}
        />
      )}
      {tab === "documents" && (
        <DocumentsWorkspace
          token={token}
          selected={documentId}
          setSelected={setDocumentId}
          onProposal={(id) => {
            setProposalId(id);
            setTab("proposals");
          }}
        />
      )}
      {tab === "proposals" && (
        <ProposalsWorkspace
          token={token}
          selected={proposalId}
          setSelected={setProposalId}
          onDocument={(id) => {
            setDocumentId(id);
            setTab("documents");
          }}
        />
      )}
      {tab === "identity" && <IdentityWorkspace token={token} />}
      {tab === "sensors" && <SensorsWorkspace token={token} />}
    </div>
  );
}
