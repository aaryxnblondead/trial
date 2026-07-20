from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from etl.database import (
    initialize_catalog,
    insert_classified_rows,
    insert_entity_match_candidate,
    insert_manifest_entry,
    insert_resolution_review_queue,
    insert_resolved_entity_link,
    insert_source_document,
    open_catalog,
)
from etl.models import SourceDefinition
from etl.matching import classify_match, generate_documentable_candidates, review_priority
from etl.normalization import classify_records, extract_records, parse_payload
from etl.sources import fetch_source_payload, validate_source_definition
from etl.storage import append_jsonl, write_artifact


def load_sources(config_path: Path) -> List[SourceDefinition]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    sources: List[SourceDefinition] = []
    for item in raw["sources"]:
        sources.append(
            SourceDefinition(
                source_id=item["source_id"],
                name=item["name"],
                source_system=item["source_system"],
                url=item["url"],
                jurisdiction=item["jurisdiction"],
                document_type=item["document_type"],
                license_note=item["license_note"],
                access_method=item.get("access_method", "official_api"),
                citation_locator=item.get("citation_locator"),
                record_path=item.get("record_path"),
                content_type_hint=item.get("content_type_hint"),
            )
        )
    return sources


def run_ingestion(config_path: Path, data_root: Path) -> List[Dict[str, Any]]:
    sources = load_sources(config_path)
    raw_root = data_root / "raw"
    manifests_root = data_root / "manifests"
    manifest_path = manifests_root / "ingestion_manifest.jsonl"
    catalog_path = data_root / "catalog.sqlite3"

    connection = open_catalog(catalog_path)
    initialize_catalog(connection)

    rows: List[Dict[str, Any]] = []
    try:
        for source in sources:
            validate_source_definition(source)
            payload, content_type = fetch_source_payload(source)
            extension = ".json" if "json" in content_type.lower() else ".bin"
            artifact_meta = write_artifact(raw_root=raw_root, source_id=source.source_id, payload=payload, extension=extension)

            source_row = {
                "source_id": source.source_id,
                "source_system": source.source_system,
                "source_name": source.name,
                "source_url": source.url,
                "jurisdiction": source.jurisdiction,
                "document_type": source.document_type,
                "access_method": source.access_method,
                "license_note": source.license_note,
                "citation_locator": source.citation_locator,
                "retrieved_at_utc": artifact_meta["retrieved_at_utc"],
                "checksum_sha256": artifact_meta["sha256"],
                "bytes_size": artifact_meta["bytes_size"],
                "artifact_path": artifact_meta["artifact_path"],
                "content_type": content_type,
                "parse_status": "parsed",
                "parse_error": None,
            }
            source_document_id = insert_source_document(connection, source_row)

            parsed_payload = parse_payload(payload, content_type or source.content_type_hint or "")
            records = extract_records(parsed_payload, record_path=source.record_path)
            classified = classify_records(records, source_document_id=source_document_id, citation_locator=source.citation_locator or source.source_id)
            inserted_counts = insert_classified_rows(connection, source_document_id=source_document_id, classified=classified)

            person_rows = connection.execute("SELECT person_id, canonical_name, normalized_name, person_role, source_document_id, citation_locator FROM person").fetchall()
            institution_rows = connection.execute("SELECT institution_id, canonical_name, normalized_name, source_document_id, citation_locator FROM institution").fetchall()
            candidates = generate_documentable_candidates(person_rows, institution_rows)
            approved_matches = 0
            review_matches = 0
            for candidate in candidates:
                review_status = classify_match(candidate)
                candidate_row = {
                    "left_entity_type": candidate.left_entity_type,
                    "left_entity_id": candidate.left_entity_id,
                    "left_entity_name": candidate.left_entity_name,
                    "right_entity_type": candidate.right_entity_type,
                    "right_entity_id": candidate.right_entity_id,
                    "right_entity_name": candidate.right_entity_name,
                    "match_type": candidate.match_type,
                    "confidence_score": candidate.confidence_score,
                    "match_reason": candidate.match_reason,
                    "review_status": review_status,
                    "source_document_id": candidate.source_document_id,
                    "citation_locator": candidate.citation_locator,
                }
                candidate_id = insert_entity_match_candidate(connection, candidate_row)
                if review_status == "approved":
                    insert_resolved_entity_link(
                        connection,
                        {
                            **candidate_row,
                            "resolution_source": "auto_approved",
                        },
                    )
                    approved_matches += 1
                else:
                    insert_resolution_review_queue(
                        connection,
                        {
                            "entity_match_candidate_id": candidate_id,
                            "left_entity_type": candidate.left_entity_type,
                            "left_entity_name": candidate.left_entity_name,
                            "right_entity_type": candidate.right_entity_type,
                            "right_entity_name": candidate.right_entity_name,
                            "confidence_score": candidate.confidence_score,
                            "match_reason": candidate.match_reason,
                            "review_priority": review_priority(candidate.confidence_score),
                            "source_document_id": candidate.source_document_id,
                            "citation_locator": candidate.citation_locator,
                        },
                    )
                    review_matches += 1

            connection.commit()

            row = {
                **source_row,
                "source_document_id": source_document_id,
                **artifact_meta,
                "inserted_persons": inserted_counts["person"],
                "inserted_institutions": inserted_counts["institution"],
                "inserted_metrics": inserted_counts["quality_metric"],
                "inserted_controls": inserted_counts["control_variable"],
                "inserted_assertions": inserted_counts["assertion_fact"],
                "inserted_candidate_matches": approved_matches + review_matches,
                "inserted_review_queue_items": review_matches,
                "inserted_resolved_links": approved_matches,
            }
            append_jsonl(manifest_path, row)
            insert_manifest_entry(connection, row)
            connection.commit()
            rows.append(row)
    finally:
        connection.close()

    return rows

