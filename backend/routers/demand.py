
"""
backend/routers/demand.py
-------------------------
Zone-Level Resource Demand Prediction (Module E),
Dynamic Demand Updates (Module C), and Scenario Simulation (Module D).

Demand predictions and simulation use the existing ML artifacts.
Inventory is read-only in this module.
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any, Tuple

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status

from backend.services.dynamic_update import (
    DynamicUpdatePayload,
    apply_dynamic_update,
)
from backend.services.scenario import (
    SimulationBatchRequest,
    run_scenario_simulation,
)
from backend.services.vulnerability import (
    adjust_demand_for_vulnerability,
    validate_demographic_shares,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demand", tags=["Demand Prediction"])

TARGET_RESOURCES = [
    "food_packets",
    "water_litres",
    "medical_kits",
    "shelter_capacity_persons",
]

RESOURCE_UNITS = {
    "food_packets": "packets",
    "water_litres": "litres",
    "medical_kits": "kits",
    "shelter_capacity_persons": "people",
}

SEVERITY_SCALE_MAPPING = {
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}

# These fallback zones are for demonstration/testing only.
# They are not database records or verified real-world incident data.
FALLBACK_ZONES = [
    {
        "id": 1,
        "name": "Zone Alpha (Central Coastal)",
        "disaster_type": "flood",
        "severity": "Medium",
        "population": 2400,
        "affected_buildings": 280,
        "data_status": "demo_fallback",
    },
    {
        "id": 2,
        "name": "Zone Beta (North Urban Sector)",
        "disaster_type": "earthquake",
        "severity": "High",
        "population": 12500,
        "affected_buildings": 1400,
        "data_status": "demo_fallback",
    },
]

_MODEL_CACHE: Optional[Dict[str, Any]] = None
_QUANTILES_CACHE: Optional[Dict[str, float]] = None
_METRICS_CACHE: Optional[Dict[str, Any]] = None


def get_ml_artifacts() -> Tuple[
    Dict[str, Any], Dict[str, float], Dict[str, Any]
]:
    """Load and cache ML models, conformal quantiles, and metrics."""

    global _MODEL_CACHE, _QUANTILES_CACHE, _METRICS_CACHE

    if (
        _MODEL_CACHE is not None
        and _QUANTILES_CACHE is not None
        and _METRICS_CACHE is not None
    ):
        return _MODEL_CACHE, _QUANTILES_CACHE, _METRICS_CACHE

    backend_dir = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    artifacts_dir = os.path.join(backend_dir, "ml", "artifacts")

    if not os.path.isdir(artifacts_dir):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML artifacts directory not found. Train models first.",
        )

    metrics_path = os.path.join(artifacts_dir, "metrics.json")

    if not os.path.isfile(metrics_path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="metrics.json is missing. Train models first.",
        )

    try:
        with open(metrics_path, "r", encoding="utf-8") as file:
            metrics_data = json.load(file)

        models = {}
        quantiles = {}

        for target in TARGET_RESOURCES:
            model_path = os.path.join(
                artifacts_dir, f"model_{target}.joblib"
            )
            quantile_path = os.path.join(
                artifacts_dir,
                f"conformal_quantile_{target}.joblib",
            )

            if not os.path.isfile(model_path):
                raise FileNotFoundError(
                    f"Missing model artifact: {model_path}"
                )

            if not os.path.isfile(quantile_path):
                raise FileNotFoundError(
                    f"Missing quantile artifact: {quantile_path}"
                )

            models[target] = joblib.load(model_path)
            quantile_obj = joblib.load(quantile_path)
            quantiles[target] = float(quantile_obj["q_hat"])

        _MODEL_CACHE = models
        _QUANTILES_CACHE = quantiles
        _METRICS_CACHE = metrics_data

        return models, quantiles, metrics_data

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load ML artifacts")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to load ML model artifacts: {exc}",
        ) from exc


def get_db_connection():
    """Get a database connection from the backend application."""

    try:
        from backend.main import get_connection
        return get_connection()
    except Exception as exc:
        logger.exception("Database connection could not be created")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is currently unavailable.",
        ) from exc


def fetch_available_inventory_stock(conn) -> Dict[str, Optional[int]]:
    """Read aggregated stock without modifying inventory."""

    stock_by_type = {
        "food_packets": 0,
        "water_litres": 0,
        "medical_kits": 0,
        "shelter_capacity_persons": None,
    }

    try:
        cursor = conn.execute(
            """
            SELECT resource_type, SUM(quantity) AS total_qty
            FROM resource_inventory
            GROUP BY resource_type
            """
        )

        for row in cursor.fetchall():
            resource_type = row.get("resource_type")
            quantity = int(row.get("total_qty") or 0)

            if resource_type == "food_packets":
                stock_by_type["food_packets"] += quantity
            elif resource_type in ("water_liters", "water_litres"):
                stock_by_type["water_litres"] += quantity
            elif resource_type == "medical_kits":
                stock_by_type["medical_kits"] += quantity

    except Exception as exc:
        logger.warning(
            "Could not read resource_inventory: %s", exc
        )

        # Try the alternative inventory table if available.
        try:
            cursor = conn.execute(
                "SELECT name, quantity FROM resources"
            )

            for row in cursor.fetchall():
                name = str(row.get("name") or "").lower()
                quantity = int(row.get("quantity") or 0)

                if "food" in name:
                    stock_by_type["food_packets"] += quantity
                elif "water" in name:
                    stock_by_type["water_litres"] += quantity
                elif "medical" in name:
                    stock_by_type["medical_kits"] += quantity

        except Exception as fallback_exc:
            logger.warning(
                "Could not read alternative inventory table: %s",
                fallback_exc,
            )

    return stock_by_type


def _get_zone_rows(
    conn,
    zone_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch database zones.

    When the database contains no matching zones, the caller may use
    the clearly labelled demo fallback zones.
    """

    sql = """
        SELECT *
        FROM disaster_zones
    """
    params = []

    if zone_id is not None:
        sql += " WHERE id = %s"
        params.append(zone_id)

    sql += " ORDER BY id ASC"

    cursor = conn.execute(sql, params)
    return [dict(row) for row in cursor.fetchall()]


def _get_zone_by_id(
    conn,
    zone_id: int,
) -> Dict[str, Any]:
    """
    Find a zone in the database first, then in the same fallback data
    used by GET /zones.

    Fallback data is used only when the requested database row is absent.
    """

    try:
        cursor = conn.execute(
            "SELECT * FROM disaster_zones WHERE id = %s",
            [zone_id],
        )
        row = cursor.fetchone()

        if row:
            return dict(row)

    except Exception as exc:
        logger.warning(
            "Database zone lookup failed for ID %s: %s",
            zone_id,
            exc,
        )

    for zone in FALLBACK_ZONES:
        if zone["id"] == zone_id:
            return dict(zone)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Zone id {zone_id} not found",
    )


def _zone_demographics(
    elderly_share: Optional[float],
    children_share: Optional[float],
    medically_dependent_share: Optional[float],
) -> None:
    try:
        validate_demographic_shares(
            elderly_share,
            children_share,
            medically_dependent_share,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/zones",
    summary="Zone-Level Resource Demand Prediction (Module E)",
)
def get_zone_demand_predictions(
    zone_id: Optional[int] = Query(None),
    disaster_type: Optional[str] = Query(None),
    elderly_share: Optional[float] = Query(None, ge=0.0, le=1.0),
    children_share: Optional[float] = Query(None, ge=0.0, le=1.0),
    medically_dependent_share: Optional[float] = Query(
        None, ge=0.0, le=1.0
    ),
):
    """Return resource-demand predictions and inventory comparisons."""

    _zone_demographics(
        elderly_share,
        children_share,
        medically_dependent_share,
    )

    models, quantiles, metrics_meta = get_ml_artifacts()

    zones = []
    inventory_stock = {
        "food_packets": 0,
        "water_litres": 0,
        "medical_kits": 0,
        "shelter_capacity_persons": None,
    }

    conn = None
    try:
        conn = get_db_connection()
        inventory_stock = fetch_available_inventory_stock(conn)
        zones = _get_zone_rows(conn, zone_id)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to fetch zones from the database")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.warning("Could not close database connection")

    if not zones:
        zones = [
            dict(zone)
            for zone in FALLBACK_ZONES
            if zone_id is None or zone["id"] == zone_id
        ]

    if not zones:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone id {zone_id} not found",
        )

    zone_results = []

    for zone in zones:
        current_id = zone.get("id", zone.get("zone_id"))
        current_name = zone.get(
            "name", zone.get("zone_name", f"Zone {current_id}")
        )
        current_type = (
            disaster_type
            or zone.get("disaster_type")
            or "earthquake"
        ).strip().lower()

        severity_raw = str(zone.get("severity") or "medium").strip().lower()
        severity_number = SEVERITY_SCALE_MAPPING.get(severity_raw, 3)

        population_raw = zone.get("population")
        buildings_raw = zone.get("affected_buildings")

        inputs_meta = {}

        if population_raw is not None and int(population_raw) > 0:
            population = int(population_raw)
            population_source = "actual"
        else:
            population = 3500
            population_source = "assumed fallback"

        inputs_meta["affected_population"] = {
            "value": population,
            "source": population_source,
        }

        if buildings_raw is not None and int(buildings_raw) > 0:
            buildings = int(buildings_raw)
            buildings_source = "actual"
        else:
            buildings = max(
                10,
                int(population / 4.5 * (severity_number / 5.0)),
            )
            buildings_source = "assumed fallback"

        inputs_meta["affected_buildings"] = {
            "value": buildings,
            "source": buildings_source,
        }
        inputs_meta["severity"] = {
            "value": severity_number,
            "source": f"mapped from severity: {severity_raw}",
        }
        inputs_meta["disaster_type"] = {
            "value": current_type,
            "source": "zone value or request override",
        }

        features = pd.DataFrame(
            [
                {
                    "disaster_type": current_type,
                    "affected_population": population,
                    "severity": severity_number,
                    "affected_buildings": buildings,
                }
            ]
        )

        baseline_demands = {}
        baseline_intervals = {}

        for target in TARGET_RESOURCES:
            prediction = models[target].predict(features)
            predicted_demand = float(
                np.clip(np.expm1(prediction[0]), 0, None)
            )
            predicted_demand = round(predicted_demand, 1)

            q_hat = quantiles[target]
            lower = round(max(0.0, predicted_demand - q_hat), 1)
            upper = round(max(0.0, predicted_demand + q_hat), 1)

            baseline_demands[target] = predicted_demand
            baseline_intervals[target] = {
                "lower": lower,
                "upper": upper,
                "margin_q_hat": round(q_hat, 1),
                "unit": RESOURCE_UNITS[target],
                "confidence_level": (
                    "Nominal 90% empirical split-conformal interval; "
                    "not a guarantee of real-world accuracy."
                ),
            }

        vulnerability = adjust_demand_for_vulnerability(
            baseline_demands=baseline_demands,
            elderly=elderly_share,
            children=children_share,
            medical_dependent=medically_dependent_share,
            use_assumed_defaults=True,
        )

        adjusted_demands = vulnerability["adjusted_demands"]
        multipliers = vulnerability["uplift_multipliers"]
        resource_results = {}

        for target in TARGET_RESOURCES:
            multiplier = multipliers.get(target, 1.0)
            base_demand = baseline_demands[target]
            adjusted_demand = adjusted_demands[target]

            adjusted_lower = round(
                max(
                    0.0,
                    baseline_intervals[target]["lower"] * multiplier,
                ),
                1,
            )
            adjusted_upper = round(
                baseline_intervals[target]["upper"] * multiplier,
                1,
            )

            stock = inventory_stock.get(target)

            if stock is not None:
                shortage = max(
                    0.0, round(adjusted_demand - stock, 1)
                )
                inventory = {
                    "available_stock": stock,
                    "estimated_shortage": shortage,
                    "unit": RESOURCE_UNITS[target],
                    "status": (
                        "Shortage Detected"
                        if shortage > 0
                        else "Sufficient Stock"
                    ),
                }
            else:
                inventory = {
                    "available_stock": None,
                    "estimated_shortage": None,
                    "unit": RESOURCE_UNITS[target],
                    "status": "Inventory tracking not applicable.",
                }

            resource_results[target] = {
                "unit": RESOURCE_UNITS[target],
                "baseline_demand": base_demand,
                "adjusted_demand": adjusted_demand,
                "vulnerability_multiplier": multiplier,
                "baseline_interval_90pct": {
                    "lower": baseline_intervals[target]["lower"],
                    "upper": baseline_intervals[target]["upper"],
                },
                "adjusted_interval_90pct": {
                    "lower": adjusted_lower,
                    "upper": adjusted_upper,
                    "note": "Approximation scaled by vulnerability multiplier.",
                },
                "inventory": inventory,
            }

        zone_results.append(
            {
                "zone_id": current_id,
                "zone_name": current_name,
                "inputs_used": inputs_meta,
                "vulnerability_assessment": {
                    "status": vulnerability["status"],
                    "demographic_inputs": vulnerability["inputs_used"],
                    "source_labels": vulnerability["source_labels"],
                    "capped_uplifts": vulnerability["capped_uplifts"],
                    "multipliers": vulnerability["uplift_multipliers"],
                },
                "resources": resource_results,
            }
        )

    return {
        "status": "success",
        "zones_count": len(zone_results),
        "model_metadata": {
            "model_name": metrics_meta.get("model_name"),
            "model_version": metrics_meta.get("model_version"),
            "training_date": metrics_meta.get("training_date_utc"),
            "data_source": metrics_meta.get("data_source"),
            "evaluation_metrics": metrics_meta.get("resources"),
        },
        "general_disclaimers": [
            "Predictions are based on trained regression models and planning assumptions.",
            "Vulnerability uplifts use configured planning weights and are not individual assessments.",
            "Nominal 90% empirical intervals do not guarantee real-world certainty.",
            "Fallback zones are demonstration data, not verified incident records.",
        ],
        "data": zone_results,
    }


@router.post(
    "/zones/{zone_id}/update",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Dynamic demand update for a zone (Module C)",
)
async def post_zone_update(
    zone_id: int,
    payload: DynamicUpdatePayload,
):
    """Process a dynamic update for a database-backed zone."""

    models, quantiles, _ = get_ml_artifacts()

    conn = None
    try:
        conn = get_db_connection()
        inventory_stock = fetch_available_inventory_stock(conn)

        base_zone = _get_zone_by_id(conn, zone_id)

        return apply_dynamic_update(
            zone_id=zone_id,
            base_zone_data=base_zone,
            payload=payload,
            models=models,
            quantiles=quantiles,
            inventory_stock=inventory_stock,
            severity_map=SEVERITY_SCALE_MAPPING,
            resource_units=RESOURCE_UNITS,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Dynamic zone update failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dynamic update failed: {exc}",
        ) from exc
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.warning("Could not close database connection")


@router.post(
    "/simulate",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Scenario-based demand simulation (Module D)",
)
async def post_scenario_simulation(
    request: SimulationBatchRequest,
):
    """
    Run what-if simulations without writing to database tables.

    Uses a database zone when present; otherwise, uses the same
    explicitly labelled fallback zones as GET /zones.
    """

    models, quantiles, _ = get_ml_artifacts()

    conn = None
    try:
        conn = get_db_connection()
        inventory_stock = fetch_available_inventory_stock(conn)

        if request.zone_id is not None:
            try:
                base_zone = _get_zone_by_id(conn, request.zone_id)
            except HTTPException:
                raise
        else:
            cursor = conn.execute(
                "SELECT * FROM disaster_zones ORDER BY id ASC LIMIT 1"
            )
            row = cursor.fetchone()

            if row:
                base_zone = dict(row)
            else:
                base_zone = dict(FALLBACK_ZONES[0])

        return run_scenario_simulation(
            base_zone=base_zone,
            scenarios=request.scenarios,
            real_inventory_snapshot=inventory_stock,
            models=models,
            quantiles=quantiles,
            severity_map=SEVERITY_SCALE_MAPPING,
            resource_units=RESOURCE_UNITS,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Scenario simulation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scenario simulation failed: {exc}",
        ) from exc
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                logger.warning("Could not close database connection")
