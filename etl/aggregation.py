from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from typing import Sequence


@dataclass(frozen=True)
class ExposureGroup:
    jurisdiction_id: str | None
    metric_year: int
    exposure_name: str
    exposure_value: float
    unit: str
    source_document_id: str
    citation_locator: str
    evidence_status: str = "derived_from_verified_links"


def refresh_derived_exposure_measures(connection, exposure_name: str = "politically_linked_private_education_density") -> list[ExposureGroup]:
    approval_rows = connection.execute(
        """
        SELECT
            rel.resolved_entity_link_id,
            rel.source_document_id,
            rel.citation_locator,
            sd.jurisdiction,
            sd.retrieved_at_utc,
            rel.left_entity_name,
            rel.right_entity_name
        FROM resolved_entity_link rel
        INNER JOIN source_document sd ON sd.source_document_id = rel.source_document_id
        WHERE rel.resolution_source = 'auto_approved'
        """
    ).fetchall()

    connection.execute(
        "DELETE FROM exposure_measure WHERE exposure_name = ? AND evidence_status = 'derived_from_verified_links'",
        (exposure_name,),
    )

    grouped: dict[tuple[str | None, int], list] = {}
    for row in approval_rows:
        retrieved_year = int(str(row["retrieved_at_utc"])[:4])
        jurisdiction_id = row["jurisdiction"]
        grouped.setdefault((jurisdiction_id, retrieved_year), []).append(row)

    derived_rows: list[ExposureGroup] = []
    for (jurisdiction_id, metric_year), rows in grouped.items():
        source_document_id = rows[0]["source_document_id"]
        citation_locator = "; ".join(sorted({str(row["citation_locator"]) for row in rows if row["citation_locator"]}))
        exposure_value = float(len(rows))
        unit = "approved_links_per_jurisdiction_year"
        group = ExposureGroup(
            jurisdiction_id=jurisdiction_id,
            metric_year=metric_year,
            exposure_name=exposure_name,
            exposure_value=exposure_value,
            unit=unit,
            source_document_id=source_document_id,
            citation_locator=citation_locator or rows[0]["citation_locator"] or source_document_id,
        )
        derived_rows.append(group)
        connection.execute(
            """
            INSERT INTO exposure_measure (
                exposure_measure_id, jurisdiction_id, metric_year, exposure_name, exposure_value, unit,
                source_document_id, citation_locator, evidence_status, created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
            """,
            (
                uuid4().hex,
                group.jurisdiction_id,
                group.metric_year,
                group.exposure_name,
                group.exposure_value,
                group.unit,
                group.source_document_id,
                group.citation_locator,
                group.evidence_status,
            ),
        )

    connection.commit()
    return derived_rows


def exposure_summary_by_jurisdiction(connection, exposure_name: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT jurisdiction_id, metric_year, exposure_value, unit, source_document_id, citation_locator, evidence_status
        FROM exposure_measure
        WHERE exposure_name = ?
        ORDER BY jurisdiction_id, metric_year
        """,
        (exposure_name,),
    ).fetchall()
    return [dict(row) for row in rows]
