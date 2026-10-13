"""
AI Power Optimizer - Constraint Validators
============================================
Hard constraints that every valid schedule MUST satisfy.
These are used both during neighbor evaluation and final validation.

Constraints:
  C1: Per-slot total power  <=  max inverter power
  C2: Cumulative energy     <=  available battery energy
  C3: Essential appliances  must meet minimum duration (when feasible)
  C4: Appliance time-window restrictions
  C5: Appliance max-duration limits
"""

from typing import List, Tuple
import sys
import os

# Allow imports from the parent package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.appliance import Appliance, BackupSystem


def calculate_slot_power(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_index: int,
) -> float:
    """
    Calculate the total power consumption in a specific time slot.

    Args:
        schedule:  2D list [appliance_idx][slot_idx] with 1=ON, 0=OFF
        appliances: List of Appliance objects
        slot_index: The time-slot to calculate

    Returns:
        Total watts consumed in this slot
    """
    total = 0.0
    for app_idx, appliance in enumerate(appliances):
        if schedule[app_idx][slot_index] == 1:
            total += appliance.power_watts
    return total


def calculate_total_energy(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
) -> float:
    """
    Calculate the total energy consumed by the entire schedule.

    Energy = Power × Time  (for each ON slot)

    Args:
        schedule:          2D schedule matrix
        appliances:        List of Appliance objects
        slot_duration_hours: Duration of each slot in hours

    Returns:
        Total energy in Watt-hours
    """
    total_energy = 0.0
    for app_idx, appliance in enumerate(appliances):
        slots_on = sum(schedule[app_idx])
        total_energy += appliance.power_watts * slots_on * slot_duration_hours
    return total_energy


def calculate_energy_per_slot(
    schedule: List[List[int]],
    appliances: List[Appliance],
    num_slots: int,
    slot_duration_hours: float,
    backup: BackupSystem,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Calculate energy consumed per slot, cumulative energy, and battery %.

    If solar is enabled, solar generation offsets battery drain.

    Returns:
        (power_per_slot, cumulative_energy, battery_pct_per_slot)
    """
    available_energy = backup.available_energy_wh
    power_per_slot = []
    cumulative_energy = []
    battery_pct = []
    running_energy = 0.0

    for s in range(num_slots):
        slot_power = calculate_slot_power(schedule, appliances, s)
        power_per_slot.append(slot_power)

        # Energy consumed this slot
        energy_this_slot = slot_power * slot_duration_hours

        # Subtract solar generation if enabled
        if backup.solar_enabled and backup.solar_generation:
            solar_idx = min(s, len(backup.solar_generation) - 1)
            solar_watts = backup.solar_generation[solar_idx]
            solar_energy = solar_watts * slot_duration_hours
            energy_this_slot = max(0, energy_this_slot - solar_energy)

        running_energy += energy_this_slot
        cumulative_energy.append(running_energy)

        remaining = available_energy - running_energy
        pct = max(0, (remaining / backup.battery_capacity_wh) * 100)
        battery_pct.append(round(pct, 1))

    return power_per_slot, cumulative_energy, battery_pct


# ═══════════════════════════════════════════════════════
#  CONSTRAINT CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════


def check_power_constraint(
    schedule: List[List[int]],
    appliances: List[Appliance],
    max_power: float,
    num_slots: int,
) -> List[int]:
    """
    C1: Check that no time slot exceeds the inverter's max power.

    Returns:
        List of slot indices where the constraint is violated.
    """
    violations = []
    for s in range(num_slots):
        if calculate_slot_power(schedule, appliances, s) > max_power:
            violations.append(s)
    return violations


def check_energy_constraint(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
    available_energy: float,
) -> float:
    """
    C2: Check that total energy does not exceed available battery energy.

    Returns:
        The amount of energy exceeding the limit (0 if feasible).
    """
    total = calculate_total_energy(schedule, appliances, slot_duration_hours)
    return max(0.0, total - available_energy)


def check_essential_constraints(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
) -> List[Tuple[str, float, float]]:
    """
    C3: Check that essential appliances meet their minimum duration.

    Returns:
        List of (appliance_name, actual_hours, required_hours) for violations.
    """
    violations = []
    for app_idx, app in enumerate(appliances):
        if app.is_essential:
            actual_hours = sum(schedule[app_idx]) * slot_duration_hours
            if actual_hours < app.min_duration_hours:
                violations.append(
                    (app.name, actual_hours, app.min_duration_hours)
                )
    return violations


def check_time_window_constraint(
    schedule: List[List[int]],
    appliances: List[Appliance],
    num_slots: int,
    outage_start_hour: float,
    slot_duration_hours: float,
) -> List[Tuple[str, int]]:
    """
    C4: Check that appliances only operate within their permitted time window.

    Returns:
        List of (appliance_name, slot_index) for violations.
    """
    violations = []
    for app_idx, app in enumerate(appliances):
        if app.preferred_start_hour is None and app.preferred_end_hour is None:
            continue
        for s in range(num_slots):
            if schedule[app_idx][s] == 1:
                slot_hour = outage_start_hour + s * slot_duration_hours
                if app.preferred_start_hour is not None and slot_hour < app.preferred_start_hour:
                    violations.append((app.name, s))
                if app.preferred_end_hour is not None and slot_hour >= app.preferred_end_hour:
                    violations.append((app.name, s))
    return violations


def check_max_duration_constraint(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
) -> List[Tuple[str, float, float]]:
    """
    C5: Check that no appliance exceeds its maximum allowed duration.

    Returns:
        List of (appliance_name, actual_hours, max_hours) for violations.
    """
    violations = []
    for app_idx, app in enumerate(appliances):
        if app.max_duration_hours is not None:
            actual_hours = sum(schedule[app_idx]) * slot_duration_hours
            if actual_hours > app.max_duration_hours:
                violations.append(
                    (app.name, actual_hours, app.max_duration_hours)
                )
    return violations


def count_all_violations(
    schedule: List[List[int]],
    appliances: List[Appliance],
    backup: BackupSystem,
    num_slots: int,
    slot_duration_hours: float,
    outage_start_hour: float = 6.0,
) -> dict:
    """
    Run all constraint checks and return a summary dict.
    """
    power_violations = check_power_constraint(
        schedule, appliances, backup.max_power_watts, num_slots
    )
    energy_excess = check_energy_constraint(
        schedule, appliances, slot_duration_hours, backup.available_energy_wh
    )
    essential_violations = check_essential_constraints(
        schedule, appliances, slot_duration_hours
    )
    time_violations = check_time_window_constraint(
        schedule, appliances, num_slots, outage_start_hour, slot_duration_hours
    )
    duration_violations = check_max_duration_constraint(
        schedule, appliances, slot_duration_hours
    )

    return {
        "power_violation_slots": power_violations,
        "energy_excess_wh": energy_excess,
        "essential_violations": essential_violations,
        "time_window_violations": time_violations,
        "max_duration_violations": duration_violations,
        "total_violations": (
            len(power_violations)
            + (1 if energy_excess > 0 else 0)
            + len(essential_violations)
            + len(time_violations)
            + len(duration_violations)
        ),
    }
