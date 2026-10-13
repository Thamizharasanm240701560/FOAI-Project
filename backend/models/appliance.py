"""
AI Power Optimizer - Data Models
=================================
Pydantic models for appliances, backup systems, optimization settings,
and result structures used throughout the application.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum


class Priority(str, Enum):
    """Appliance priority levels for optimization weighting."""
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ── Priority weights used by the fitness function ──
PRIORITY_WEIGHTS = {
    Priority.VERY_HIGH: 10,
    Priority.HIGH: 7,
    Priority.MEDIUM: 4,
    Priority.LOW: 1,
}


class Appliance(BaseModel):
    """
    Represents a single household appliance with its power requirements
    and scheduling preferences.
    """
    name: str = Field(..., min_length=1, description="Appliance name")
    power_watts: float = Field(..., gt=0, description="Power consumption in Watts")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority level")
    required_duration_hours: float = Field(
        default=1.0, ge=0, description="Desired operating duration in hours"
    )
    min_duration_hours: float = Field(
        default=0.0, ge=0, description="Minimum operating duration in hours"
    )
    max_duration_hours: Optional[float] = Field(
        default=None, ge=0, description="Maximum operating duration in hours"
    )
    preferred_start_hour: Optional[float] = Field(
        default=None, ge=0, le=24, description="Preferred start hour (0-24)"
    )
    preferred_end_hour: Optional[float] = Field(
        default=None, ge=0, le=24, description="Preferred end hour (0-24)"
    )
    is_essential: bool = Field(
        default=False, description="Whether this appliance is essential"
    )
    continuous_operation: bool = Field(
        default=False,
        description="Whether the appliance must run without interruption",
    )

    @field_validator("max_duration_hours")
    @classmethod
    def max_duration_gte_min(cls, v, info):
        min_dur = info.data.get("min_duration_hours", 0)
        if v is not None and v < min_dur:
            raise ValueError("max_duration_hours must be >= min_duration_hours")
        return v


class BackupSystem(BaseModel):
    """
    Represents the household backup-power system (inverter + battery).
    """
    max_power_watts: float = Field(
        ..., gt=0, description="Maximum inverter power output in Watts"
    )
    battery_capacity_wh: float = Field(
        ..., gt=0, description="Total battery capacity in Watt-hours"
    )
    battery_percentage: float = Field(
        ..., ge=0, le=100, description="Current battery charge percentage"
    )
    outage_duration_hours: float = Field(
        ..., gt=0, description="Expected power-outage duration in hours"
    )
    solar_enabled: bool = Field(
        default=False, description="Whether solar generation is available"
    )
    solar_generation: Optional[List[float]] = Field(
        default=None,
        description="Solar generation in Watts for each time slot",
    )

    @property
    def available_energy_wh(self) -> float:
        """Calculate usable energy: capacity × percentage / 100."""
        return self.battery_capacity_wh * self.battery_percentage / 100.0


class OptimizationSettings(BaseModel):
    """
    Simulated Annealing hyper-parameters and time-slot configuration.
    """
    initial_temperature: float = Field(default=1000.0, gt=0)
    min_temperature: float = Field(default=0.1, gt=0)
    cooling_rate: float = Field(default=0.995, gt=0, lt=1)
    max_iterations: int = Field(default=10000, gt=0)
    time_slot_minutes: int = Field(default=30, description="Slot size in minutes")

    @field_validator("time_slot_minutes")
    @classmethod
    def valid_slot_size(cls, v):
        if v not in (15, 30, 60):
            raise ValueError("time_slot_minutes must be 15, 30, or 60")
        return v


class OptimizationRequest(BaseModel):
    """Complete request payload for the /api/optimize endpoint."""
    backup: BackupSystem
    appliances: List[Appliance]
    settings: OptimizationSettings = Field(default_factory=OptimizationSettings)


class ApplianceSchedule(BaseModel):
    """The ON/OFF schedule for a single appliance across all time slots."""
    appliance_name: str
    power_watts: float
    priority: str
    is_essential: bool
    slots: List[int]  # 1 = ON, 0 = OFF
    energy_consumed_wh: float
    operating_hours: float


class SAMetrics(BaseModel):
    """Telemetry data from the Simulated Annealing run."""
    initial_temperature: float
    final_temperature: float
    total_iterations: int
    accepted_count: int
    rejected_count: int
    initial_fitness: float
    best_fitness: float
    fitness_history: List[float]  # sampled every N iterations
    temperature_history: List[float]


class ComparisonData(BaseModel):
    """Before-vs-After comparison between naive and SA schedules."""
    naive_energy_consumed: float
    naive_remaining_energy: float
    naive_priority_score: float
    naive_essential_satisfaction: float
    naive_appliances_powered: int
    naive_backup_duration: float
    sa_energy_consumed: float
    sa_remaining_energy: float
    sa_priority_score: float
    sa_essential_satisfaction: float
    sa_appliances_powered: int
    sa_backup_duration: float


class OptimizationResult(BaseModel):
    """Complete result payload returned by /api/optimize."""
    schedule: List[ApplianceSchedule]
    time_slots: List[str]  # e.g. ["06:00", "06:30", ...]
    fitness: float
    energy_consumed_wh: float
    remaining_energy_wh: float
    battery_percentage: float
    peak_power_watts: float
    priority_satisfaction: float
    essential_satisfaction: float
    appliances_powered: int
    total_appliances: int
    backup_duration_hours: float
    power_per_slot: List[float]
    energy_per_slot: List[float]
    battery_percentage_per_slot: List[float]
    explanations: List[str]
    warnings: List[str]
    sa_metrics: SAMetrics
    comparison: ComparisonData
