from __future__ import annotations

import argparse
import json
from pathlib import Path

from etl.database import open_catalog
from etl.regression import RegressionSpecification, run_panel_regression


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 4 regression analysis.")
    parser.add_argument("--catalog", required=True, help="Path to the SQLite catalog produced by ingestion.")
    parser.add_argument("--analysis-name", required=True, help="Audit label for the analysis run.")
    parser.add_argument("--exposure-name", required=True, help="Exposure_name from exposure_measure.")
    parser.add_argument("--outcome-metric-name", required=True, help="Metric name from quality_metric.")
    parser.add_argument("--controls", nargs="*", default=[], help="Control variable names from control_variable.")
    args = parser.parse_args()

    catalog_path = Path(args.catalog).resolve()
    connection = open_catalog(catalog_path)
    try:
        outcome = run_panel_regression(
            connection,
            RegressionSpecification(
                analysis_name=args.analysis_name,
                exposure_name=args.exposure_name,
                outcome_metric_name=args.outcome_metric_name,
                control_variable_names=tuple(args.controls),
            ),
        )
    finally:
        connection.close()

    print(json.dumps(outcome.__dict__, ensure_ascii=True))


if __name__ == "__main__":
    main()