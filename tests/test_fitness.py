"""
AI Power Optimizer — Fitness Function Tests
=============================================
Verifies that the fitness function rewards good schedules
and penalizes constraint violations.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.appliance import Appliance, BackupSystem, Priority
from optimizer.fitness import (
    calculate_fitness,
    calculate_priority_satisfaction,
    calculate_essential_satisfaction,
)


def make_appliance(name="Test", power=100, priority=Priority.MEDIUM,
                   required=1.0, min_d=0.0, max_d=None,
                   start=None, end=None, essential=False):
    return Appliance(
        name=name, power_watts=power, priority=priority,
        required_duration_hours=required, min_duration_hours=min_d,
        max_duration_hours=max_d, preferred_start_hour=start,
        preferred_end_hour=end, is_essential=essential,
    )


def make_backup(max_power=1000, capacity=3000, pct=70):
    return BackupSystem(
        max_power_watts=max_power, battery_capacity_wh=capacity,
        battery_percentage=pct, outage_duration_hours=4,
    )


# ──────────────────────────────────────────────
#  TEST: Higher-priority appliances get higher fitness
# ──────────────────────────────────────────────

def test_priority_reward():
    """A very-high priority appliance ON should score higher than low."""
    backup = make_backup()
    apps_high = [make_appliance(priority=Priority.VERY_HIGH)]
    apps_low  = [make_appliance(priority=Priority.LOW)]
    schedule = [[1, 1, 0, 0]]

    fitness_high = calculate_fitness(schedule, apps_high, backup, 4, 0.5)
    fitness_low  = calculate_fitness(schedule, apps_low,  backup, 4, 0.5)
    assert fitness_high > fitness_low, \
        f"Very-high ({fitness_high}) should beat low ({fitness_low})"
    print("✅ test_priority_reward PASSED")


# ──────────────────────────────────────────────
#  TEST: Essential appliance bonus
# ──────────────────────────────────────────────

def test_essential_bonus():
    """Essential appliances ON should score higher than non-essential (same power/priority)."""
    backup = make_backup()
    apps_ess = [make_appliance(essential=True)]
    apps_non = [make_appliance(essential=False)]
    schedule = [[1, 1, 0, 0]]

    f_ess = calculate_fitness(schedule, apps_ess, backup, 4, 0.5)
    f_non = calculate_fitness(schedule, apps_non, backup, 4, 0.5)
    assert f_ess > f_non
    print("✅ test_essential_bonus PASSED")


# ──────────────────────────────────────────────
#  TEST: Power violation incurs penalty
# ──────────────────────────────────────────────

def test_power_violation_penalty():
    """Schedule exceeding inverter max should have lower fitness."""
    backup = make_backup(max_power=100)
    apps = [make_appliance(power=150)]  # 150W > 100W max
    schedule_on  = [[1, 0, 0, 0]]  # violation
    schedule_off = [[0, 0, 0, 0]]  # no violation

    f_on  = calculate_fitness(schedule_on,  apps, backup, 4, 0.5)
    f_off = calculate_fitness(schedule_off, apps, backup, 4, 0.5)
    assert f_on < f_off, f"Violating schedule ({f_on}) should be worse than empty ({f_off})"
    print("✅ test_power_violation_penalty PASSED")


# ──────────────────────────────────────────────
#  TEST: Energy violation incurs penalty
# ──────────────────────────────────────────────

def test_energy_violation_penalty():
    """Schedule consuming more than available energy gets penalized."""
    backup = make_backup(capacity=100, pct=100)  # 100 Wh available
    apps = [make_appliance(power=200)]
    # 200W × 4 slots × 0.5h = 400 Wh >> 100 Wh → big penalty
    schedule = [[1, 1, 1, 1]]
    fitness = calculate_fitness(schedule, apps, backup, 4, 0.5)
    assert fitness < 0, f"Heavy energy violation should be negative, got {fitness}"
    print("✅ test_energy_violation_penalty PASSED")


# ──────────────────────────────────────────────
#  TEST: Switching penalty
# ──────────────────────────────────────────────

def test_switching_penalty():
    """More ON/OFF transitions should reduce fitness."""
    backup = make_backup()
    apps = [make_appliance(power=50)]
    continuous = [[1, 1, 1, 1]]   # 0 transitions
    toggling   = [[1, 0, 1, 0]]   # 3 transitions

    f_cont = calculate_fitness(continuous, apps, backup, 4, 0.5)
    f_togl = calculate_fitness(toggling,   apps, backup, 4, 0.5)
    assert f_cont > f_togl
    print("✅ test_switching_penalty PASSED")


# ──────────────────────────────────────────────
#  TEST: Priority satisfaction percentage
# ──────────────────────────────────────────────

def test_priority_satisfaction():
    """Full duration met → 100% satisfaction."""
    apps = [make_appliance(required=1.0, priority=Priority.HIGH)]
    schedule = [[1, 1, 0, 0]]  # 1.0h at 0.5h slots = required
    sat = calculate_priority_satisfaction(schedule, apps, 0.5)
    assert sat == 100.0
    print("✅ test_priority_satisfaction PASSED")


def test_priority_satisfaction_partial():
    """Half the required duration → ~50% satisfaction."""
    apps = [make_appliance(required=2.0, priority=Priority.HIGH)]
    schedule = [[1, 1, 0, 0]]  # 1.0h of 2.0h required
    sat = calculate_priority_satisfaction(schedule, apps, 0.5)
    assert 45 <= sat <= 55, f"Expected ~50, got {sat}"
    print("✅ test_priority_satisfaction_partial PASSED")


# ──────────────────────────────────────────────
#  TEST: Essential satisfaction percentage
# ──────────────────────────────────────────────

def test_essential_satisfaction():
    """Both essentials meet min → 100%."""
    apps = [
        make_appliance(essential=True, min_d=0.5),
        make_appliance(essential=True, min_d=0.5),
    ]
    schedule = [[1, 1, 0, 0], [1, 0, 0, 0]]
    sat = calculate_essential_satisfaction(schedule, apps, 0.5)
    assert sat == 100.0
    print("✅ test_essential_satisfaction PASSED")


def test_essential_satisfaction_partial():
    """One of two essentials unmet → 50%."""
    apps = [
        make_appliance(essential=True, min_d=0.5),
        make_appliance(essential=True, min_d=2.0),
    ]
    schedule = [[1, 0, 0, 0], [1, 0, 0, 0]]  # 2nd needs 2h, gets 0.5h
    sat = calculate_essential_satisfaction(schedule, apps, 0.5)
    assert sat == 50.0
    print("✅ test_essential_satisfaction_partial PASSED")


# ──────────────────────────────────────────────
#  TEST: Empty schedule fitness
# ──────────────────────────────────────────────

def test_empty_schedule():
    """All OFF schedule should still compute without error."""
    backup = make_backup()
    apps = [make_appliance()]
    schedule = [[0, 0, 0, 0]]
    fitness = calculate_fitness(schedule, apps, backup, 4, 0.5)
    assert isinstance(fitness, float)
    print("✅ test_empty_schedule PASSED")


# ──────────────────────────────────────────────
#  RUN ALL TESTS
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  FITNESS FUNCTION TESTS")
    print("=" * 50 + "\n")

    test_priority_reward()
    test_essential_bonus()
    test_power_violation_penalty()
    test_energy_violation_penalty()
    test_switching_penalty()
    test_priority_satisfaction()
    test_priority_satisfaction_partial()
    test_essential_satisfaction()
    test_essential_satisfaction_partial()
    test_empty_schedule()

    print(f"\n{'=' * 50}")
    print("  ALL FITNESS TESTS PASSED ✅")
    print("=" * 50)
