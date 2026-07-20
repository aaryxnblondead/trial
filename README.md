# Academic Legislative-Education Analysis

## Run order

1. Ingest sources with `py -3 run_ingestion.py --config ingest_sources.sample.json --data-root data`.
2. Run entity resolution through the ingestion pipeline, which stores approved links and review-queue items in `data/catalog.sqlite3`.
3. Refresh derived exposures from approved links with the dashboard bridge or by calling `etl.aggregation.refresh_derived_exposure_measures`.
4. Run regression analysis with `py -3 run_analysis.py --catalog data/catalog.sqlite3 --analysis-name ... --exposure-name politically_linked_private_education_density --outcome-metric-name ...`.
5. Launch the dashboard with `streamlit run app.py`.

## Provenance rule

Every displayed claim must trace to a `source_document` row or an `analysis_run` row in `catalog.sqlite3`. The dashboard is configured to show citations and source metadata alongside every surfaced result.
