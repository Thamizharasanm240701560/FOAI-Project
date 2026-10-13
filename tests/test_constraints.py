"""
AI Power Optimizer — Constraint Tests
=======================================
Verifies that all hard constraints are correctly enforced.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.appliance import Appliance, BackupSystem, Priority
from optimizer.constraints import (
    calculate_slot_power,
    calculate_total_energy,
    check_power_constraint,
    check_energy_constraint,
    check_essential_constraints,
    check_time_window_constraint,
    check_max_duration_constraint,
    count_all_violations,
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


def make_backup(max_power=1000, capacity=3000, pct=70, duration=4):
    return BackupSystem(
        max_power_watts=max_power, battery_capacity_wh=capacity,
        battery_percentage=pct, outage_duration_hours=duration,
    )


# ──────────────────────────────────────────────
#  TEST: Slot power calculation
# ──────────────────────────────────────────────

def test_slot_power_calculation():
    """Total power in a slot is the sum of ON appliances."""
    apps = [make_appliance(power=150), make_appliance(power=75)]
    schedule = [[1, 0, 1], [1, 1, 0]]  # both ON in slot 0
    assert calculate_slot_power(schedule, apps, 0) == 225
    assert calculate_slot_power(schedule, apps, 1) == 75
    assert calculate_slot_power(schedule, apps, 2) == 150
    print("✅ test_slot_power_calculation PASSED")


# ──────────────────────────────────────────────
#  TEST: Total energy calculation
# ──────────────────────────────────────────────

def test_total_energy_calculation():
    """Energy = Power × Time for each ON slot."""
    apps = [make_appliance(power=100)]
    schedule = [[1, 1, 0, 0]]  # 2 slots ON
    slot_hours = 0.5  # 30-minute slots
    energy = calculate_total_energy(schedule, apps, slot_hours)
    # 100W × 2 slots × 0.5h = 100 Wh
    assert energy == 100.0, f"Expected 100, got {energy}"
    print("✅ test_total_energy_calculation PASSED")


# ──────────────────────────────────────────────
#  TEST: Power constraint — no slot exceeds max
# ──────────────────────────────────────────────

def test_power_constraint_no_violation():
    """A valid schedule should have zero power violations."""
    apps = [make_appliance(power=200), make_appliance(power=300)]
    schedule = [[1, 1], [1, 0]]  # slot 0: 500W, slot 1: 200W
    violations = check_power_constraint(schedule, apps, max_power=1000, num_slots=2)
    assert len(violations) == 0
    print("✅ test_power_constraint_no_violation PASSED")


def test_power_constraint_with_violation():
    """Detect slots where combined power exceeds inverter max."""
    apps = [make_appliance(power=600), make_appliance(power=500)]
    schedule = [[1, 0], [1, 0]]  # slot 0: 1100W (exceeds 1000W)
    violations = check_power_constraint(schedule, apps, max_power=1000, num_slots=2)
    assert 0 in violations
    assert len(violations) == 1
    print("✅ test_power_constraint_with_violation PASSED")


# ──────────────────────────────────────────────
#  TEST: Energy constraint — total ≤ battery
# ──────────────────────────────────────────────

def test_energy_constraint_no_violation():
    """Total energy within battery capacity → no excess."""
    apps = [make_appliance(power=100)]
    schedule = [[1, 1, 1, 1]]
    excess = check_energy_constraint(schedule, apps, 0.5, available_energy=500)
    assert excess == 0.0
    print("✅ test_energy_constraint_no_violation PASSED")


def test_energy_constraint_with_violation():
    """Total energy exceeds battery → positive excess."""
    apps = [make_appliance(power=500)]
    schedule = [[1, 1, 1, 1]]
    # 500W × 4 slots × 0.5h = 1000 Wh, but only 500 Wh available
    excess = check_energy_constraint(schedule, apps, 0.5, available_energy=500)
    assert excess == 500.0, f"Expected 500, got {excess}"
    print("✅ test_energy_constraint_with_violation PASSED")


# ──────────────────────────────────────────────
#  TEST: Essential appliance constraints
# ──────────────────────────────────────────────

def test_essential_constraint_satisfied():
    """Essential appliance meets minimum duration → no violation."""
    apps = [make_appliance(essential=True, min_d=1.0)]
    schedule = [[1, 1, 1, 0]]  # 1.5h at 0.5h slots
    violations = check_essential_constraints(schedule, apps, 0.5)
    assert len(violations) == 0
    print("✅ test_essential_constraint_satisfied PASSED")


def test_essential_constraint_violated():
    """Essential appliance below minimum duration → violation reported."""
    apps = [make_appliance(name="WiFi", essential=True, min_d=2.0)]
    schedule = [[1, 0, 0, 0]]  # only 0.5h
    violations = check_essential_constraints(schedule, apps, 0.5)
    assert len(violations) == 1
    assert violations[0][0] == "WiFi"
    print("✅ test_essential_constraint_violated PASSED")


# ──────────────────────────────────────────────
#  TEST: Time window constraint
# ──────────────────────────────────────────────

def test_time_window_respected():
    """Appliance ON within its preferred window → no violation."""
    # Window: 6–8, outage starts at 6
    apps = [make_appliance(start=6, end=8)]
    schedule = [[1, 1, 1, 0]]  # 6:00, 6:30, 7:00 → all in window
    violations = check_time_window_constraint(schedule, apps, 4, 6.0, 0.5)
    assert len(violations) == 0
    print("✅ test_time_window_respected PASSED")


def test_time_window_violated():
    """Appliance ON outside its window → violation detected."""
    apps = [make_appliance(start=6, end=7)]
    # slot 2 = 7:00, slot 3 = 7:30 → outside [6, 7)
    schedule = [[0, 0, 1, 1]]
    violations = check_time_window_constraint(schedule, apps, 4, 6.0, 0.5)
    assert len(violations) >= 1
    print("✅ test_time_window_violated PASSED")


# ──────────────────────────────────────────────
#  TEST: Max duration constraint
# ──────────────────────────────────────────────

def test_max_duration_respected():
    apps = [make_appliance(max_d=2.0)]
    schedule = [[1, 1, 1, 0]]  # 1.5h ≤ 2.0h
    violations = check_max_duration_constraint(schedule, apps, 0.5)
    assert len(violations) == 0
    print("✅ test_max_duration_respected PASSED")


def test_max_duration_violated():
    apps = [make_appliance(name="AC", max_d=1.0)]
    schedule = [[1, 1, 1, 1]]  # 2.0h > 1.0h
    violations = check_max_duration_constraint(schedule, apps, 0.5)
    assert len(violations) == 1
    assert violations[0][0] == "AC"
    print("✅ test_max_duration_violated PASSED")


# ──────────────────────────────────────────────
#  TEST: Battery calculation
# ──────────────────────────────────────────────

def test_battery_available_energy():
    """Available energy = capacity × percentage / 100."""
    backup = make_backup(capacity=3000, pct=70)
    assert backup.available_energy_wh == 2100.0
    backup2 = make_backup(capacity=3000, pct=100)
    assert backup2.available_energy_wh == 3000.0
    backup3 = make_backup(capacity=3000, pct=0)
    assert backup3.available_energy_wh == 0.0
    print("✅ test_battery_available_energy PASSED")


# ──────────────────────────────────────────────
#  TEST: All-violations summary
# ──────────────────────────────────────────────

def test_count_all_violations_clean():
    """Clean schedule with no violations."""
    apps = [make_appliance(power=100, essential=True, min_d=0.5)]
    backup = make_backup(max_power=1000, capacity=3000, pct=100)
    schedule = [[1, 1, 0, 0]]
    result = count_all_violations(schedule, apps, backup, 4, 0.5)
    assert result["total_violations"] == 0
    print("✅ test_count_all_violations_clean PASSED")


# ──────────────────────────────────────────────
#  RUN ALL TESTS
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  CONSTRAINT TESTS")
    print("=" * 50 + "\n")

    test_slot_power_calculation()
    test_total_energy_calculation()
    test_power_constraint_no_violation()
    test_power_constraint_with_violation()
    test_energy_constraint_no_violation()
    test_energy_constraint_with_violation()
    test_essential_constraint_satisfied()
    test_essential_constraint_violated()
    test_time_window_respected()
    test_time_window_violated()
    test_max_duration_respected()
    test_max_duration_violated()
    test_battery_available_energy()
    test_count_all_violations_clean()

    print(f"\n{'=' * 50}")
    print("  ALL CONSTRAINT TESTS PASSED ✅")
    print("=" * 50)
