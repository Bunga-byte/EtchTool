import io
import json
from datetime import datetime, timedelta, timezone
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError

from app.enterprise.contracts import (
    AccessDenied, CapabilityUnsupported, ConnectionConfig, PermanentConnectorError,
    DocumentMetadata, SearchQuery, SourceDocument, SourceScope, metadata_version_token,
)
from app.enterprise.connectors import SyntheticFileConnector, fixture_connector
from app.enterprise.documents import OCRPage, ParserLimits, parse_document
from app.enterprise.extraction import extract_facts, propose_with_internal_ai, validate_proposal_evidence


def doc(content, mime="text/plain", revision="1"):
    return SourceDocument(original_id="SYN-DOC-TEST",revision=revision,source_system="synthetic_informs",
        collection="maintenance",title="Synthetic test document",mime_type=mime,
        content=content.encode() if isinstance(content,str) else content,equipment_alias="tool1a",chamber_alias="ch1a",
        recorded_at=datetime(2026,1,26,tzinfo=timezone.utc),effective_at=datetime(2026,1,26,tzinfo=timezone.utc))


def small_scope(source="informs-demo",collections=frozenset({"maintenance"})):
    return SourceScope(source_id=source,equipment_aliases=frozenset({"tool1a"}),collections=collections)


def explicit_claim():
    return "\n".join(["Kind: installation","Tool alias: tool1a","Chamber alias: ch1a","Position alias: rf1a",
        "Component serial: SYN-NEW-003","Installed at: 2026-01-26T00:00:00Z"])


def test_fixture_discovery_filters_and_scope_are_enforced():
    connector=fixture_connector()
    scope=small_scope()
    page=connector.search(SearchQuery(serial_number="SYN-01A-RF-003"),scope)
    assert [item.original_id for item in page.items]==["syn-replacement-001"]
    assert not connector.search(SearchQuery(keyword="not in any fixture"),scope).items
    assert all(item.equipment_alias=="tool1a" and item.collection=="maintenance"
               for item in connector.search(SearchQuery(),scope).items)
    for query in (SearchQuery(equipment_aliases={"tool2a"}),SearchQuery(collections={"procedures"})):
        with pytest.raises(AccessDenied):
            connector.search(query,scope)
    with pytest.raises(AccessDenied):
        connector.get_document("syn-other-tool-001",scope)
    with pytest.raises(AccessDenied):
        connector.get_document("syn-procedure-001",scope)
    with pytest.raises(AccessDenied):
        connector.search(SearchQuery(),small_scope(source="lam-demo"))
    with pytest.raises(ValidationError):
        SourceScope(source_id="informs-demo",equipment_aliases={"*"},collections={"maintenance"})


def test_all_capabilities_are_explicit_and_unsupported_calls_fail():
    connector=fixture_connector()
    caps=connector.capabilities()
    assert caps.search and caps.retrieve_documents and caps.incremental_polling
    assert not caps.time_series and not caps.subscribe_updates and not caps.installation_records
    schema=connector.discover_schema(small_scope())
    assert schema["proprietary_schema_known"] is False
    assert all(document.synthetic is True for document in connector._documents.values())
    for call in (lambda:connector.list_records(SearchQuery(),small_scope()),
                 lambda:connector.get_time_series(SearchQuery(),small_scope()),
                 lambda:connector.get_installations(SearchQuery(),small_scope()),
                 lambda:connector.subscribe(small_scope())):
        with pytest.raises(CapabilityUnsupported):
            call()
    with pytest.raises(PermanentConnectorError):
        fixture_connector("https://not-an-approved-source.invalid")


def test_attachment_retrieval_requires_authorized_parent_and_attachment_scope():
    connector=fixture_connector()
    full=small_scope(collections={"maintenance","procedures"})
    attachment=connector.get_attachment("syn-replacement-001","syn-procedure-001",full)
    assert attachment.mime_type=="text/html"
    with pytest.raises(AccessDenied):
        connector.get_attachment("syn-replacement-001","syn-procedure-001",small_scope())
    with pytest.raises(AccessDenied):
        connector.get_attachment("syn-replacement-001","syn-other-tool-001",full)


def test_bounded_pagination_unchanged_versions_and_resume_filters():
    connector=fixture_connector()
    scope=small_scope()
    result=[]
    cursor=None
    while True:
        page=connector.search(SearchQuery(limit=2,cursor=cursor),scope)
        result.extend(page.items)
        cursor=page.next_cursor
        if cursor is None:
            break
    assert len({item.original_id for item in result})==len(result)==5
    known={item.original_id:metadata_version_token(item) for item in result}
    unchanged=connector.incremental(SearchQuery(known_versions=known),scope)
    assert not unchanged.items and unchanged.unchanged_count==5
    first=connector.search(SearchQuery(limit=1),scope)
    with pytest.raises(PermanentConnectorError,match="cursor"):
        connector.search(SearchQuery(limit=1,cursor=first.next_cursor,keyword="replacement"),scope)
    limited=connector.search(SearchQuery(start_at="2026-01-26T08:00:00Z",end_at="2026-01-26T10:00:00Z"),scope)
    assert [item.original_id for item in limited.items]==["syn-replacement-001","syn-installation-001"]


def test_changed_content_same_revision_reprocessed_and_stale_cursor_rejected():
    connector=fixture_connector()
    scope=small_scope()
    original=connector.get_document("syn-replacement-001",scope)
    changed=original.model_copy(update={"content":original.content+b"\nAdditional synthetic finding.\n"})
    docs=[changed if item.original_id==original.original_id else item for item in connector._documents.values()]
    new=SyntheticFileConnector(connector.config,docs)
    known={original.original_id:metadata_version_token(original.metadata())}
    found=new.search(SearchQuery(known_versions=known,serial_number="SYN-01A-RF-003"),scope)
    assert len(found.items)==1 and found.items[0].content_hash!=original.content_hash
    cursor=connector.search(SearchQuery(limit=1),scope).next_cursor
    with pytest.raises(PermanentConnectorError):
        new.search(SearchQuery(cursor=cursor,limit=1),scope)
    old=parse_document(original)
    reparsed=parse_document(original)
    assert old.content_hash==reparsed.content_hash and old.parser_version==reparsed.parser_version


def test_incremental_metadata_only_correction_forces_retrieval_and_invalidates_snapshot():
    connector=fixture_connector()
    scope=small_scope()
    discovered=connector.search(SearchQuery(),scope)
    known={item.original_id:metadata_version_token(item) for item in discovered.items}
    original=connector.get_document("syn-replacement-001",scope)
    corrected=original.model_copy(update={"effective_at":original.effective_at+timedelta(hours=1)})
    documents=[corrected if item.original_id==original.original_id else item for item in connector._documents.values()]
    changed_connector=SyntheticFileConnector(connector.config,documents)
    page=changed_connector.incremental(SearchQuery(known_versions=known),scope)
    assert [item.original_id for item in page.items]==[original.original_id]
    assert page.unchanged_count==len(discovered.items)-1
    retrieved=changed_connector.get_document(page.items[0].original_id,scope)
    assert retrieved.content==original.content and retrieved.revision==original.revision
    assert retrieved.effective_at!=original.effective_at
    cursor=connector.search(SearchQuery(limit=1),scope).next_cursor
    with pytest.raises(PermanentConnectorError,match="cursor"):
        changed_connector.incremental(SearchQuery(cursor=cursor,limit=1),scope)


def test_metadata_cache_token_normalizes_timezone_and_covers_full_envelope():
    metadata=fixture_connector().get_document("syn-replacement-001",small_scope()).metadata()
    raw=metadata.model_dump(mode="json")
    raw["effective_at"]="2026-01-25T18:00:00-06:00"
    assert metadata_version_token(DocumentMetadata.model_validate(raw))==metadata_version_token(metadata)
    for field,value in (("title","Corrected synthetic title"),("equipment_alias","tool2a"),
                        ("collection","procedures"),("filename","corrected.txt"),("attachment_ids",())):
        changed=metadata.model_copy(update={field:value})
        assert metadata_version_token(changed)!=metadata_version_token(metadata)


def test_connection_config_does_not_accept_credential_values():
    connector=fixture_connector()
    data=connector.config.model_dump()
    data["password"]="do-not-accept"
    with pytest.raises(ValidationError):
        ConnectionConfig.model_validate(data)
    with pytest.raises(ValidationError):
        connector.get_document("syn-replacement-001",small_scope()).content=b"modified"


def test_plain_text_exact_spans_and_human_review_gate():
    source=doc(explicit_claim())
    parsed=parse_document(source)
    proposal=extract_facts(parsed)[0]
    assert proposal.payload["component_serial"]=="SYN-NEW-003"
    assert proposal.verification=="unverified" and proposal.requires_review
    for references in proposal.evidence.values():
        for reference in references:
            assert parsed.text[reference.start:reference.end]==reference.quote
            assert source.content.decode()[reference.source_start:reference.source_end]==reference.quote
            assert reference.revision==source.revision and reference.content_hash==source.content_hash
    changed=doc(explicit_claim(),revision="2")
    with pytest.raises(ValueError,match="version"):
        validate_proposal_evidence(parse_document(changed),proposal)


def test_missing_identity_is_staged_with_explicit_blocking_issues():
    connector=fixture_connector()
    parsed=parse_document(connector.get_document("syn-missing-evidence-001",small_scope()))
    proposal=extract_facts(parsed)[0]
    assert "component_serial" not in proposal.payload and "installed_at" not in proposal.payload
    assert any("component_serial" in issue for issue in proposal.issues)
    assert proposal.requires_review


def test_conflicting_fields_are_not_last_value_wins():
    parsed=parse_document(doc(explicit_claim()+"\nComponent serial: SYN-DIFFERENT\n"))
    proposal=extract_facts(parsed)[0]
    assert "component_serial" not in proposal.payload
    assert any("conflicting extracted" in issue for issue in proposal.issues)


def test_html_is_text_only_and_records_raw_source_span():
    raw="<html><script>secretNetworkCall()</script><style>.hidden{}</style><p>Kind: installation</p><p>Tool alias: tool1a</p><img src='https://never-fetched.invalid/x'></html>"
    parsed=parse_document(doc(raw,"text/html"))
    assert parsed.status=="parsed"
    assert "secretNetworkCall" not in parsed.text and "never-fetched" not in parsed.text
    assert "Kind: installation" in parsed.text
    proposal=extract_facts(parsed)[0]
    reference=proposal.evidence["tool_alias"][0]
    assert raw[reference.source_start:reference.source_end]=="tool1a"


@pytest.mark.parametrize("identity_html,expected",[("SYN-A&amp;B","SYN-A&B"),("SYN-A<span>-B</span>","SYN-A-B")])
def test_html_inline_entities_preserve_complete_identity(identity_html,expected):
    raw=f"<p>Kind: installation</p><p>Component serial: {identity_html}</p>"
    parsed=parse_document(doc(raw,"text/html"))
    proposal=extract_facts(parsed)[0]
    assert proposal.payload["component_serial"]==expected
    reference=proposal.evidence["component_serial"][0]
    assert reference.quote==expected
    assert raw[reference.source_start:reference.source_end] in (identity_html,identity_html.removesuffix("</span>"))
    assert parsed.text[reference.start:reference.end]==expected


def test_json_nested_records_and_exact_scalar_locations():
    values=[{"kind":"installation","tool_alias":"tool1a","chamber_alias":"ch1a","position_alias":"rf1a",
             "component_serial":"SYN-JSON-003","installed_at":"2026-01-26T00:00:00Z"}]
    source=doc(json.dumps({"records":values},indent=2),"application/json")
    parsed=parse_document(source)
    proposal=extract_facts(parsed)[0]
    reference=proposal.evidence["component_serial"][0]
    assert reference.locator=="json:$.records[0].component_serial"
    assert json.loads(reference.quote)=="SYN-JSON-003"
    assert source.content.decode()[reference.source_start:reference.source_end]==reference.quote


def test_csv_preserves_row_evidence_and_rejects_malformed_columns():
    content="kind,tool_alias,chamber_alias,position_alias,component_serial,installed_at\ninstallation,tool1a,ch1a,rf1a,SYN-CSV-003,2026-01-26T00:00:00Z\n"
    parsed=parse_document(doc(content,"text/csv"))
    proposal=extract_facts(parsed)[0]
    reference=proposal.evidence["component_serial"][0]
    assert reference.row==2 and reference.quote=="SYN-CSV-003"
    assert content[reference.source_start:reference.source_end]==reference.quote
    assert parse_document(doc("a,b\nonly-one\n","text/csv")).status=="error"


def pdf_bytes(blank=False):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer=PdfWriter()
    page=writer.add_blank_page(width=612,height=792)
    if not blank:
        font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream=DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 720 Td (Kind: installation) Tj 0 -20 Td (Tool alias: tool1a) Tj ET")
        page[NameObject("/Contents")]=writer._add_object(stream)
    output=io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_page_spans_and_scanned_pdf_ocr_required():
    parsed=parse_document(doc(pdf_bytes(),"application/pdf"))
    assert parsed.status=="parsed"
    proposal=extract_facts(parsed)[0]
    assert proposal.evidence["tool_alias"][0].page==1
    scanned=parse_document(doc(pdf_bytes(blank=True),"application/pdf"))
    assert scanned.status=="ocr_required" and not extract_facts(scanned)
    assert "no external OCR" in scanned.issues[0]


def test_internal_ocr_is_explicit_unverified_and_bounded():
    class FakeInternalOCR:
        version="synthetic-ocr-test-v1"
        def extract(self,document,max_pages):
            return [OCRPage(page=1,text=explicit_claim(),confidence=0.8)]
    parsed=parse_document(doc(pdf_bytes(blank=True),"application/pdf"),ocr_provider=FakeInternalOCR())
    assert parsed.status=="parsed" and "ocr:" in parsed.parser_version
    assert "unverified" in parsed.issues[0]
    assert extract_facts(parsed)[0].requires_review


def test_low_ocr_confidence_is_retained_in_evidence_and_caps_claim_confidence():
    class LowConfidenceOCR:
        version="synthetic-low-confidence-ocr-v1"
        def extract(self,document,max_pages):
            return [OCRPage(page=1,text=explicit_claim(),confidence=0.1)]
    parsed=parse_document(doc(pdf_bytes(blank=True),"application/pdf"),ocr_provider=LowConfidenceOCR())
    proposal=extract_facts(parsed)[0]
    reference=proposal.evidence["component_serial"][0]
    assert reference.text_extraction_method=="ocr"
    assert reference.text_extraction_provider_version==LowConfidenceOCR.version
    assert reference.text_extraction_confidence==0.1
    assert proposal.confidence["component_serial"]==0.1
    assert proposal.verification=="unverified"
    raised=proposal.model_copy(update={"confidence":dict(proposal.confidence,component_serial=0.95)})
    with pytest.raises(ValueError,match="OCR text confidence"):
        validate_proposal_evidence(parsed,raised)


def test_xlsx_cells_formula_handling_and_archive_bounds():
    from openpyxl import Workbook
    book=Workbook()
    sheet=book.active
    sheet.title="Synthetic"
    sheet.append(["kind","tool_alias","chamber_alias","position_alias","component_serial","installed_at","findings"])
    sheet.append(["installation","tool1a","ch1a","rf1a","SYN-XLSX-003","2026-01-26T00:00:00Z","=1+1"])
    output=io.BytesIO()
    book.save(output)
    parsed=parse_document(doc(output.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    proposal=extract_facts(parsed)[0]
    assert proposal.payload["component_serial"]=="SYN-XLSX-003" and "findings" not in proposal.payload
    assert proposal.evidence["component_serial"][0].locator=="xlsx:Synthetic!E2"
    assert any("formula not evaluated" in issue for issue in parsed.issues)
    archive=io.BytesIO()
    with ZipFile(archive,"w",compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("oversized.xml","x"*100000)
    rejected=parse_document(doc(archive.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    assert rejected.status=="error" and "decompression limits" in rejected.issues[0]


def test_document_limits_unsupported_type_and_malformed_files():
    assert parse_document(doc("longer than 1 byte"),limits=ParserLimits(max_bytes=1)).status=="error"
    assert parse_document(doc("a\nb\nc"),limits=ParserLimits(max_rows=2)).status=="error"
    assert parse_document(doc(b"not a PDF","application/pdf")).status=="error"
    assert parse_document(doc("x","application/octet-stream")).status=="unsupported"


def test_internal_ai_requires_schema_evidence_exact_version_and_supported_values():
    parsed=parse_document(doc(explicit_claim()))
    initial=extract_facts(parsed)[0]
    class FakeAI:
        version="synthetic-internal-ai-v1"
        def __init__(self,draft): self.draft=draft
        def propose(self,document,output_schema):
            assert "properties" in output_schema
            return [self.draft]
    accepted=propose_with_internal_ai(parsed,FakeAI(initial.model_dump(mode="json")))[0]
    assert accepted.method=="internal_ai_proposal" and accepted.verification=="unverified"
    assert accepted.evidence["component_serial"][0].extraction_version=="synthetic-internal-ai-v1"
    missing=initial.model_dump(mode="json")
    missing["evidence"].pop("component_serial")
    with pytest.raises(ValueError,match="missing evidence"):
        propose_with_internal_ai(parsed,FakeAI(missing))
    invented=initial.model_dump(mode="json")
    invented["payload"]["component_serial"]="SYN-INVENTED-DOES-NOT-EXIST"
    with pytest.raises(ValueError,match="unsupported value"):
        propose_with_internal_ai(parsed,FakeAI(invented))
    altered=initial.model_dump(mode="json")
    altered["evidence"]["component_serial"][0]["quote"]="wrong quote"
    with pytest.raises(ValueError,match="quote"):
        propose_with_internal_ai(parsed,FakeAI(altered))
    wrong_location=initial.model_dump(mode="json")
    wrong_location["evidence"]["component_serial"][0]["page"]=999
    with pytest.raises(ValueError,match="source location"):
        propose_with_internal_ai(parsed,FakeAI(wrong_location))
    shortened=initial.model_dump(mode="json")
    shortened["payload"]["component_serial"]="SYN-NEW"
    with pytest.raises(ValueError,match="unsupported value"):
        propose_with_internal_ai(parsed,FakeAI(shortened))
    extra=initial.model_dump(mode="json")
    extra["evidence"]["forged_extra_field"]=extra["evidence"]["component_serial"]
    with pytest.raises(ValueError,match="exactly match"):
        propose_with_internal_ai(parsed,FakeAI(extra))
