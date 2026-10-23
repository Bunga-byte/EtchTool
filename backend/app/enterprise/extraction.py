"""Deterministic fact proposals plus a constrained internal-AI extension boundary.

Extraction stages claims; it never writes authoritative equipment state.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .contracts import EvidenceSpan, FactProposalDraft, ParsedDocument, TextBlock


EXTRACTION_VERSION = "frip-key-fields-v1.1"


class EngineeringClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["installation", "replacement", "maintenance", "inventory", "failure_evidence"]
    tool_alias: str | None = None
    chamber_alias: str | None = None
    position_alias: str | None = None
    equipment_configuration: str | None = None
    component_name: str | None = None
    component_serial: str | None = None
    old_component_serial: str | None = None
    part_number: str | None = None
    revision: str | None = None
    installed_at: str | None = None
    removed_at: str | None = None
    maintenance_type: str | None = None
    completed_at: str | None = None
    pm_completed_at: str | None = None
    equipment_restored_at: str | None = None
    work_order_reference: str | None = None
    failure_id: str | None = None
    findings: str | None = None
    replacement_reason: str | None = None
    failure_symptom: str | None = None
    reported_failure_mode: str | None = None
    technician_diagnosis: str | None = None
    troubleshooting_actions: str | None = None
    root_cause_finding: str | None = None
    downtime_reference: str | None = None
    related_attachments: str | None = None

    @field_validator("installed_at", "removed_at", "completed_at", "pm_completed_at", "equipment_restored_at")
    @classmethod
    def timestamps(cls, value):
        if value is not None:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("extracted timestamps must include UTC offset")
        return value

    @field_validator("*", mode="before")
    @classmethod
    def bounded_strings(cls, value):
        if isinstance(value,str) and len(value) > 4000:
            raise ValueError("claim field exceeds extraction length limit")
        return value


LABELS = {
    "kind":"kind", "action":"kind", "eventtype":"kind",
    "tool":"tool_alias", "toolalias":"tool_alias", "toolid":"tool_alias",
    "chamber":"chamber_alias", "chamberalias":"chamber_alias", "chamberid":"chamber_alias",
    "position":"position_alias", "positionalias":"position_alias", "slot":"position_alias",
    "configuration":"equipment_configuration", "equipmentconfiguration":"equipment_configuration",
    "componentname":"component_name", "component":"component_name",
    "componentserial":"component_serial", "newserial":"component_serial", "serialnumber":"component_serial",
    "oldcomponentserial":"old_component_serial", "oldserial":"old_component_serial",
    "partnumber":"part_number", "oempartnumber":"part_number",
    "revision":"revision", "componentrevision":"revision",
    "installedat":"installed_at", "installationtimestamp":"installed_at",
    "removedat":"removed_at", "removaltimestamp":"removed_at",
    "maintenancetype":"maintenance_type", "completedat":"completed_at", "repaircompletion":"completed_at",
    "pmcompletedat":"pm_completed_at", "equipmentrestoredat":"equipment_restored_at",
    "workorderreference":"work_order_reference", "workorder":"work_order_reference",
    "failureid":"failure_id", "findings":"findings", "replacementreason":"replacement_reason",
    "failuresymptom":"failure_symptom", "reportedfailuremode":"reported_failure_mode",
    "techniciandiagnosis":"technician_diagnosis", "troubleshootingactions":"troubleshooting_actions",
    "rootcausefinding":"root_cause_finding", "downtimereference":"downtime_reference",
    "relatedattachments":"related_attachments",
}


def _label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _evidence(parsed: ParsedDocument, block: TextBlock, start: int, end: int) -> EvidenceSpan:
    # Raw offsets are exact when the parsed block preserves the source text.
    raw_start,raw_end = block.source_start,block.source_end
    if raw_start is not None and raw_end is not None and raw_end - raw_start == len(block.text):
        raw_start += start - block.start
        raw_end = raw_start + end - start
    if block.source_segments:
        overlaps = [segment for segment in block.source_segments if segment.start < end and segment.end > start]
        if overlaps:
            first,last = overlaps[0],overlaps[-1]
            raw_start = first.source_start
            raw_end = last.source_end
            if first.source_end-first.source_start == first.end-first.start:
                raw_start += max(start-first.start,0)
            if last.source_end-last.source_start == last.end-last.start:
                raw_end -= max(last.end-end,0)
    return EvidenceSpan(source_system=parsed.source_system,original_id=parsed.original_id,revision=parsed.revision,
        content_hash=parsed.content_hash,block_id=block.id,quote=parsed.text[start:end],start=start,end=end,
        page=block.page,row=block.row,sheet=block.sheet,source_start=raw_start,source_end=raw_end,
        locator=block.locator,parser_version=parsed.parser_version,extraction_version=EXTRACTION_VERSION,
        text_extraction_method=block.text_extraction_method,text_extraction_confidence=block.text_extraction_confidence,
        text_extraction_provider_version=block.text_extraction_provider_version)


def _csv_tokens(row: str) -> list[tuple[int,int]]:
    tokens = []
    start = 0
    quote = False
    index = 0
    while index < len(row):
        value = row[index]
        if value == '"':
            if quote and index+1 < len(row) and row[index+1] == '"':
                index += 2
                continue
            quote = not quote
        if value == ',' and not quote:
            tokens.append((start,index))
            start = index + 1
        index += 1
    tokens.append((start,len(row)))
    return tokens


def extract_facts(parsed: ParsedDocument, field_mapping: dict[str,str] | None = None) -> list[FactProposalDraft]:
    """Extract explicit key/value facts only; missing identities remain missing."""
    if parsed.status != "parsed":
        return []
    mapping = dict(LABELS)
    for source,target in (field_mapping or {}).items():
        if target not in EngineeringClaim.model_fields:
            raise ValueError(f"unknown extraction mapping target {target}")
        mapping[_label(source)] = target
    groups: dict[str,dict[str,Any]] = {}

    def add(group, field, value, evidence):
        if field is None or value in (None, ""):
            return
        bucket = groups.setdefault(group,{"payload":{},"evidence":{},"issues":[]})
        if field in bucket["payload"] and bucket["payload"][field] != value:
            bucket["issues"].append(f"conflicting extracted values for {field}; no authoritative value selected")
            bucket["payload"].pop(field,None)
            bucket["evidence"].pop(field,None)
            bucket.setdefault("conflicted",set()).add(field)
            return
        if field in bucket.get("conflicted",set()):
            return
        bucket["payload"][field] = value
        bucket["evidence"].setdefault(field,[]).append(evidence)

    csv_blocks = [block for block in parsed.blocks if block.locator.startswith("csv:")]
    if csv_blocks:
        headers = next(csv.reader([csv_blocks[0].text]))
        for block in csv_blocks[1:]:
            values = next(csv.reader(io.StringIO(block.text)))
            spans = _csv_tokens(block.text)
            for header,value,(start,end) in zip(headers,values,spans):
                add(f"csv:{block.row}",mapping.get(_label(header)),value,
                    _evidence(parsed,block,block.start+start,block.start+end))
    xlsx_blocks = [block for block in parsed.blocks if block.locator.startswith("xlsx:")]
    if xlsx_blocks:
        # Explicit first-row headings only; no inferred free-form cell relationships.
        headings = {}
        for block in xlsx_blocks:
            coordinate = block.locator.rsplit("!",1)[-1]
            column = re.match(r"[A-Z]+",coordinate).group()
            if block.row == 1:
                headings[(block.sheet,column)] = mapping.get(_label(block.text))
            elif not block.text.startswith("[FORMULA NOT EVALUATED]"):
                add(f"xlsx:{block.sheet}:{block.row}",headings.get((block.sheet,column)),block.text,
                    _evidence(parsed,block,block.start,block.end))
    for block in parsed.blocks:
        if block.locator.startswith(("csv:","xlsx:")):
            continue
        if block.locator.startswith("json:"):
            path = block.locator[5:]
            if "." not in path:
                continue
            group,key = path.rsplit(".",1)
            target = mapping.get(_label(key))
            value = json.loads(block.text)
            if target and isinstance(value,str):
                add(group,target,value,_evidence(parsed,block,block.start,block.end))
            continue
        # HTML/PDF/OCR/text blocks can contain multiple explicit labelled lines.
        for match in re.finditer(r"(?m)^\s*([^:\n]{1,80}):[ \t]*(.+?)\s*$",block.text):
            target = mapping.get(_label(match.group(1)))
            if target:
                start = block.start + match.start(2)
                end = block.start + match.end(2)
                add("document",target,match.group(2),_evidence(parsed,block,start,end))
    proposals = []
    for bucket in groups.values():
        payload = bucket["payload"]
        if "kind" not in payload:
            continue
        issues = list(bucket["issues"])
        try:
            claim = EngineeringClaim.model_validate(payload)
        except ValidationError as exc:
            for error in exc.errors():
                field = str(error["loc"][0])
                issues.append(f"invalid {field}: {error['msg']}")
                payload.pop(field,None)
                bucket["evidence"].pop(field,None)
            if "kind" not in payload:
                continue
            claim = EngineeringClaim.model_validate(payload)
        payload = claim.model_dump(exclude_none=True)
        required = ["tool_alias","chamber_alias","position_alias","component_serial"]
        if claim.kind == "replacement":
            required += ["old_component_serial","removed_at","installed_at"]
        elif claim.kind in {"installation","inventory"}:
            required += ["installed_at"]
        elif claim.kind == "maintenance":
            required = ["tool_alias","chamber_alias","component_serial","maintenance_type"]
        else:
            required = ["tool_alias","chamber_alias","findings"]
        for field in required:
            if not payload.get(field):
                issues.append(f"missing evidence for {field}; canonical promotion must remain blocked")
        draft = FactProposalDraft(kind=claim.kind,payload=payload,evidence={field:bucket["evidence"][field] for field in payload},
                                  confidence={field:min([0.95]+[span.text_extraction_confidence for span in bucket["evidence"][field]
                                                              if span.text_extraction_confidence is not None]) for field in payload},
                                  method="deterministic_key_fields",
                                  extraction_version=EXTRACTION_VERSION,issues=issues)
        validate_proposal_evidence(parsed,draft)
        proposals.append(draft)
    return proposals


class InternalAIExtractor(Protocol):
    """Implement only with approved internal inference; there is no external client."""
    version: str

    def propose(self, document: ParsedDocument, output_schema: dict[str,Any]) -> list[dict[str,Any]]: ...


def validate_proposal_evidence(parsed: ParsedDocument, proposal: FactProposalDraft) -> None:
    claim = EngineeringClaim.model_validate(proposal.payload)
    if claim.kind != proposal.kind:
        raise ValueError("proposal kind disagrees with structured payload")
    if set(proposal.payload) - set(proposal.evidence):
        raise ValueError("missing evidence for proposed fields")
    if set(proposal.evidence) != set(proposal.payload) or set(proposal.confidence) != set(proposal.payload):
        raise ValueError("evidence and confidence fields must exactly match the structured payload")
    blocks = {block.id:block for block in parsed.blocks}
    for field,value in proposal.payload.items():
        references = proposal.evidence.get(field,[])
        if not references:
            raise ValueError(f"missing evidence for proposed field {field}")
        if field not in proposal.confidence or not 0 <= proposal.confidence[field] <= 1:
            raise ValueError("proposal confidence must be explicit and between zero and one")
        supported = False
        for reference in references:
            block = blocks.get(reference.block_id)
            if (reference.source_system != parsed.source_system or reference.original_id != parsed.original_id or
                    reference.revision != parsed.revision or reference.content_hash != parsed.content_hash or
                    reference.parser_version != parsed.parser_version or block is None):
                raise ValueError("evidence references a different source version or parser")
            if not block.start <= reference.start < reference.end <= block.end:
                raise ValueError("evidence span lies outside its source block")
            if parsed.text[reference.start:reference.end] != reference.quote:
                raise ValueError("evidence quote does not match exact source span")
            expected = _evidence(parsed,block,reference.start,reference.end)
            if any(getattr(reference,key) != getattr(expected,key) for key in
                   ("page","row","sheet","source_start","source_end","locator","text_extraction_method",
                    "text_extraction_confidence","text_extraction_provider_version")):
                raise ValueError("evidence source location does not match its source block")
            # Identity/engineering facts must have lexical support. Interpretation
            # beyond explicit source wording belongs in a reviewed narrative.
            narrative_fields = {"findings","replacement_reason","failure_symptom","reported_failure_mode",
                                "technician_diagnosis","troubleshooting_actions","root_cause_finding","related_attachments"}
            if field in narrative_fields and str(value).casefold() in reference.quote.casefold():
                supported = True
            else:
                decoded = reference.quote.strip()
                try:
                    candidate = json.loads(decoded)
                    if isinstance(candidate,str):
                        decoded = candidate
                except (ValueError, TypeError):
                    # CSV quoted fields use doubled quote escaping.
                    try:
                        candidate = next(csv.reader([decoded],strict=True))
                        if len(candidate)==1:
                            decoded = candidate[0]
                    except csv.Error:
                        pass
                if decoded.strip() == str(value).strip():
                    supported = True
        if not supported:
            raise ValueError(f"unsupported value for proposed field {field}")
        text_confidence = [reference.text_extraction_confidence for reference in references
                           if reference.text_extraction_confidence is not None]
        if text_confidence and proposal.confidence[field] > min(text_confidence):
            raise ValueError("proposal confidence exceeds supporting OCR text confidence")


def propose_with_internal_ai(parsed: ParsedDocument, provider: InternalAIExtractor) -> list[FactProposalDraft]:
    """Validate schema, source anchoring and lexical support before staging AI output."""
    if parsed.status != "parsed":
        return []
    schema = FactProposalDraft.model_json_schema()
    schema["properties"]["payload"] = EngineeringClaim.model_json_schema()
    raw = provider.propose(parsed,schema)
    if len(raw) > 1000:
        raise ValueError("internal AI returned too many proposals")
    proposals = []
    for item in raw:
        draft = FactProposalDraft.model_validate(item)
        validate_proposal_evidence(parsed,draft)
        evidence = {field:[reference.model_copy(update={"extraction_version":provider.version}) for reference in references]
                    for field,references in draft.evidence.items()}
        draft = draft.model_copy(update={"method":"internal_ai_proposal","extraction_version":provider.version,"evidence":evidence})
        proposals.append(draft)
    return proposals
