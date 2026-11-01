
"""
backend/services/scenario.py
----------------------------
Module D: Scenario Simulation Service.

Simulates disaster-relief scenarios involving:
- Response speed.
- Resource availability.
- Population changes.
- Severity changes.

Safety:
- Inventory is copied into memory before calculations.
- This service does not insert, update, or delete database records.
- Untracked resources return null inventory metrics.
"""

from typing import Any, Dict, List, Optional
import copy

from pydantic import BaseModel, Field, field_validator


class SingleScenarioConfig(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Scenario name."
    )

    response_speed: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of demand deliverable within the response window."
    )

    resource_availability: float = Field(
        100.0,
        ge=0.0,
        le=150.0,
        description="Percentage of baseline inventory available."
    )

    population_multiplier: Optional[float] = Field(
        1.0,
        ge=0.1,
        le=10.0
    )

    population_override: Optional[int] = Field(
        None,
        ge=50,
        le=2_000_000
    )

    severity_override: Optional[str] = Field(
        None,
        description="low, medium, high, or critical."
    )

    severity_delta: Optional[int] = Field(
        0,
        ge=-4,
        le=4
    )

    @field_validator("severity_override")
    @classmethod
    def validate_severity_override(
        cls,
        value: Optional[str]
    ) -> Optional[str]:
        if value is None:
            return None

        clean = value.strip().lower()

        allowed = {
            "low", "medium", "high", "critical",
            "1", "2", "3", "4", "5"
        }

        if clean not in allowed:
            raise ValueError(
                "Invalid severity_override. Allowed values: "
                "'low', 'medium', 'high', 'critical', or '1' to '5'."
            )

        return clean


class SimulationBatchRequest(BaseModel):
    zone_id: Optional[int] = Field(
        None,
        description="Optional zone ID to simulate."
    )

    scenarios: List[SingleScenarioConfig] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Between one and five scenarios."
    )


def run_scenario_simulation(
    base_zone: Dict[str, Any],
    scenarios: List[SingleScenarioConfig],
    real_inventory_snapshot: Dict[str, Any],
    models: Dict[str, Any],
    quantiles: Dict[str, float],
    severity_map: Dict[str, int],
    resource_units: Dict[str, str],
) -> Dict[str, Any]:
    """
    Run scenarios against an in-memory inventory snapshot.

    This function performs no database writes.
    """

    # Import using the package path used by backend.main:app.
    from backend.services.dynamic_update import _run_pipeline

    if not isinstance(base_zone, dict):
        raise ValueError("base_zone must be a dictionary.")

    if not scenarios:
        raise ValueError("At least one scenario is required.")

    zone_id = base_zone.get("id", base_zone.get("zone_id"))
    zone_name = base_zone.get(
        "name",
        base_zone.get("zone_name", f"Zone {zone_id or 'Unknown'}")
    )

    orig_pop = max(1, int(base_zone.get("population") or 3500))
    orig_sev_str = str(base_zone.get("severity") or "Medium")
    orig_d_type = str(base_zone.get("disaster_type") or "earthquake")
    orig_bld = max(0, int(base_zone.get("affected_buildings") or 0))

    normalized_severity_map = {
        str(key).strip().lower(): int(value)
        for key, value in severity_map.items()
    }

    resource_keys = [
        "food_packets",
        "water_litres",
        "medical_kits",
        "shelter_capacity_persons",
    ]

    # Check required units before starting the simulation.
    missing_units = [
        key for key in resource_keys
        if key not in resource_units
    ]
    if missing_units:
        raise ValueError(
            f"Missing resource units for: {', '.join(missing_units)}"
        )

    # Copy the snapshot once; never modify the original.
    in_memory_stock = copy.deepcopy(real_inventory_snapshot or {})
    scenario_outputs = []

    for scenario in scenarios:
        if scenario.population_override is not None:
            sim_pop = scenario.population_override
        else:
            multiplier = (
                scenario.population_multiplier
                if scenario.population_multiplier is not None
                else 1.0
            )
            sim_pop = int(round(orig_pop * multiplier))

        sim_pop = max(10, sim_pop)

        original_severity_number = normalized_severity_map.get(
            orig_sev_str.strip().lower(), 3
        )

        if scenario.severity_override is not None:
            requested_severity = scenario.severity_override.lower()

            severity_numbers = {
                "low": 1,
                "medium": 3,
                "high": 4,
                "critical": 5,
                "1": 1,
                "2": 2,
                "3": 3,
                "4": 4,
                "5": 5,
            }

            sim_sev_num = severity_numbers[requested_severity]
            reverse_severity = {
                1: "Low",
                2: "Low",
                3: "Medium",
                4: "High",
                5: "Critical",
            }
            sim_sev_str = reverse_severity[sim_sev_num]
        else:
            delta = scenario.severity_delta or 0
            sim_sev_num = max(
                1,
                min(5, original_severity_number + delta)
            )

            reverse_severity = {
                1: "Low",
                2: "Low",
                3: "Medium",
                4: "High",
                5: "Critical",
            }
            sim_sev_str = reverse_severity[sim_sev_num]

        # Scale affected buildings by population and severity.
        severity_ratio = (
            sim_sev_num / max(1, original_severity_number)
        )
        population_ratio = sim_pop / orig_pop

        sim_bld = max(
            5,
            int(round(orig_bld * population_ratio * severity_ratio))
        )

        demands, intervals = _run_pipeline(
            disaster_type=orig_d_type,
            population=sim_pop,
            severity_str=sim_sev_str,
            buildings=sim_bld,
            demographics={
                "elderly": None,
                "children": None,
                "medical_dependent": None,
            },
            models=models,
            quantiles=quantiles,
            severity_map=severity_map,
            resource_units=resource_units,
        )

        resource_metrics = {}

        for resource in resource_keys:
            unit = resource_units[resource]
            demand_value = demands[resource]
            interval = intervals.get(resource)

            raw_stock = in_memory_stock.get(resource)

            if raw_stock is None:
                resource_metrics[resource] = {
                    "unit": unit,
                    "estimated_demand": demand_value,
                    "available_resources": None,
                    "shortage": None,
                    "deliverable_within_window": None,
                    "unmet_demand": None,
                    "interval_90pct": interval,
                    "note": (
                        "Stock metrics unavailable: inventory is not "
                        "tracked for this resource."
                    ),
                }
                continue

            available = round(
                float(raw_stock)
                * scenario.resource_availability
                / 100.0,
                1,
            )

            shortage = max(
                0.0,
                round(demand_value - available, 1)
            )

            deliverable = round(
                min(
                    available,
                    demand_value * scenario.response_speed,
                ),
                1,
            )

            unmet = max(
                0.0,
                round(demand_value - deliverable, 1)
            )

            resource_metrics[resource] = {
                "unit": unit,
                "estimated_demand": demand_value,
                "available_resources": available,
                "shortage": shortage,
                "deliverable_within_window": deliverable,
                "unmet_demand": unmet,
                "interval_90pct": interval,
            }

        scenario_outputs.append({
            "scenario_name": scenario.name,
            "simulation_parameters": {
                "response_speed": scenario.response_speed,
                "resource_availability_pct": scenario.resource_availability,
                "simulated_population": sim_pop,
                "simulated_severity": sim_sev_str,
                "simulated_buildings": sim_bld,
            },
            "formula_definitions": {
                "estimated_demand": (
                    "Demand prediction adjusted for scenario conditions."
                ),
                "available_resources": (
                    "Inventory snapshot multiplied by availability percentage."
                ),
                "shortage": (
                    "max(0, estimated_demand - available_resources)."
                ),
                "deliverable_within_window": (
                    "min(available_resources, "
                    "estimated_demand * response_speed)."
                ),
                "unmet_demand": (
                    "max(0, estimated_demand - deliverable_within_window)."
                ),
            },
            "results": resource_metrics,
        })

    return {
        "status": "success",
        "zone_id": zone_id,
        "zone_name": zone_name,
        "scenarios_evaluated": len(scenario_outputs),
        "safety_guarantee": (
            "Simulation uses an in-memory inventory snapshot. "
            "This service does not modify database tables."
        ),
        "scenarios": scenario_outputs,
    }
