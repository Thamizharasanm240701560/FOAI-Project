"""
AI Power Optimizer - Simulated Annealing Engine
=================================================
FOAI SYLLABUS: Unit II — Local Search and Optimization Problems

This module implements the Simulated Annealing (SA) algorithm for
household backup-power scheduling.  It is HAND-IMPLEMENTED — no
external optimization library or solver is used.

═══════════════════════════════════════════════════════════════════
 KEY FOAI CONCEPTS DEMONSTRATED
═══════════════════════════════════════════════════════════════════

 1. STATE REPRESENTATION
    A candidate solution (schedule) is a 2-D binary matrix:
        schedule[appliance_index][time_slot_index]  ∈ {0, 1}
    where 1 = ON and 0 = OFF.

 2. INITIAL STATE
    Generated randomly with priority-based heuristics
    (see scheduler.py → generate_initial_solution).

 3. CURRENT STATE
    The schedule currently being explored by the SA loop.

 4. NEIGHBOR STATE
    A new schedule obtained by making ONE small random change
    to the current state (see neighbor.py → generate_neighbor).

 5. OBJECTIVE / FITNESS FUNCTION
    Evaluates how "good" a schedule is.  Higher = better.
    Combines rewards (priority, duration, energy) and penalties
    (power/energy violations, switching).
    (see fitness.py → calculate_fitness).

 6. TEMPERATURE (T)
    Controls the probability of accepting worse solutions.
    Starts high (exploration) and decreases over time (exploitation).

 7. COOLING SCHEDULE
    T_new = T_old × cooling_rate   (geometric cooling)
    e.g.  T = 1000 × 0.95^iteration

 8. ACCEPTANCE PROBABILITY
    If the neighbor is BETTER  → always accept.
    If the neighbor is WORSE   → accept with probability:

        P = exp( ΔE / T )

    where  ΔE = neighbor_fitness − current_fitness  (negative value)
    and    T  = current temperature.

    At high T, P ≈ 1  → many worse moves accepted (exploration).
    At low  T, P ≈ 0  → only improvements accepted (exploitation).

 9. ITERATIONS
    The loop runs until T < T_min  OR  iteration ≥ max_iterations.

10. BEST SOLUTION TRACKING
    The best schedule seen across ALL iterations is stored
    separately and returned as the final answer.

═══════════════════════════════════════════════════════════════════
 ALGORITHM PSEUDOCODE
═══════════════════════════════════════════════════════════════════

    current_state  ← generate_initial_solution()
    best_state     ← current_state
    T              ← initial_temperature

    WHILE T > T_min AND iteration < max_iterations:
        neighbor_state ← generate_neighbor(current_state)
        ΔE ← fitness(neighbor_state) − fitness(current_state)

        IF ΔE > 0:
            current_state ← neighbor_state          # better → accept
        ELSE:
            P ← exp(ΔE / T)
            IF random() < P:
                current_state ← neighbor_state      # worse → maybe accept
            # else: reject (keep current_state)

        IF fitness(current_state) > fitness(best_state):
            best_state ← current_state

        T ← T × cooling_rate
        iteration ← iteration + 1

    RETURN best_state
═══════════════════════════════════════════════════════════════════

Why Simulated Annealing? (FOAI justification)
  • The appliance-scheduling problem has an exponentially large state
    space (2^(appliances × time_slots) possible schedules).
  • Complete search (BFS/DFS) is infeasible.
  • SA is a LOCAL SEARCH method — it works with one state at a time
    and explores neighbors, making it memory-efficient.
  • The probabilistic acceptance of worse solutions allows SA to
    ESCAPE LOCAL OPTIMA, unlike pure hill-climbing.
  • SA does NOT require gradient information, making it suitable for
    combinatorial / discrete optimization problems.
"""

import math
import random
import copy
from typing import List, Tuple
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.appliance import Appliance, BackupSystem, OptimizationSettings
from optimizer.fitness import calculate_fitness
from optimizer.neighbor import generate_neighbor
from optimizer.scheduler import generate_initial_solution


def run_simulated_annealing(
    appliances: List[Appliance],
    backup: BackupSystem,
    settings: OptimizationSettings,
    num_slots: int,
    slot_duration_hours: float,
    outage_start_hour: float = 6.0,
) -> Tuple[List[List[int]], dict]:
    """
    Execute the Simulated Annealing optimization loop.

    This function implements the complete SA algorithm as described
    in FOAI Unit II — Local Search and Optimization.

    Args:
        appliances:          Household appliances to schedule
        backup:              Backup-power system configuration
        settings:            SA hyper-parameters (T₀, T_min, α, max_iter)
        num_slots:           Number of time slots in the schedule
        slot_duration_hours: Duration of each slot in hours
        outage_start_hour:   When the outage starts (hour of day)

    Returns:
        (best_schedule, metrics_dict)
        best_schedule — the optimized 2-D binary matrix
        metrics_dict  — SA telemetry for visualization / viva demo
    """

    # ══════════════════════════════════════════════════════
    #  STEP 1: Generate INITIAL STATE
    # ══════════════════════════════════════════════════════
    # The initial state is a randomly generated schedule that
    # respects basic feasibility (e.g. skipping appliances
    # whose power exceeds the inverter capacity).
    current_state = generate_initial_solution(
        appliances, backup, num_slots, slot_duration_hours, outage_start_hour
    )

    # ══════════════════════════════════════════════════════
    #  STEP 2: Evaluate the INITIAL FITNESS
    # ══════════════════════════════════════════════════════
    current_fitness = calculate_fitness(
        current_state, appliances, backup,
        num_slots, slot_duration_hours, outage_start_hour,
    )

    # ══════════════════════════════════════════════════════
    #  STEP 3: Initialize BEST SOLUTION tracking
    # ══════════════════════════════════════════════════════
    # We always keep a copy of the best state seen so far,
    # because the current state may wander to worse solutions.
    best_state   = copy.deepcopy(current_state)
    best_fitness = current_fitness
    initial_fitness = current_fitness

    # ══════════════════════════════════════════════════════
    #  STEP 4: Set SA hyper-parameters
    # ══════════════════════════════════════════════════════
    temperature    = settings.initial_temperature   # T₀ (e.g. 1000)
    min_temp       = settings.min_temperature       # T_min (e.g. 0.1)
    cooling_rate   = settings.cooling_rate           # α (e.g. 0.95)
    max_iterations = settings.max_iterations         # e.g. 10000

    # Telemetry counters
    accepted_count = 0   # how many neighbor states were accepted
    rejected_count = 0   # how many were rejected
    fitness_history     = [current_fitness]
    temperature_history = [temperature]

    # Sample telemetry at intervals to keep arrays manageable
    sample_interval = max(1, max_iterations // 200)

    # ══════════════════════════════════════════════════════
    #  STEP 5: MAIN SA LOOP — Local Search
    # ══════════════════════════════════════════════════════
    iteration = 0
    while temperature > min_temp and iteration < max_iterations:

        # ── 5a. Generate a NEIGHBOR STATE ──
        # A small random perturbation of the current schedule.
        # One of 6 mutation operators is applied (see neighbor.py).
        neighbor_state = generate_neighbor(
            current_state, appliances, num_slots
        )

        # ── 5b. Evaluate the NEIGHBOR FITNESS ──
        neighbor_fitness = calculate_fitness(
            neighbor_state, appliances, backup,
            num_slots, slot_duration_hours, outage_start_hour,
        )

        # ── 5c. Calculate ΔE (change in fitness) ──
        delta_e = neighbor_fitness - current_fitness

        # ── 5d. ACCEPTANCE DECISION ──
        if delta_e > 0:
            # Neighbor is BETTER → always accept
            accept = True
        else:
            # Neighbor is WORSE → accept with probability P = exp(ΔE / T)
            # This is the KEY SA mechanism:
            #   - At high T, exp(ΔE/T) ≈ 1, so worse moves are often accepted
            #     → allows EXPLORATION and escaping local optima.
            #   - At low T, exp(ΔE/T) ≈ 0, so only improvements are accepted
            #     → focuses on EXPLOITATION near the best found solution.
            try:
                acceptance_probability = math.exp(delta_e / temperature)
            except (OverflowError, ZeroDivisionError):
                acceptance_probability = 0.0
            accept = random.random() < acceptance_probability

        if accept:
            # Move to the neighbor state
            current_state   = neighbor_state
            current_fitness = neighbor_fitness
            accepted_count += 1

            # ── 5e. Update BEST SOLUTION if improved ──
            if current_fitness > best_fitness:
                best_state   = copy.deepcopy(current_state)
                best_fitness = current_fitness
        else:
            rejected_count += 1

        # ── 5f. COOLING SCHEDULE: T = T × α ──
        # Geometric cooling: temperature decreases exponentially.
        temperature *= cooling_rate

        # Record telemetry at sample points
        iteration += 1
        if iteration % sample_interval == 0:
            fitness_history.append(best_fitness)
            temperature_history.append(temperature)

    # Append final state
    fitness_history.append(best_fitness)
    temperature_history.append(temperature)

    # ══════════════════════════════════════════════════════
    #  STEP 6: Return the BEST SOLUTION and metrics
    # ══════════════════════════════════════════════════════
    metrics = {
        "initial_temperature": settings.initial_temperature,
        "final_temperature":   temperature,
        "total_iterations":    iteration,
        "accepted_count":      accepted_count,
        "rejected_count":      rejected_count,
        "initial_fitness":     initial_fitness,
        "best_fitness":        best_fitness,
        "fitness_history":     fitness_history,
        "temperature_history": temperature_history,
    }

    return best_state, metrics
