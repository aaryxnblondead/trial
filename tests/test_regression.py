from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from etl.database import initialize_catalog, insert_exposure_measure, open_catalog
from etl.regression import RegressionSpecification, run_panel_regression


def _seed_panel(connection: sqlite3.Connection, exposure_values: list[tuple[str, int, float]], outcome_rule) -> None:
    connection.executescript(
        """
        DELETE FROM exposure_measure;
        DELETE FROM quality_metric;
        DELETE FROM control_variable;
        DELETE FROM analysis_run;
        DELETE FROM regression_result;
        """
    )
    source_document_id = str(uuid4())
    for jurisdiction_id, metric_year, exposure_value in exposure_values:
        insert_exposure_measure(
            connection,
            {
                "jurisdiction_id": jurisdiction_id,
                "metric_year": metric_year,
                "exposure_name": "politically_linked_private_education_density",
                "exposure_value": exposure_value,
                "unit": "count_per_jurisdiction_year",
                "source_document_id": source_document_id,
                "citation_locator": f"{jurisdiction_id}-{metric_year}",
                "evidence_status": "documented_direct",
            },
        )
        control_value = 100.0 + metric_year * 0.25 + (0.5 if jurisdiction_id == "state_b" else 0.0)
        connection.execute(
            """
            INSERT INTO control_variable (
                control_variable_id, jurisdiction_id, metric_year, variable_name, variable_value, unit,
                source_document_id, citation_locator, evidence_status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                str(uuid4()),
                jurisdiction_id,
                metric_year,
                "per_capita_income",
                control_value,
                "index",
                source_document_id,
                f"{jurisdiction_id}-{metric_year}",
                "documented_direct",
            ),
        )
        outcome_value = outcome_rule(jurisdiction_id, metric_year, exposure_value, control_value)
        connection.execute(
            """
            INSERT INTO quality_metric (
                quality_metric_id, jurisdiction_id, metric_year, metric_name, metric_value, unit,
                grade_band, demographic_scope, source_document_id, citation_locator, evidence_status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                str(uuid4()),
                jurisdiction_id,
                metric_year,
                "public_school_learning_outcome_gap",
                outcome_value,
                "score",
                "grade_5",
                "district",
                source_document_id,
                f"{jurisdiction_id}-{metric_year}",
                "documented_direct",
            ),
        )
    connection.commit()


class RegressionTests(unittest.TestCase):
    def test_run_panel_regression_stores_positive_effect_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.sqlite3"
            connection = open_catalog(catalog_path)
            try:
                initialize_catalog(connection)
                _seed_panel(
                    connection,
                    [
                        ("state_a", 2021, 1.0),
                        ("state_a", 2022, 3.0),
                        ("state_a", 2023, 2.0),
                        ("state_b", 2021, 2.0),
                        ("state_b", 2022, 1.0),
                        ("state_b", 2023, 4.0),
                    ],
                    lambda jurisdiction_id, metric_year, exposure_value, control_value: 15.0
                    + 2.5 * exposure_value
                    + 0.1 * control_value
                    + (1.0 if jurisdiction_id == "state_b" else 0.0)
                    + 0.2 * (metric_year - 2021),
                )
                outcome = run_panel_regression(
                    connection,
                    RegressionSpecification(
                        analysis_name="phase4_positive_test",
                        exposure_name="politically_linked_private_education_density",
                        outcome_metric_name="public_school_learning_outcome_gap",
                        control_variable_names=("per_capita_income",),
                    ),
                )

                analysis_run_count = connection.execute("SELECT COUNT(*) FROM analysis_run").fetchone()[0]
                result_count = connection.execute("SELECT COUNT(*) FROM regression_result").fetchone()[0]
                exposure_row = connection.execute(
                    "SELECT estimate, ci_lower, ci_upper FROM regression_result WHERE coefficient_name = 'exposure_value'"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(analysis_run_count, 1)
            self.assertGreater(result_count, 0)
            self.assertIsNotNone(exposure_row)
            self.assertGreater(outcome.exposure_coefficient, 0.0)
            self.assertTrue(outcome.supports_h1)
            self.assertLess(exposure_row[1], exposure_row[2])

    def test_run_panel_regression_reports_null_when_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "catalog.sqlite3"
            connection = open_catalog(catalog_path)
            try:
                initialize_catalog(connection)
                _seed_panel(
                    connection,
                    [
                        ("state_a", 2021, 1.0),
                        ("state_a", 2022, 3.0),
                        ("state_a", 2023, 2.0),
                        ("state_b", 2021, 2.0),
                        ("state_b", 2022, 1.0),
                        ("state_b", 2023, 4.0),
                    ],
                    lambda jurisdiction_id, metric_year, exposure_value, control_value: 25.0 + 0.1 * control_value + (0.5 if jurisdiction_id == "state_b" else 0.0),
                )
                outcome = run_panel_regression(
                    connection,
                    RegressionSpecification(
                        analysis_name="phase4_null_test",
                        exposure_name="politically_linked_private_education_density",
                        outcome_metric_name="public_school_learning_outcome_gap",
                        control_variable_names=("per_capita_income",),
                    ),
                )
            finally:
                connection.close()

            self.assertFalse(outcome.supports_h1)
            self.assertLessEqual(abs(outcome.exposure_coefficient), 1.0)
            self.assertIn("No statistically significant positive association", outcome.note)


if __name__ == "__main__":
    unittest.main()