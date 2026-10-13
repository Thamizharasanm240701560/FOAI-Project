"""
AI Power Optimizer - Neighbor Generation
==========================================
Generates neighboring solutions for Simulated Annealing by making
small random modifications to the current schedule.

Mutation Operators:
  1. Toggle ON  – Turn a random appliance ON in a random slot
  2. Toggle OFF – Turn a random appliance OFF in a random slot
  3. Move       – Move an appliance's ON slot to a different slot
  4. Extend     – Add one adjacent ON slot (extend duration)
  5. Reduce     – Remove one ON slot (reduce duration)
  6. Swap       – Swap ON/OFF state between two appliances in a slot
"""

import random
import copy
from typing import List
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.appliance import Appliance


def generate_neighbor(
    schedule: List[List[int]],
    appliances: List[Appliance],
    num_slots: int,
) -> List[List[int]]:
    """
    Generate a neighboring solution by applying one random mutation.

    The mutation is chosen uniformly at random from the 6 operators.
    If the chosen operator cannot apply (e.g. nothing to move),
    a fallback toggle is used.

    Args:
        schedule:   Current 2D schedule matrix [appliance][slot]
        appliances: List of Appliance objects
        num_slots:  Number of time slots

    Returns:
        A new schedule (deep copy with one mutation applied)
    """
    neighbor = copy.deepcopy(schedule)
    num_apps = len(appliances)

    if num_apps == 0 or num_slots == 0:
        return neighbor

    # Choose a random mutation operator (1-6)
    operator = random.randint(1, 6)

    if operator == 1:
        # ── TOGGLE ON ──
        # Pick a random appliance and slot, set to ON
        app_idx = random.randint(0, num_apps - 1)
        slot_idx = random.randint(0, num_slots - 1)
        neighbor[app_idx][slot_idx] = 1

    elif operator == 2:
        # ── TOGGLE OFF ──
        # Pick a random appliance and slot, set to OFF
        app_idx = random.randint(0, num_apps - 1)
        slot_idx = random.randint(0, num_slots - 1)
        neighbor[app_idx][slot_idx] = 0

    elif operator == 3:
        # ── MOVE ──
        # Find an ON slot for a random appliance and move it elsewhere
        app_idx = random.randint(0, num_apps - 1)
        on_slots = [s for s in range(num_slots) if neighbor[app_idx][s] == 1]
        off_slots = [s for s in range(num_slots) if neighbor[app_idx][s] == 0]
        if on_slots and off_slots:
            src = random.choice(on_slots)
            dst = random.choice(off_slots)
            neighbor[app_idx][src] = 0
            neighbor[app_idx][dst] = 1
        else:
            # Fallback: simple toggle
            slot_idx = random.randint(0, num_slots - 1)
            neighbor[app_idx][slot_idx] = 1 - neighbor[app_idx][slot_idx]

    elif operator == 4:
        # ── EXTEND ──
        # Find an ON slot and turn on an adjacent OFF slot
        app_idx = random.randint(0, num_apps - 1)
        on_slots = [s for s in range(num_slots) if neighbor[app_idx][s] == 1]
        if on_slots:
            slot = random.choice(on_slots)
            # Check neighbors
            candidates = []
            if slot > 0 and neighbor[app_idx][slot - 1] == 0:
                candidates.append(slot - 1)
            if slot < num_slots - 1 and neighbor[app_idx][slot + 1] == 0:
                candidates.append(slot + 1)
            if candidates:
                neighbor[app_idx][random.choice(candidates)] = 1
            else:
                # No adjacent off slot – toggle a random slot on
                slot_idx = random.randint(0, num_slots - 1)
                neighbor[app_idx][slot_idx] = 1
        else:
            # Nothing on – turn one on
            slot_idx = random.randint(0, num_slots - 1)
            neighbor[app_idx][slot_idx] = 1

    elif operator == 5:
        # ── REDUCE ──
        # Turn off one random ON slot for a random appliance
        app_idx = random.randint(0, num_apps - 1)
        on_slots = [s for s in range(num_slots) if neighbor[app_idx][s] == 1]
        if on_slots:
            slot = random.choice(on_slots)
            neighbor[app_idx][slot] = 0
        else:
            # Nothing to reduce – toggle random
            slot_idx = random.randint(0, num_slots - 1)
            neighbor[app_idx][slot_idx] = 1

    elif operator == 6:
        # ── SWAP ──
        # In a random slot, swap ON/OFF between two different appliances
        if num_apps >= 2:
            slot_idx = random.randint(0, num_slots - 1)
            a, b = random.sample(range(num_apps), 2)
            neighbor[a][slot_idx], neighbor[b][slot_idx] = (
                neighbor[b][slot_idx],
                neighbor[a][slot_idx],
            )
        else:
            # Only one appliance – toggle
            slot_idx = random.randint(0, num_slots - 1)
            neighbor[0][slot_idx] = 1 - neighbor[0][slot_idx]

    return neighbor
