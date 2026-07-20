from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from etl.database import insert_analysis_run, insert_regression_result, utc_now_iso


@dataclass(frozen=True)
class RegressionSpecification:
    analysis_name: str
    exposure_name: str
    outcome_metric_name: str
    control_variable_names: Sequence[str]


@dataclass(frozen=True)
class RegressionOutcome:
    analysis_run_id: str
    model_name: str
    n_obs: int
    exposure_coefficient: float
    exposure_std_error: float
    exposure_ci_lower: float
    exposure_ci_upper: float
    exposure_p_value: float | None
    supports_h1: bool
    note: str


def _snapshot_hash(frame: pd.DataFrame, columns: Sequence[str]) -> str:
    digest = hashlib.sha256()
    csv_text = frame.loc[:, list(columns)].sort_values(list(columns)).to_csv(index=False)
    digest.update(csv_text.encode("utf-8"))
    return digest.hexdigest()


def _load_panel_frame(connection, exposure_name: str, outcome_metric_name: str, control_variable_names: Sequence[str]) -> pd.DataFrame:
    exposure_frame = pd.read_sql_query(
        """
        SELECT jurisdiction_id, metric_year, exposure_value
        FROM exposure_measure
        WHERE exposure_name = ?
        """,
        connection,
        params=[exposure_name],
    )
    outcome_frame = pd.read_sql_query(
        """
        SELECT jurisdiction_id, metric_year, metric_value AS outcome_value
        FROM quality_metric
        WHERE metric_name = ?
        """,
        connection,
        params=[outcome_metric_name],
    )

    frame = exposure_frame.merge(outcome_frame, on=["jurisdiction_id", "metric_year"], how="inner")
    for control_name in control_variable_names:
        control_frame = pd.read_sql_query(
            """
            SELECT jurisdiction_id, metric_year, variable_value
            FROM control_variable
            WHERE variable_name = ?
            """,
            connection,
            params=[control_name],
        ).rename(columns={"variable_value": control_name})
        frame = frame.merge(control_frame, on=["jurisdiction_id", "metric_year"], how="left")

    return frame.dropna(subset=["exposure_value", "outcome_value"])


def _build_formula(control_variable_names: Sequence[str], frame: pd.DataFrame) -> str:
    terms = ["exposure_value"]
    terms.extend(control_variable_names)
    if frame["jurisdiction_id"].nunique() > 1:
        terms.append("C(jurisdiction_id)")
    if frame["metric_year"].nunique() > 1:
        terms.append("C(metric_year)")
    return "outcome_value ~ " + " + ".join(terms)


def run_panel_regression(connection, specification: RegressionSpecification) -> RegressionOutcome:
    frame = _load_panel_frame(
        connection,
        exposure_name=specification.exposure_name,
        outcome_metric_name=specification.outcome_metric_name,
        control_variable_names=specification.control_variable_names,
    )
    if frame.empty:
        raise ValueError("No overlapping exposure and outcome rows were found for the requested specification.")

    snapshot_columns = ["jurisdiction_id", "metric_year", "exposure_value", "outcome_value", *specification.control_variable_names]
    snapshot_hash = _snapshot_hash(frame, snapshot_columns)
    controls_definition = ", ".join(specification.control_variable_names) if specification.control_variable_names else "none"

    analysis_run_id = insert_analysis_run(
        connection,
        {
            "analysis_name": specification.analysis_name,
            "model_name": "statsmodels_ols_fixed_effects",
            "data_snapshot_hash": snapshot_hash,
            "specification_hash": hashlib.sha256(
                "|".join(
                    [
                        specification.analysis_name,
                        specification.exposure_name,
                        specification.outcome_metric_name,
                        controls_definition,
                    ]
                ).encode("utf-8")
            ).hexdigest(),
            "code_version_hash": hashlib.sha256(b"etl.regression.v1").hexdigest(),
            "outcome_definition": specification.outcome_metric_name,
            "exposure_definition": specification.exposure_name,
            "controls_definition": controls_definition,
        },
    )

    formula = _build_formula(specification.control_variable_names, frame)
    model = smf.ols(formula=formula, data=frame)
    try:
        fitted = model.fit(cov_type="cluster", cov_kwds={"groups": frame["jurisdiction_id"]}) if frame["jurisdiction_id"].nunique() > 1 else model.fit(cov_type="HC1")
    except Exception:
        fallback_terms = ["exposure_value", *specification.control_variable_names]
        fallback_formula = "outcome_value ~ " + " + ".join(fallback_terms)
        model = smf.ols(formula=fallback_formula, data=frame)
        fitted = model.fit(cov_type="HC1")
        formula = fallback_formula

    confidence_intervals = fitted.conf_int(alpha=0.05)
    params = fitted.params
    standard_errors = fitted.bse
    pvalues = fitted.pvalues
    for coefficient_name in params.index:
        insert_regression_result(
            connection,
            {
                "analysis_run_id": analysis_run_id,
                "coefficient_name": coefficient_name,
                "estimate": float(params[coefficient_name]),
                "std_error": float(standard_errors[coefficient_name]),
                "ci_lower": float(confidence_intervals.loc[coefficient_name, 0]),
                "ci_upper": float(confidence_intervals.loc[coefficient_name, 1]),
                "p_value": float(pvalues[coefficient_name]) if coefficient_name in pvalues else None,
                "n_obs": int(fitted.nobs),
            },
        )

    exposure_estimate = float(params["exposure_value"])
    exposure_std_error = float(standard_errors["exposure_value"])
    exposure_ci_lower = float(confidence_intervals.loc["exposure_value", 0])
    exposure_ci_upper = float(confidence_intervals.loc["exposure_value", 1])
    exposure_p_value = float(pvalues["exposure_value"]) if "exposure_value" in pvalues else None
    supports_h1 = exposure_p_value is not None and exposure_p_value < 0.05 and exposure_estimate > 0
    note = (
        f"Observed positive association consistent with H1 using formula: {formula}."
        if supports_h1
        else f"No statistically significant positive association observed using formula: {formula}; treat as a null or weak-association result."
    )

    connection.commit()
    return RegressionOutcome(
        analysis_run_id=analysis_run_id,
        model_name="statsmodels_ols_fixed_effects",
        n_obs=int(fitted.nobs),
        exposure_coefficient=exposure_estimate,
        exposure_std_error=exposure_std_error,
        exposure_ci_lower=exposure_ci_lower,
        exposure_ci_upper=exposure_ci_upper,
        exposure_p_value=exposure_p_value,
        supports_h1=supports_h1,
        note=note,
    )
