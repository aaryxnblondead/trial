from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence


_HARD_EMPTY = {"", "na", "n/a", "null", "none", "unknown"}
_PREFERRED_ARRAY_KEYS: Sequence[str] = (
    "records",
    "data",
    "items",
    "results",
    "entities",
    "people",
    "institutions",
    "metrics",
    "controls",
    "assertions",
)
_HONORIFIC_RE = re.compile(r"^(?:shri|sri|shrimati|smt|mr|mrs|ms|dr|prof|hon|hon'ble)\.?\s+", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z\s]+")
_MULTISPACE_RE = re.compile(r"\s+")


def canonical_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u00a0", " ")
    text = text.strip()
    if text.lower() in _HARD_EMPTY:
        return ""
    return text


def normalize_name(value: Any) -> str:
    text = canonical_text(value)
    if not text:
        return ""
    text = _HONORIFIC_RE.sub("", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _MULTISPACE_RE.sub(" ", text)
    return text.strip().lower()


def parse_payload(payload: bytes, content_type: str) -> Any:
    text = payload.decode("utf-8", errors="replace")
    content_type = content_type.lower()
    if "json" in content_type or text.lstrip().startswith(("{", "[")):
        return json.loads(text)
    if "csv" in content_type or "," in text.splitlines()[0] if text.splitlines() else False:
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)
    if "ndjson" in content_type or any(line.lstrip().startswith("{") for line in text.splitlines() if line.strip()):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return text


def _follow_record_path(data: Any, record_path: str | None) -> Any:
    if not record_path:
        return data
    current = data
    for part in record_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return data
    return current if current is not None else data


def extract_records(data: Any, record_path: str | None = None) -> List[Dict[str, Any]]:
    scoped = _follow_record_path(data, record_path)
    if isinstance(scoped, list):
        return [row for row in scoped if isinstance(row, dict)]
    if isinstance(scoped, dict):
        for key in _PREFERRED_ARRAY_KEYS:
            value = scoped.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [scoped]
    return []


def _coerce_float(value: Any) -> float | None:
    text = canonical_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_int(value: Any) -> int | None:
    text = canonical_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def classify_records(records: Iterable[Dict[str, Any]], source_document_id: str, citation_locator: str) -> Dict[str, List[Dict[str, Any]]]:
    classified: Dict[str, List[Dict[str, Any]]] = {
        "person": [],
        "institution": [],
        "quality_metric": [],
        "control_variable": [],
        "ownership_instrument": [],
        "assertion_fact": [],
    }
    for row in records:
        citation = canonical_text(row.get("citation_locator")) or citation_locator
        kind = canonical_text(row.get("kind") or row.get("entity_type") or row.get("record_type")).lower()

        person_name = row.get("person_name") or row.get("politician_name") or row.get("family_member_name") or row.get("director_name") or row.get("trustee_name") or row.get("name")
        institution_name = row.get("institution_name") or row.get("school_name") or row.get("college_name") or row.get("university_name") or row.get("coaching_name") or row.get("company_name")

        if kind in {"person", "politician", "family_member", "director", "trustee"} or person_name:
            classified["person"].append(
                {
                    "canonical_name": canonical_text(person_name),
                    "normalized_name": normalize_name(person_name),
                    "person_role": kind or canonical_text(row.get("person_role")) or "person",
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                }
            )

        if kind in {"institution", "school", "college", "university", "coaching_business", "education_company"} or institution_name:
            classified["institution"].append(
                {
                    "canonical_name": canonical_text(institution_name),
                    "normalized_name": normalize_name(institution_name),
                    "institution_type": canonical_text(row.get("institution_type")) or kind or "unknown",
                    "legal_form": canonical_text(row.get("legal_form")) or "unknown",
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                }
            )

        metric_name = canonical_text(row.get("metric_name"))
        metric_value = _coerce_float(row.get("metric_value"))
        if metric_name and metric_value is not None:
            classified["quality_metric"].append(
                {
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "metric_year": _coerce_int(row.get("metric_year")),
                    "unit": canonical_text(row.get("unit")),
                    "grade_band": canonical_text(row.get("grade_band")),
                    "demographic_scope": canonical_text(row.get("demographic_scope")),
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                }
            )

        variable_name = canonical_text(row.get("variable_name"))
        variable_value = _coerce_float(row.get("variable_value"))
        if variable_name and variable_value is not None:
            classified["control_variable"].append(
                {
                    "variable_name": variable_name,
                    "variable_value": variable_value,
                    "metric_year": _coerce_int(row.get("metric_year")),
                    "unit": canonical_text(row.get("unit")),
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                }
            )

        instrument_type = canonical_text(row.get("instrument_type"))
        if instrument_type:
            classified["ownership_instrument"].append(
                {
                    "instrument_type": instrument_type,
                    "instrument_identifier": canonical_text(row.get("instrument_identifier")),
                    "legal_entity_name": canonical_text(row.get("legal_entity_name")),
                    "effective_start_date": canonical_text(row.get("effective_start_date")),
                    "effective_end_date": canonical_text(row.get("effective_end_date")),
                    "registry_authority": canonical_text(row.get("registry_authority")),
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                }
            )

        predicate_type = canonical_text(row.get("predicate_type"))
        if predicate_type:
            classified["assertion_fact"].append(
                {
                    "subject_entity_type": canonical_text(row.get("subject_entity_type")),
                    "subject_entity_name": canonical_text(row.get("subject_entity_name")),
                    "predicate_type": predicate_type,
                    "object_entity_type": canonical_text(row.get("object_entity_type")),
                    "object_entity_name": canonical_text(row.get("object_entity_name")),
                    "numeric_value": _coerce_float(row.get("numeric_value")),
                    "text_value": canonical_text(row.get("text_value")),
                    "date_value": canonical_text(row.get("date_value")),
                    "source_document_id": source_document_id,
                    "citation_locator": citation,
                    "evidence_status": canonical_text(row.get("evidence_status")) or "documented_direct",
                    "confidence_score": _coerce_float(row.get("confidence_score")),
                }
            )

    return classified