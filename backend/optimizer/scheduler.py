"""
AI Power Optimizer - Scheduler
================================
Generates initial solutions and the naive baseline used for comparison.
"""

import random
from typing import List
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.appliance import Appliance, BackupSystem, Priority, PRIORITY_WEIGHTS


def calculate_num_slots(outage_duration_hours: float, slot_minutes: int) -> int:
    """How many time slots fit into the outage duration."""
    return max(1, int(outage_duration_hours * 60 / slot_minutes))


def generate_time_labels(
    num_slots: int, slot_minutes: int, start_hour: float = 6.0
) -> List[str]:
    """
    Generate human-readable labels for each time slot.
    Example: ["06:00", "06:30", "07:00", ...]
    """
    labels = []
    for s in range(num_slots):
        total_minutes = int(start_hour * 60) + s * slot_minutes
        h = total_minutes // 60
        m = total_minutes % 60
        labels.append(f"{h:02d}:{m:02d}")
    return labels


def generate_initial_solution(
    appliances: List[Appliance],
    backup: BackupSystem,
    num_slots: int,
    slot_duration_hours: float,
    outage_start_hour: float = 6.0,
) -> List[List[int]]:
    """
    Generate a random initial schedule that respects basic feasibility.

    Strategy:
      - Skip appliances whose power exceeds the inverter max
      - For essential appliances, try to schedule their required slots
      - For others, randomly assign ON/OFF based on priority probability
      - Respects time-window preferences when set
    """
    schedule = []
    for app_idx, app in enumerate(appliances):
        row = [0] * num_slots

        # Skip appliance if its power alone exceeds inverter capacity
        if app.power_watts > backup.max_power_watts:
            schedule.append(row)
            continue

        # Determine how many slots this appliance should ideally run
        required_slots = max(1, int(app.required_duration_hours / slot_duration_hours))
        required_slots = min(required_slots, num_slots)

        # Determine valid slots (respecting time window)
        valid_slots = []
        for s in range(num_slots):
            slot_hour = outage_start_hour + s * slot_duration_hours
            start_ok = (app.preferred_start_hour is None or
                        slot_hour >= app.preferred_start_hour)
            end_ok = (app.preferred_end_hour is None or
                      slot_hour < app.preferred_end_hour)
            if start_ok and end_ok:
                valid_slots.append(s)

        if not valid_slots:
            valid_slots = list(range(num_slots))

        # Probability of being ON depends on priority
        priority_prob = {
            Priority.VERY_HIGH: 0.8,
            Priority.HIGH: 0.6,
            Priority.MEDIUM: 0.4,
            Priority.LOW: 0.2,
        }
        prob = priority_prob.get(app.priority, 0.3)

        # For essential appliances, ensure minimum coverage
        if app.is_essential:
            chosen = random.sample(valid_slots, min(required_slots, len(valid_slots)))
            for s in chosen:
                row[s] = 1
        else:
            # Randomly assign based on priority probability
            for s in valid_slots:
                if random.random() < prob and sum(row) < required_slots:
                    row[s] = 1

        schedule.append(row)

    return schedule


def generate_naive_schedule(
    appliances: List[Appliance],
    backup: BackupSystem,
    num_slots: int,
    slot_duration_hours: float,
    outage_start_hour: float = 6.0,
) -> List[List[int]]:
    """
    Generate a naive/greedy baseline schedule for comparison.

    Strategy (simple fixed-priority):
      1. Sort appliances by priority (highest first)
      2. For each appliance (in priority order):
         - Try to schedule it for its required duration
         - Only schedule if it doesn't exceed inverter power
         - Only schedule if battery energy is sufficient
      3. No optimization, no backtracking

    This is intentionally sub-optimal to demonstrate the
    improvement gained by Simulated Annealing.
    """
    schedule = [[0] * num_slots for _ in appliances]

    # Sort indices by priority (highest weight first), essential first
    sorted_indices = sorted(
        range(len(appliances)),
        key=lambda i: (
            appliances[i].is_essential,
            PRIORITY_WEIGHTS[appliances[i].priority],
        ),
        reverse=True,
    )

    available_energy = backup.available_energy_wh
    energy_used = 0.0

    for app_idx in sorted_indices:
        app = appliances[app_idx]

        # Skip if single appliance exceeds inverter
        if app.power_watts > backup.max_power_watts:
            continue

        required_slots = max(1, int(app.required_duration_hours / slot_duration_hours))
        slots_scheduled = 0

        for s in range(num_slots):
            if slots_scheduled >= required_slots:
                break

            # Check time window
            slot_hour = outage_start_hour + s * slot_duration_hours
            if app.preferred_start_hour is not None and slot_hour < app.preferred_start_hour:
                continue
            if app.preferred_end_hour is not None and slot_hour >= app.preferred_end_hour:
                continue

            # Check power constraint for this slot
            current_power = sum(
                appliances[i].power_watts
                for i in range(len(appliances))
                if schedule[i][s] == 1
            )
            if current_power + app.power_watts > backup.max_power_watts:
                continue

            # Check energy constraint
            energy_this_slot = app.power_watts * slot_duration_hours
            if energy_used + energy_this_slot > available_energy:
                continue

            schedule[app_idx][s] = 1
            energy_used += energy_this_slot
            slots_scheduled += 1

    return schedule
