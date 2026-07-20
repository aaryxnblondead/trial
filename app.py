from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from etl.aggregation import exposure_summary_by_jurisdiction, refresh_derived_exposure_measures


st.set_page_config(layout="wide", page_title="Civic-Tech Legislative Analysis Dashboard")


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def load_dataframe(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
    return pd.read_sql_query(query, connection, params=params)


st.title("Legislative Educational Stakes and Public Education Outcomes")
st.caption("Citation-first academic dashboard. Every displayed claim is backed by a source_document record or an explicit analysis run.")

catalog_default = Path("data/catalog.sqlite3")
catalog_path_text = st.sidebar.text_input("Catalog path", value=str(catalog_default))
catalog_path = Path(catalog_path_text)

if not catalog_path.exists():
    st.error(f"Catalog database not found at {catalog_path}. Run ingestion, matching, and analysis first.")
    st.stop()

connection = get_db_connection(catalog_path)

try:
    st.sidebar.subheader("Derived Exposure Bridge")
    bridge_exposure_name = st.sidebar.text_input("Exposure name", value="politically_linked_private_education_density")
    if st.sidebar.button("Refresh derived exposures"):
        bridge_rows = refresh_derived_exposure_measures(connection, exposure_name=bridge_exposure_name)
        st.sidebar.success(f"Derived {len(bridge_rows)} exposure rows.")

    st.header("Statistical Evidence")
    runs_df = load_dataframe(connection, "SELECT * FROM analysis_run ORDER BY created_at_utc DESC")
    if runs_df.empty:
        st.info("No analysis runs are stored yet.")
    else:
        selected_run_id = st.selectbox(
            "Select analysis run",
            options=runs_df["analysis_run_id"].tolist(),
            format_func=lambda run_id: runs_df.loc[runs_df["analysis_run_id"] == run_id, "analysis_name"].iloc[0],
        )
        run_row = runs_df.loc[runs_df["analysis_run_id"] == selected_run_id].iloc[0]
        st.write({
            "analysis_run_id": run_row["analysis_run_id"],
            "analysis_name": run_row["analysis_name"],
            "model_name": run_row["model_name"],
            "data_snapshot_hash": run_row["data_snapshot_hash"],
            "specification_hash": run_row["specification_hash"],
        })

        results_df = load_dataframe(
            connection,
            """
            SELECT coefficient_name, estimate, std_error, ci_lower, ci_upper, p_value, n_obs
            FROM regression_result
            WHERE analysis_run_id = ?
            ORDER BY coefficient_name
            """,
            (selected_run_id,),
        )
        st.dataframe(results_df, use_container_width=True)

        linked_docs_df = load_dataframe(
            connection,
            """
            SELECT DISTINCT sd.source_document_id, sd.source_system, sd.document_type, sd.source_url,
                            sd.jurisdiction, sd.retrieved_at_utc, sd.checksum_sha256, sd.artifact_path, sd.citation_locator
            FROM exposure_measure em
            INNER JOIN source_document sd ON sd.source_document_id = em.source_document_id
            WHERE em.exposure_name = ?
            ORDER BY sd.retrieved_at_utc DESC
            """,
            (run_row["exposure_definition"],),
        )
        st.subheader("Source documents behind the selected exposure definition")
        st.dataframe(linked_docs_df, use_container_width=True)

    st.header("Exposure Bridge")
    exposure_name = st.text_input("Exposure measure name", value="politically_linked_private_education_density")
    exposure_df = pd.DataFrame(exposure_summary_by_jurisdiction(connection, exposure_name))
    if exposure_df.empty:
        st.info("No derived exposure rows are stored yet.")
    else:
        st.dataframe(exposure_df, use_container_width=True)

    st.header("Entity Resolution Drill-Down")
    search_term = st.text_input("Search resolved link by name", value="").strip()
    if search_term:
        links_df = load_dataframe(
            connection,
            """
            SELECT resolved_entity_link_id, left_entity_name, right_entity_name, match_type, confidence_score,
                   resolution_source, source_document_id, citation_locator
            FROM resolved_entity_link
            WHERE left_entity_name LIKE ? OR right_entity_name LIKE ?
            ORDER BY confidence_score DESC, left_entity_name ASC
            """,
            (f"%{search_term}%", f"%{search_term}%"),
        )
        if links_df.empty:
            st.info("No resolved links matched that search.")
        else:
            for _, row in links_df.iterrows():
                with st.expander(f"{row['left_entity_name']} ↔ {row['right_entity_name']} ({row['confidence_score']:.2f})"):
                    st.write({
                        "resolved_entity_link_id": row["resolved_entity_link_id"],
                        "match_type": row["match_type"],
                        "resolution_source": row["resolution_source"],
                        "source_document_id": row["source_document_id"],
                        "citation_locator": row["citation_locator"],
                    })
                    doc_row = connection.execute(
                        "SELECT source_system, document_type, source_url, jurisdiction, artifact_path, checksum_sha256, retrieved_at_utc, license_note FROM source_document WHERE source_document_id = ?",
                        (row["source_document_id"],),
                    ).fetchone()
                    if doc_row:
                        st.json(dict(doc_row))

    st.header("Analysis Data Sources")
    source_doc_df = load_dataframe(
        connection,
        "SELECT source_document_id, source_system, source_name, document_type, source_url, jurisdiction, citation_locator, retrieved_at_utc FROM source_document ORDER BY retrieved_at_utc DESC",
    )
    st.dataframe(source_doc_df, use_container_width=True)
finally:
    connection.close()
