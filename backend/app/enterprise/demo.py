"""Exercise the synthetic source-to-component-to-PM workflow in an isolated DB.

Run from backend with ``../.venv/bin/python -m app.enterprise.demo``.
No existing application database, credentials, or upstream systems are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "synthetic-isolated-demo-admin"
NOTE = "Synthetic engineering demonstration: verified exact source evidence and configuration"


def run_demo(directory: Path) -> dict:
    """Create a fresh local database and drive the same APIs used by the UI."""
    database = directory / "enterprise-demo.db"
    if database.exists():
        raise ValueError("The demonstration requires a new isolated database")
    config = Settings(
        database_url=f"sqlite:///{database}",
        mode="synthetic",
        auth_backend="local_tokens",
        tokens_json={TOKEN: {"subject": "synthetic-demo-engineer", "role": "admin"}},
    )
    app = create_app(config)
    with TestClient(app) as client:

        def request(method: str, path: str, payload=None):
            response = client.request(
                method, path, json=payload, headers={"Authorization": f"Bearer {TOKEN}"}
            )
            if not response.is_success:
                raise RuntimeError(
                    f"Demo {method} {path}: {response.status_code}: {response.text}"
                )
            return response.json()

        def ingest(source: str, original_id: str):
            job = request(
                "POST",
                "/api/enterprise/jobs",
                {
                    "source_id": source,
                    "window_start": "2026-01-01T00:00:00Z",
                    "window_end": "2026-02-01T00:00:00Z",
                    "query": {"original_ids": [original_id]},
                },
            )
            for _ in range(20):
                job = request("POST", f"/api/enterprise/jobs/{job['id']}/run")
                if job["status"] != "pending":
                    break
            if job["status"] != "succeeded":
                raise RuntimeError(f"Synthetic ingestion did not succeed: {job}")
            documents = request("GET", f"/api/enterprise/documents?source_id={source}")[
                "items"
            ]
            document = next(d for d in documents if d["original_id"] == original_id)
            return job, request("GET", f"/api/enterprise/documents/{document['id']}")

        job, document = ingest("informs-demo", "syn-replacement-001")
        proposal = next(p for p in document["proposals"] if p["kind"] == "replacement")
        preview = request("GET", f"/api/enterprise/proposals/{proposal['id']}/preview")
        if not preview["can_approve"]:
            raise RuntimeError("Synthetic replacement failed engineering validation")
        evidence = [span for spans in proposal["evidence"].values() for span in spans]
        if not evidence or any(
            document["text"][s["start"] : s["end"]] != s["quote"] for s in evidence
        ):
            raise RuntimeError(
                "Extracted evidence does not match the preserved original"
            )
        # Staging alone must leave the original serialized component installed.
        staged = request("GET", "/api/inventory?chamber_id=ch-1-a")["items"]
        if "SYN-01A-RF-003" in {row["serial_number"] for row in staged}:
            raise RuntimeError("Unapproved extraction changed the canonical inventory")
        approval = request(
            "POST",
            f"/api/enterprise/proposals/{proposal['id']}/review",
            {"decision": "approve", "note": NOTE},
        )
        baseline = request("GET", "/api/components/cmp-enterprise-spare")

        telemetry_job, telemetry_document = ingest("fdc-demo", "syn-fdc-001")
        unapproved = request("GET", "/api/components/cmp-enterprise-spare")
        mappings = request("GET", "/api/enterprise/mappings")["items"]
        for mapping in mappings:
            if mapping["verification"] == "proposed":
                request(
                    "POST",
                    f"/api/enterprise/mappings/{mapping['id']}/review",
                    {"decision": "approve", "note": NOTE},
                )
        rules = request("GET", "/api/enterprise/exposure-rules")["items"]
        for rule in rules:
            if rule["verification"] == "proposed":
                request(
                    "POST",
                    f"/api/enterprise/exposure-rules/{rule['id']}/review",
                    {"decision": "approve", "note": NOTE},
                )

        current = request("GET", "/api/components/cmp-enterprise-spare")
        removed = request("GET", "/api/components/cmp-1-a-rf")
        traces = request(
            "GET",
            "/api/enterprise/components/cmp-enterprise-spare/telemetry"
            "?start=2026-01-26T00:00:00Z&end=2026-01-31T00:00:00Z",
        )
        lineage = request(
            "GET", "/api/enterprise/components/cmp-enterprise-spare/lineage"
        )
        inventory = request("GET", "/api/inventory?chamber_id=ch-1-a")["items"]
        pm = request("GET", "/api/pm")["items"]
        return {
            "synthetic": True,
            "isolated_database": True,
            "as_of": "2026-01-31T00:00:00Z",
            "source_job": {
                "id": job["id"],
                "status": job["status"],
                "metrics": job["metrics"],
            },
            "telemetry_job": {
                "id": telemetry_job["id"],
                "status": telemetry_job["status"],
                "metrics": telemetry_job["metrics"],
            },
            "source_document_id": document["id"],
            "telemetry_document_id": telemetry_document["id"],
            "proposal_id": proposal["id"],
            "evidence_spans_verified": len(evidence),
            "review_status": approval["proposal"]["status"],
            "failure_created": approval["canonical"]["failure_created"],
            "replacement_at": current["installed_at"],
            "old_removed_at": removed["removed_at"],
            "old_component_rf_hours": removed["exposure"]["hours"],
            "baseline_new_component_rf_hours": baseline["exposure"]["hours"],
            "unapproved_telemetry_rf_hours": unapproved["exposure"]["hours"],
            "approved_new_component_rf_hours": current["exposure"]["hours"],
            "pm": current["pm"],
            "exposure": current["exposure"],
            "inventory_refreshed": any(row["id"] == current["id"] for row in inventory),
            "fleet_pm_refreshed": next(
                (row["pm"] for row in pm if row["id"] == current["id"]), None
            ),
            "telemetry": traces,
            "lineage": lineage,
            "component_api": "/api/components/cmp-enterprise-spare",
            "browser_test": "frontend/e2e/enterprise.spec.ts",
        }


def main():
    with TemporaryDirectory(prefix="frip-enterprise-demo-") as directory:
        result = run_demo(Path(directory))
        # Keep CLI output concise; complete traces are checked by acceptance tests.
        result.pop("telemetry")
        result["lineage_records"] = len(result.pop("lineage")["items"])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
