"""
services/dynamic_update.py
--------------------------
Module C: Dynamic Demand Updates Service.

Supported Trigger Types:
1. 'field_report': scout or first-responder ground situation reports.
2. 'population_update': revised count of affected individuals in the zone.
3. 'severity_change': upgraded or downgraded disaster severity level.
4. 'satellite_assessment': manually submitted damage evaluation payload (labeled: 'manually supplied assessment, not live satellite integration').

Validation & Outlier Guardrails:
- population >= 0 and <= 2,000,000 (sane upper bound for an urban sector).
- severity in ['low', 'medium', 'high', 'critical'] or numeric 1-5.
- building counts >= 0.
- damage fraction between 0.0 and 1.0.
- source text is required and cannot be empty.
- Outlier detection: If reported population shifts by > 2.5x increase or < 0.4x reduction compared to baseline,
  the report is marked 'flagged_for_review' and NOT applied automatically to prevent erratic supply dispatches.
- Idempotency-safe: Duplicate submissions with the same idempotency key or content hash return the existing report
  without double-counting or re-triggering updates.
- In-memory fallback ledger: Works seamlessly even when PostgreSQL is offline or table is pending migration.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel, Field, field_validator

from backend.services.vulnerability import adjust_demand_for_vulnerability

# Maximum allowed population swing without manual supervisor confirmation
OUTLIER_MAX_MULTIPLIER = 2.5
OUTLIER_MIN_MULTIPLIER = 0.4

# In-memory store for active session reports (idempotency & fast recall)
_REPORT_LEDGER: Dict[str, Dict[str, Any]] = {}
_ZONE_STATE_STORE: Dict[int, Dict[str, Any]] = {}

class DynamicUpdatePayload(BaseModel):
    trigger_type: str = Field(..., description="One of: 'field_report', 'population_update', 'severity_change', 'satellite_assessment'")
    source_text: str = Field(..., min_length=3, max_length=200, description="Organization or scout source (e.g. 'NDRF Team 4', 'District Collectorate')")
    idempotency_key: Optional[str] = Field(None, max_length=100, description="Optional unique client token to prevent duplicate processing")
    
    # Optional trigger attributes
    reported_population: Optional[int] = Field(None, ge=0, le=2000000, description="Updated affected population")
    reported_severity: Optional[str] = Field(None, description="Severity: 'low', 'medium', 'high', 'critical' or '1'-'5'")
    reported_affected_buildings: Optional[int] = Field(None, ge=0, description="Count of damaged building footprints")
    damage_fraction: Optional[float] = Field(None, ge=0.0, le=1.0, description="Satellite assessment damage ratio (0.0 to 1.0)")
    assessment_date: Optional[str] = Field(None, description="Date of manual assessment (ISO format)")
    
    # Demographic vulnerability overrides
    elderly_share: Optional[float] = Field(None, ge=0.0, le=1.0)
    children_share: Optional[float] = Field(None, ge=0.0, le=1.0)
    medically_dependent_share: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger(cls, v: str) -> str:
        valid_triggers = {"field_report", "population_update", "severity_change", "satellite_assessment"}
        val = v.strip().lower()
        if val not in valid_triggers:
            raise ValueError(f"Invalid trigger_type '{v}'. Allowed: {sorted(list(valid_triggers))}")
        return val

    @field_validator("reported_severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = str(v).strip().lower()
        valid = {"low", "medium", "high", "critical", "1", "2", "3", "4", "5"}
        if val not in valid:
            raise ValueError(f"Invalid severity '{v}'. Allowed: 'low', 'medium', 'high', 'critical' or 1-5.")
        return val


def compute_idempotency_hash(zone_id: int, payload: DynamicUpdatePayload) -> str:
    """Computes a deterministic hash of payload if no client key is provided."""
    if payload.idempotency_key:
        return f"zone_{zone_id}:{payload.idempotency_key}"
    raw = f"{zone_id}:{payload.trigger_type}:{payload.reported_population}:{payload.reported_severity}:{payload.reported_affected_buildings}:{payload.damage_fraction}:{payload.source_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def apply_dynamic_update(
    zone_id: int,
    base_zone_data: Dict[str, Any],
    payload: DynamicUpdatePayload,
    models: Dict[str, Any],
    quantiles: Dict[str, float],
    inventory_stock: Dict[str, Any],
    severity_map: Dict[str, int],
    resource_units: Dict[str, str],
) -> Dict[str, Any]:
    """
    Evaluates dynamic update, checks for duplicates, applies outlier filters,
    and recalculates resource demand using the Day 3 prediction engine.
    """
    idem_key = compute_idempotency_hash(zone_id, payload)
    
    # Check for duplicate submission
    if idem_key in _REPORT_LEDGER:
        existing = _REPORT_LEDGER[idem_key]
        return {
            "status": "duplicate_ignored",
            "message": "Duplicate update detected. Previous result returned to prevent double-counting.",
            "report_id": existing.get("id"),
            "data": existing.get("result"),
        }

    # Retrieve current last-known state for this zone
    current_state = _ZONE_STATE_STORE.get(zone_id, {
        "population": base_zone_data.get("population", 3500),
        "severity": base_zone_data.get("severity", "Medium"),
        "buildings": base_zone_data.get("affected_buildings", 280),
        "disaster_type": base_zone_data.get("disaster_type", "earthquake"),
        "demographics": {
            "elderly": None,
            "children": None,
            "medical_dependent": None
        }
    })

    prev_pop = current_state["population"]
    prev_sev = current_state["severity"]
    prev_bld = current_state["buildings"]
    prev_d_type = current_state["disaster_type"]

    # Compute Previous Demand using previous state
    prev_demands, prev_intervals = _run_pipeline(
        disaster_type=prev_d_type,
        population=prev_pop,
        severity_str=prev_sev,
        buildings=prev_bld,
        demographics=current_state["demographics"],
        models=models,
        quantiles=quantiles,
        severity_map=severity_map,
        resource_units=resource_units,
    )

    # Inspect trigger changes
    new_pop = prev_pop
    new_sev = prev_sev
    new_bld = prev_bld
    changed_fields = []
    inputs_meta = {}

    is_outlier = False
    outlier_reason = None

    # Handle triggers
    if payload.trigger_type == "population_update":
        if payload.reported_population is not None:
            ratio = payload.reported_population / max(1, prev_pop)
            if ratio > OUTLIER_MAX_MULTIPLIER or ratio < OUTLIER_MIN_MULTIPLIER:
                is_outlier = True
                outlier_reason = f"Reported population ({payload.reported_population}) deviates by factor {ratio:.2f}x from previous state ({prev_pop}). Flagged for manual review."
            else:
                new_pop = payload.reported_population
                changed_fields.append("affected_population")

    elif payload.trigger_type == "severity_change":
        if payload.reported_severity is not None:
            new_sev = payload.reported_severity
            changed_fields.append("severity")

    elif payload.trigger_type == "satellite_assessment":
        # Manual satellite assessment
        if payload.damage_fraction is not None:
            # Estimate updated building counts from damage fraction
            new_bld = int(round(prev_pop * 0.22 * payload.damage_fraction))
            new_bld = max(1, new_bld)
            changed_fields.append("affected_buildings (derived from manual satellite damage fraction)")
        if payload.reported_affected_buildings is not None:
            new_bld = payload.reported_affected_buildings
            changed_fields.append("affected_buildings")

    elif payload.trigger_type == "field_report":
        # Scout ground report may update any of population, severity, or buildings
        if payload.reported_population is not None:
            ratio = payload.reported_population / max(1, prev_pop)
            if ratio > OUTLIER_MAX_MULTIPLIER or ratio < OUTLIER_MIN_MULTIPLIER:
                is_outlier = True
                outlier_reason = f"Ground scout population ({payload.reported_population}) deviates by factor {ratio:.2f}x. Flagged for review."
            else:
                new_pop = payload.reported_population
                changed_fields.append("affected_population")
        if payload.reported_severity is not None:
            new_sev = payload.reported_severity
            changed_fields.append("severity")
        if payload.reported_affected_buildings is not None:
            new_bld = payload.reported_affected_buildings
            changed_fields.append("affected_buildings")

    # Update demographics if provided
    new_demographics = dict(current_state["demographics"])
    if payload.elderly_share is not None:
        new_demographics["elderly"] = payload.elderly_share
        changed_fields.append("elderly_share")
    if payload.children_share is not None:
        new_demographics["children"] = payload.children_share
        changed_fields.append("children_share")
    if payload.medically_dependent_share is not None:
        new_demographics["medical_dependent"] = payload.medically_dependent_share
        changed_fields.append("medically_dependent_share")

    # Label inputs and metadata
    inputs_meta["affected_population"] = {
        "value": new_pop,
        "source": "reported (field telemetry)" if "affected_population" in changed_fields else "last_known_fallback"
    }
    inputs_meta["severity"] = {
        "value": new_sev,
        "source": "reported (field telemetry)" if "severity" in changed_fields else "last_known_fallback"
    }
    inputs_meta["affected_buildings"] = {
        "value": new_bld,
        "source": "reported (field/satellite assessment)" if any("affected_buildings" in f for f in changed_fields) else "last_known_fallback"
    }

    if is_outlier:
        # Outlier report: Do NOT update state. Keep previous demand active.
        result_payload = {
            "validation_status": "flagged_for_review",
            "message": outlier_reason,
            "trigger_type": payload.trigger_type,
            "source_text": payload.source_text,
            "applied_to_demand": False,
            "zone_id": zone_id,
            "changed_inputs": changed_fields,
            "current_active_demand": prev_demands,
        }
        _REPORT_LEDGER[idem_key] = {"id": idem_key, "result": result_payload}
        return result_payload

    # Normal accepted report: Recalculate demands using updated parameters
    new_demands, new_intervals = _run_pipeline(
        disaster_type=prev_d_type,
        population=new_pop,
        severity_str=new_sev,
        buildings=new_bld,
        demographics=new_demographics,
        models=models,
        quantiles=quantiles,
        severity_map=severity_map,
        resource_units=resource_units,
    )

    # Compute resource differences (new - prev)
    resource_comparisons = {}
    for r in ["food_packets", "water_litres", "medical_kits", "shelter_capacity_persons"]:
        p_val = prev_demands[r]
        n_val = new_demands[r]
        diff = round(n_val - p_val, 1)
        stock_val = inventory_stock.get(r)
        shortage = max(0.0, round(n_val - stock_val, 1)) if stock_val is not None else None
        
        resource_comparisons[r] = {
            "unit": resource_units[r],
            "previous_demand": p_val,
            "new_demand": n_val,
            "demand_delta": diff,
            "percentage_change": f"{((n_val - p_val) / max(1.0, p_val)) * 100:+.1f}%",
            "adjusted_interval_90pct": new_intervals[r],
            "available_stock": stock_val,
            "estimated_shortage": shortage,
        }

    # Update the zone's active state
    _ZONE_STATE_STORE[zone_id] = {
        "population": new_pop,
        "severity": new_sev,
        "buildings": new_bld,
        "disaster_type": prev_d_type,
        "demographics": new_demographics,
        "last_updated_at": datetime.now(timezone.utc).isoformat()
    }

    result_payload = {
        "validation_status": "accepted",
        "trigger_type": payload.trigger_type,
        "satellite_notice": "manually supplied assessment, not live satellite integration" if payload.trigger_type == "satellite_assessment" else None,
        "source_text": payload.source_text,
        "applied_to_demand": True,
        "zone_id": zone_id,
        "changed_inputs": changed_fields,
        "inputs_metadata": inputs_meta,
        "resource_updates": resource_comparisons,
    }

    _REPORT_LEDGER[idem_key] = {"id": idem_key, "result": result_payload}
    return result_payload


def _run_pipeline(
    disaster_type: str,
    population: int,
    severity_str: str,
    buildings: int,
    demographics: Dict[str, Optional[float]],
    models: Dict[str, Any],
    quantiles: Dict[str, float],
    severity_map: Dict[str, int],
    resource_units: Dict[str, str],
) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """Internal helper to execute Day 3 ML regression + vulnerability uplift."""
    import pandas as pd
    import numpy as np

    sev_clean = str(severity_str).strip().lower()
    sev_num = severity_map.get(sev_clean, 3)

    feat_df = pd.DataFrame([{
        "disaster_type": disaster_type.strip().lower(),
        "affected_population": population,
        "severity": sev_num,
        "affected_buildings": buildings,
    }])

    base_demands = {}
    base_intervals = {}

    for target in ["food_packets", "water_litres", "medical_kits", "shelter_capacity_persons"]:
        pipe = models[target]
        q_hat = quantiles[target]

        pred_log = pipe.predict(feat_df)
        pred_val = float(np.clip(np.expm1(pred_log[0]), 0, None))
        base_demands[target] = round(pred_val, 1)

        low = float(np.clip(pred_val - q_hat, 0, None))
        up = float(pred_val + q_hat)
        base_intervals[target] = (low, up)

    # Vulnerability adjustment
    vuln_res = adjust_demand_for_vulnerability(
        baseline_demands=base_demands,
        elderly=demographics.get("elderly"),
        children=demographics.get("children"),
        medical_dependent=demographics.get("medical_dependent"),
        use_assumed_defaults=True
    )

    adjusted_demands = vuln_res["adjusted_demands"]
    multipliers = vuln_res["uplift_multipliers"]

    adj_intervals = {}
    for target in ["food_packets", "water_litres", "medical_kits", "shelter_capacity_persons"]:
        mult = multipliers.get(target, 1.0)
        low, up = base_intervals[target]
        adj_intervals[target] = {
            "lower": round(max(0.0, low * mult), 1),
            "upper": round(up * mult, 1)
        }

    return adjusted_demands, adj_intervals
