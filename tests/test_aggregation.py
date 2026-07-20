from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from etl.aggregation import refresh_derived_exposure_measures
from etl.database import initialize_catalog, open_catalog


class AggregationTests(unittest.TestCase):
    def test_refresh_derived_exposure_measures_groups_approved_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.sqlite3"
            connection = open_catalog(catalog_path)
            try:
                initialize_catalog(connection)
                source_document_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO source_document (
                        source_document_id, source_id, source_system, source_name, source_url, jurisdiction,
                        document_type, access_method, license_note, citation_locator, retrieved_at_utc,
                        checksum_sha256, bytes_size, artifact_path, content_type, parse_status, parse_error,
                        created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        source_document_id,
                        "sample",
                        "ECI",
                        "Sample source",
                        "https://example.org/source.json",
                        "IN",
                        "json_api",
                        "official_api",
                        "public",
                        "p1",
                        "2026-01-01T00:00:00+00:00",
                        "abc123",
                        10,
                        "/tmp/source.json",
                        "application/json",
                        "parsed",
                        None,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO resolved_entity_link (
                        resolved_entity_link_id, left_entity_type, left_entity_id, left_entity_name,
                        right_entity_type, right_entity_id, right_entity_name, match_type, confidence_score,
                        resolution_source, source_document_id, citation_locator, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        str(uuid4()),
                        "person",
                        None,
                        "A. K. Singh",
                        "institution",
                        None,
                        "A K Singh",
                        "deterministic_name",
                        1.0,
                        "auto_approved",
                        source_document_id,
                        "p1",
                    ),
                )
                connection.commit()

                derived_rows = refresh_derived_exposure_measures(connection)
                exposure_rows = connection.execute(
                    "SELECT jurisdiction_id, metric_year, exposure_value, evidence_status, citation_locator FROM exposure_measure"
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual(len(derived_rows), 1)
            self.assertEqual(len(exposure_rows), 1)
            self.assertEqual(exposure_rows[0]["metric_year"], 2026)
            self.assertEqual(exposure_rows[0]["exposure_value"], 1.0)
            self.assertEqual(exposure_rows[0]["evidence_status"], "derived_from_verified_links")
            self.assertIn("p1", exposure_rows[0]["citation_locator"])


if __name__ == "__main__":
    unittest.main()