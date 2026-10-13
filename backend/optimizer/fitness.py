"""
AI Power Optimizer - Fitness Function
=======================================
Evaluates the quality of a candidate appliance schedule.

The fitness function balances REWARDS for desired behavior against
PENALTIES for constraint violations:

  ┌─────────────────────────────────────────────────────────────────┐
  │  Fitness = Priority Reward                                     │
  │          + Essential Appliance Reward                           │
  │          + Duration Satisfaction Reward                         │
  │          + Time Preference Reward                               │
  │          + Energy Utilization Reward                            │
  │          − Power Violation Penalty                              │
  │          − Energy Violation Penalty                             │
  │          − Switching Penalty                                    │
  │          − Essential Violation Penalty                          │
  └─────────────────────────────────────────────────────────────────┘

Each component is documented in detail below.
"""

from typing import List
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.appliance import Appliance, BackupSystem, Priority, PRIORITY_WEIGHTS
from optimizer.constraints import (
    calculate_slot_power,
    calculate_total_energy,
)

# ── Penalty / reward multipliers ──
POWER_VIOLATION_PENALTY = 10000    # Per slot that exceeds inverter max
ENERGY_VIOLATION_PENALTY = 5000    # If total energy exceeds battery
ESSENTIAL_VIOLATION_PENALTY = 8000 # Per essential appliance not meeting min
SWITCHING_PENALTY_FACTOR = 2       # Per ON→OFF or OFF→ON transition
ESSENTIAL_REWARD_BONUS = 50        # Extra reward per ON slot for essential apps
DURATION_SATISFACTION_WEIGHT = 30  # Reward for meeting required duration
TIME_PREFERENCE_WEIGHT = 15        # Reward for operating in preferred window
ENERGY_UTILIZATION_WEIGHT = 10     # Reward for good energy utilization


def calculate_fitness(
    schedule: List[List[int]],
    appliances: List[Appliance],
    backup: BackupSystem,
    num_slots: int,
    slot_duration_hours: float,
    outage_start_hour: float = 6.0,
) -> float:
    """
    Compute the total fitness of a candidate schedule.

    Higher fitness = better schedule.

    Args:
        schedule:           2D matrix [appliance][slot] with 1/0
        appliances:         List of Appliance objects
        backup:             BackupSystem configuration
        num_slots:          Number of time slots
        slot_duration_hours: Duration of each slot in hours
        outage_start_hour:  Hour-of-day the outage begins (default 6 AM)

    Returns:
        Fitness score (float)
    """
    fitness = 0.0

    # ═══ 1. PRIORITY REWARD ═══
    # Higher-priority appliances earn more points per ON slot.
    # Formula: Σ (priority_weight × slots_on × power / 100)
    for app_idx, app in enumerate(appliances):
        slots_on = sum(schedule[app_idx])
        weight = PRIORITY_WEIGHTS[app.priority]
        fitness += weight * slots_on * (app.power_watts / 100.0)

    # ═══ 2. ESSENTIAL APPLIANCE REWARD ═══
    # Extra bonus for every slot an essential appliance is ON.
    # Formula: Σ (ESSENTIAL_REWARD_BONUS × slots_on)  for essential apps
    for app_idx, app in enumerate(appliances):
        if app.is_essential:
            slots_on = sum(schedule[app_idx])
            fitness += ESSENTIAL_REWARD_BONUS * slots_on

    # ═══ 3. DURATION SATISFACTION REWARD ═══
    # Reward for meeting (or approaching) the required operating duration.
    # Score = min(actual / required, 1.0) × weight
    for app_idx, app in enumerate(appliances):
        if app.required_duration_hours > 0:
            actual_hours = sum(schedule[app_idx]) * slot_duration_hours
            satisfaction = min(actual_hours / app.required_duration_hours, 1.0)
            fitness += DURATION_SATISFACTION_WEIGHT * satisfaction * PRIORITY_WEIGHTS[app.priority]

    # ═══ 4. TIME PREFERENCE REWARD ═══
    # Reward for scheduling an appliance within its preferred time window.
    # Formula: preference_weight × (slots_in_window / total_slots_on)
    for app_idx, app in enumerate(appliances):
        if app.preferred_start_hour is None and app.preferred_end_hour is None:
            continue
        slots_on = sum(schedule[app_idx])
        if slots_on == 0:
            continue
        in_window = 0
        for s in range(num_slots):
            if schedule[app_idx][s] == 1:
                slot_hour = outage_start_hour + s * slot_duration_hours
                start_ok = (app.preferred_start_hour is None or
                            slot_hour >= app.preferred_start_hour)
                end_ok = (app.preferred_end_hour is None or
                          slot_hour < app.preferred_end_hour)
                if start_ok and end_ok:
                    in_window += 1
        fitness += TIME_PREFERENCE_WEIGHT * (in_window / slots_on) * PRIORITY_WEIGHTS[app.priority]

    # ═══ 5. ENERGY UTILIZATION REWARD ═══
    # Reward for using a reasonable fraction of available energy.
    # Too little → wasted backup potential.  Too much → risk of depletion.
    # Ideal utilization is 60-90% of available energy.
    available = backup.available_energy_wh
    total_energy = calculate_total_energy(schedule, appliances, slot_duration_hours)
    if available > 0:
        utilization = total_energy / available
        if 0.6 <= utilization <= 0.9:
            fitness += ENERGY_UTILIZATION_WEIGHT * 10  # ideal range bonus
        elif utilization < 0.6:
            fitness += ENERGY_UTILIZATION_WEIGHT * utilization * 10
        else:
            fitness += ENERGY_UTILIZATION_WEIGHT * max(0, (1.0 - utilization)) * 10

    # ═══ 6. POWER VIOLATION PENALTY ═══
    # HARD CONSTRAINT: per-slot total power must not exceed inverter max.
    # Penalty = POWER_VIOLATION_PENALTY × (excess / max_power) per violating slot
    for s in range(num_slots):
        slot_power = calculate_slot_power(schedule, appliances, s)
        if slot_power > backup.max_power_watts:
            excess_ratio = (slot_power - backup.max_power_watts) / backup.max_power_watts
            fitness -= POWER_VIOLATION_PENALTY * (1 + excess_ratio)

    # ═══ 7. ENERGY VIOLATION PENALTY ═══
    # HARD CONSTRAINT: total energy must not exceed available battery energy.
    # Penalty = ENERGY_VIOLATION_PENALTY × (excess / available)
    if total_energy > available:
        excess_ratio = (total_energy - available) / max(available, 1)
        fitness -= ENERGY_VIOLATION_PENALTY * (1 + excess_ratio)

    # ═══ 8. SWITCHING PENALTY ═══
    # Discourage unnecessary ON/OFF toggling.
    # Penalty = SWITCHING_PENALTY_FACTOR × number_of_transitions
    for app_idx in range(len(appliances)):
        transitions = 0
        for s in range(1, num_slots):
            if schedule[app_idx][s] != schedule[app_idx][s - 1]:
                transitions += 1
        fitness -= SWITCHING_PENALTY_FACTOR * transitions

    # ═══ 9. ESSENTIAL VIOLATION PENALTY ═══
    # HARD CONSTRAINT: essential appliances should meet their minimum duration.
    # Penalty applied when essential app runs less than its minimum.
    for app_idx, app in enumerate(appliances):
        if app.is_essential:
            actual_hours = sum(schedule[app_idx]) * slot_duration_hours
            if actual_hours < app.min_duration_hours:
                shortfall = (app.min_duration_hours - actual_hours) / max(app.min_duration_hours, 0.1)
                fitness -= ESSENTIAL_VIOLATION_PENALTY * (1 + shortfall)

    return fitness


def calculate_priority_satisfaction(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
) -> float:
    """
    Calculate what percentage of priority-weighted demand is satisfied.

    Returns:
        Percentage 0-100
    """
    total_possible = 0.0
    total_achieved = 0.0
    for app_idx, app in enumerate(appliances):
        weight = PRIORITY_WEIGHTS[app.priority]
        total_possible += weight * app.required_duration_hours
        actual_hours = sum(schedule[app_idx]) * slot_duration_hours
        achieved = min(actual_hours, app.required_duration_hours)
        total_achieved += weight * achieved
    if total_possible == 0:
        return 100.0
    return round((total_achieved / total_possible) * 100, 1)


def calculate_essential_satisfaction(
    schedule: List[List[int]],
    appliances: List[Appliance],
    slot_duration_hours: float,
) -> float:
    """
    Calculate what percentage of essential appliance requirements are met.

    Returns:
        Percentage 0-100
    """
    essential_count = 0
    satisfied = 0
    for app_idx, app in enumerate(appliances):
        if app.is_essential:
            essential_count += 1
            actual_hours = sum(schedule[app_idx]) * slot_duration_hours
            if actual_hours >= app.min_duration_hours:
                satisfied += 1
    if essential_count == 0:
        return 100.0
    return round((satisfied / essential_count) * 100, 1)
