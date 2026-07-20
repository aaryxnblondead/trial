from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def open_catalog(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_catalog(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS source_document (
            source_document_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_system TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            jurisdiction TEXT NOT NULL,
            document_type TEXT NOT NULL,
            access_method TEXT NOT NULL,
            license_note TEXT NOT NULL,
            citation_locator TEXT,
            retrieved_at_utc TEXT NOT NULL,
            checksum_sha256 TEXT NOT NULL,
            bytes_size INTEGER NOT NULL,
            artifact_path TEXT NOT NULL,
            content_type TEXT NOT NULL,
            parse_status TEXT NOT NULL,
            parse_error TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jurisdiction (
            jurisdiction_id TEXT PRIMARY KEY,
            level TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_jurisdiction_id TEXT,
            official_code TEXT,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS person (
            person_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            person_role TEXT NOT NULL,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS institution (
            institution_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            institution_type TEXT NOT NULL,
            legal_form TEXT NOT NULL,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ownership_instrument (
            ownership_instrument_id TEXT PRIMARY KEY,
            instrument_type TEXT NOT NULL,
            instrument_identifier TEXT,
            legal_entity_name TEXT,
            effective_start_date TEXT,
            effective_end_date TEXT,
            registry_authority TEXT,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quality_metric (
            quality_metric_id TEXT PRIMARY KEY,
            jurisdiction_id TEXT,
            metric_year INTEGER,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            unit TEXT,
            grade_band TEXT,
            demographic_scope TEXT,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS control_variable (
            control_variable_id TEXT PRIMARY KEY,
            jurisdiction_id TEXT,
            metric_year INTEGER,
            variable_name TEXT NOT NULL,
            variable_value REAL NOT NULL,
            unit TEXT,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assertion_fact (
            assertion_fact_id TEXT PRIMARY KEY,
            subject_entity_type TEXT NOT NULL,
            subject_entity_name TEXT,
            predicate_type TEXT NOT NULL,
            object_entity_type TEXT,
            object_entity_name TEXT,
            numeric_value REAL,
            text_value TEXT,
            date_value TEXT,
            source_document_id TEXT NOT NULL,
            citation_locator TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            confidence_score REAL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ingestion_manifest (
            ingestion_manifest_id TEXT PRIMARY KEY,
            source_document_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_system TEXT NOT NULL,
            source_url TEXT NOT NULL,
            retrieved_at_utc TEXT NOT NULL,
            checksum_sha256 TEXT NOT NULL,
            bytes_size INTEGER NOT NULL,
            artifact_path TEXT NOT NULL,
            content_type TEXT NOT NULL,
            parse_status TEXT NOT NULL,
            inserted_persons INTEGER NOT NULL,
            inserted_institutions INTEGER NOT NULL,
            inserted_metrics INTEGER NOT NULL,
            inserted_controls INTEGER NOT NULL,
            inserted_assertions INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        """
    )
    connection.commit()


def insert_source_document(connection: sqlite3.Connection, row: Mapping[str, Any]) -> str:
    source_document_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO source_document (
            source_document_id, source_id, source_system, source_name, source_url, jurisdiction,
            document_type, access_method, license_note, citation_locator, retrieved_at_utc,
            checksum_sha256, bytes_size, artifact_path, content_type, parse_status, parse_error,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_document_id,
            row["source_id"],
            row["source_system"],
            row["source_name"],
            row["source_url"],
            row["jurisdiction"],
            row["document_type"],
            row["access_method"],
            row["license_note"],
            row.get("citation_locator"),
            row["retrieved_at_utc"],
            row["checksum_sha256"],
            row["bytes_size"],
            row["artifact_path"],
            row["content_type"],
            row["parse_status"],
            row.get("parse_error"),
            utc_now_iso(),
        ),
    )
    return source_document_id


def _insert_rows(connection: sqlite3.Connection, table: str, id_column: str, rows: Iterable[Mapping[str, Any]], columns: list[str]) -> int:
    inserted = 0
    for row in rows:
        record_id = str(uuid4())
        values = [record_id]
        for column in columns:
            values.append(row.get(column))
        values.append(utc_now_iso())
        placeholders = ", ".join(["?"] * len(values))
        connection.execute(
            f"INSERT INTO {table} ({id_column}, {', '.join(columns)}, created_at_utc) VALUES ({placeholders})",
            values,
        )
        inserted += 1
    return inserted


def insert_classified_rows(connection: sqlite3.Connection, source_document_id: str, classified: Dict[str, list[Dict[str, Any]]]) -> Dict[str, int]:
    counts = {
        "person": 0,
        "institution": 0,
        "quality_metric": 0,
        "control_variable": 0,
        "ownership_instrument": 0,
        "assertion_fact": 0,
    }
    if classified.get("person"):
        counts["person"] = _insert_rows(
            connection,
            "person",
            "person_id",
            classified["person"],
            ["canonical_name", "normalized_name", "person_role", "source_document_id", "citation_locator", "evidence_status"],
        )
    if classified.get("institution"):
        counts["institution"] = _insert_rows(
            connection,
            "institution",
            "institution_id",
            classified["institution"],
            ["canonical_name", "normalized_name", "institution_type", "legal_form", "source_document_id", "citation_locator", "evidence_status"],
        )
    if classified.get("quality_metric"):
        counts["quality_metric"] = _insert_rows(
            connection,
            "quality_metric",
            "quality_metric_id",
            classified["quality_metric"],
            ["jurisdiction_id", "metric_year", "metric_name", "metric_value", "unit", "grade_band", "demographic_scope", "source_document_id", "citation_locator", "evidence_status"],
        )
    if classified.get("control_variable"):
        counts["control_variable"] = _insert_rows(
            connection,
            "control_variable",
            "control_variable_id",
            classified["control_variable"],
            ["jurisdiction_id", "metric_year", "variable_name", "variable_value", "unit", "source_document_id", "citation_locator", "evidence_status"],
        )
    if classified.get("ownership_instrument"):
        counts["ownership_instrument"] = _insert_rows(
            connection,
            "ownership_instrument",
            "ownership_instrument_id",
            classified["ownership_instrument"],
            ["instrument_type", "instrument_identifier", "legal_entity_name", "effective_start_date", "effective_end_date", "registry_authority", "source_document_id", "citation_locator", "evidence_status"],
        )
    if classified.get("assertion_fact"):
        counts["assertion_fact"] = _insert_rows(
            connection,
            "assertion_fact",
            "assertion_fact_id",
            classified["assertion_fact"],
            ["subject_entity_type", "subject_entity_name", "predicate_type", "object_entity_type", "object_entity_name", "numeric_value", "text_value", "date_value", "source_document_id", "citation_locator", "evidence_status", "confidence_score"],
        )
    return counts


def insert_manifest_entry(connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO ingestion_manifest (
            ingestion_manifest_id, source_document_id, source_id, source_name, source_system, source_url,
            retrieved_at_utc, checksum_sha256, bytes_size, artifact_path, content_type, parse_status,
            inserted_persons, inserted_institutions, inserted_metrics, inserted_controls, inserted_assertions,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            row["source_document_id"],
            row["source_id"],
            row["source_name"],
            row["source_system"],
            row["source_url"],
            row["retrieved_at_utc"],
            row["checksum_sha256"],
            row["bytes_size"],
            row["artifact_path"],
            row["content_type"],
            row["parse_status"],
            row["inserted_persons"],
            row["inserted_institutions"],
            row["inserted_metrics"],
            row["inserted_controls"],
            row["inserted_assertions"],
            utc_now_iso(),
        ),
    )