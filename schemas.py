from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator


# Directive Types
DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
]

BatteryAction = Literal[
    "charge",
    "discharge",
    "idle"
]


# Structured Adjustments
class SolarReductionAdjustment(BaseModel):
    hours: List[int]
    factor: float


class MinimumBatteryReserveAdjustment(BaseModel):
    hours: List[int]
    minimum_energy_kwh: float


class NoChargeWindowAdjustment(BaseModel):
    hours: List[int]


class NoDischargeWindowAdjustment(BaseModel):
    hours: List[int]


class MaxGridWindowAdjustment(BaseModel):
    hours: List[int]
    max_grid_kwh: float


StructuredAdjustment = Optional[
    Union[
        SolarReductionAdjustment,
        MinimumBatteryReserveAdjustment,
        NoChargeWindowAdjustment,
        NoDischargeWindowAdjustment,
        MaxGridWindowAdjustment,
    ]
]


# Interpretation
class DirectiveInterpretationEntry(BaseModel):
    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Optional[Union[dict, None]] = None
    explanation: str


# Hourly Request Entry
class HourInput(BaseModel):
    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float


# Battery Input Object
class BatteryInput(BaseModel):
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float


# Optimize Energy Request
class OptimizeEnergyRequest(BaseModel):
    scenario_id: str
    operator_notes: List[str]
    hours: List[HourInput]
    battery: BatteryInput

    @field_validator("operator_notes")
    @classmethod
    def validate_operator_notes(cls, v):
        if not (1 <= len(v) <= 3):
            raise ValueError("operator_notes must contain 1 to 3 non-empty strings")
        for note in v:
            if not note or not note.strip():
                raise ValueError("operator_notes cannot contain empty strings")
        return v

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v):
        if len(v) != 24:
            raise ValueError("hours array must contain exactly 24 entries")
        hours_seen = [h.hour for h in v]
        if sorted(hours_seen) != list(range(24)):
            raise ValueError("hours must contain exactly hours 0 through 23")
        return sorted(v, key=lambda x: x.hour)


# Hourly Plan Entry
class HourlyPlanEntry(BaseModel):
    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: BatteryAction
    battery_kwh: float
    battery_energy_after_kwh: float


# Optimize Energy Response
class OptimizeEnergyResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[DirectiveInterpretationEntry]
    hourly_plan: List[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str


class HealthResponse(BaseModel):
    status: str = "ok"
