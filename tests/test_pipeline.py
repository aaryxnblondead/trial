from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etl.pipeline import run_ingestion


class PipelineTests(unittest.TestCase):
    def test_run_ingestion_writes_artifact_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            config_path = tmp_path / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "source_id": "sample-source",
                                "name": "Sample",
                                "source_system": "ECI",
                                "url": "https://example.org/source.json",
                                "jurisdiction": "IN",
                                "document_type": "json_api",
                                "access_method": "official_api",
                                "license_note": "public",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            data_root = tmp_path / "data"

            payload = json.dumps(
                {
                    "records": [
                        {
                            "kind": "person",
                            "person_name": "Shri A. K. Singh",
                            "citation_locator": "p1",
                        }
                    ]
                }
            ).encode("utf-8")

            with patch("etl.pipeline.fetch_source_payload", return_value=(payload, "application/json")):
                rows = run_ingestion(config_path=config_path, data_root=data_root)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            artifact_path = Path(row["artifact_path"])
            self.assertTrue(artifact_path.exists())
            self.assertEqual(artifact_path.suffix, ".json")

            manifest_path = data_root / "manifests" / "ingestion_manifest.jsonl"
            self.assertTrue(manifest_path.exists())
            lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)

            catalog_path = data_root / "catalog.sqlite3"
            self.assertTrue(catalog_path.exists())
            connection = sqlite3.connect(catalog_path)
            try:
                source_document_count = connection.execute("SELECT COUNT(*) FROM source_document").fetchone()[0]
                person_row = connection.execute("SELECT canonical_name, normalized_name FROM person").fetchone()
            finally:
                connection.close()

            self.assertEqual(source_document_count, 1)
            self.assertIsNotNone(person_row)
            self.assertEqual(person_row[0], "Shri A. K. Singh")
            self.assertEqual(person_row[1], "a k singh")


if __name__ == "__main__":
    unittest.main()
