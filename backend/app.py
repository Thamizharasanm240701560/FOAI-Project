"""
AI Power Optimizer - FastAPI Application
==========================================
Main backend application providing REST API endpoints for the
household backup-power optimization system.

Endpoints:
  GET  /api/health              – Health check
  GET  /api/default-appliances  – Default appliances + demo scenario
  POST /api/validate            – Validate input without optimization
  POST /api/optimize            – Run Simulated Annealing optimization
  GET  /                        – Serve frontend
"""

import json
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

# Ensure local imports work
sys.path.insert(0, os.path.dirname(__file__))

from models.appliance import (
    Appliance, BackupSystem, OptimizationSettings,
    OptimizationRequest, OptimizationResult,
    ApplianceSchedule, SAMetrics, ComparisonData,
    PRIORITY_WEIGHTS,
)
from optimizer.simulated_annealing import run_simulated_annealing
from optimizer.scheduler import (
    calculate_num_slots, generate_time_labels, generate_naive_schedule,
)
from optimizer.fitness import (
    calculate_fitness, calculate_priority_satisfaction,
    calculate_essential_satisfaction,
)
from optimizer.constraints import (
    calculate_total_energy, calculate_slot_power,
    calculate_energy_per_slot, count_all_violations,
)

# ════════════════════════════════════════════
#  App Setup
# ════════════════════════════════════════════

app = FastAPI(
    title="AI Power Optimizer",
    description="Intelligent household backup-power management using Simulated Annealing",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ════════════════════════════════════════════
#  Helper: Load default data
# ════════════════════════════════════════════

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "default_appliances.json")


def load_defaults():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


# ════════════════════════════════════════════
#  Helper: Generate Explanations
# ════════════════════════════════════════════

def generate_explanations(
    schedule, appliances, backup, num_slots, slot_duration_hours,
    time_labels, outage_start_hour=6.0
):
    """
    Generate natural-language explanations for each appliance's schedule.
    These are derived from the ACTUAL optimization results, not hardcoded.
    """
    explanations = []

    for app_idx, app in enumerate(appliances):
        slots_on = sum(schedule[app_idx])
        actual_hours = slots_on * slot_duration_hours
        on_times = [
            time_labels[s] for s in range(num_slots) if schedule[app_idx][s] == 1
        ]

        # ── Case 1: Appliance is completely OFF ──
        if slots_on == 0:
            if app.power_watts > backup.max_power_watts:
                explanations.append(
                    f"⛔ {app.name} is OFF for the entire outage because its "
                    f"power consumption ({app.power_watts}W) exceeds the "
                    f"inverter capacity ({backup.max_power_watts}W)."
                )
            else:
                explanations.append(
                    f"⚠️ {app.name} is OFF — it was displaced by higher-priority "
                    f"appliances to conserve battery energy."
                )
            continue

        # ── Case 2: Appliance is ON for some or all slots ──
        priority_reason = f"it has {app.priority.value.replace('_', ' ').lower()} priority"
        essential_reason = " and is marked as essential" if app.is_essential else ""

        # Duration analysis
        if app.required_duration_hours > 0:
            pct = min(100, round(actual_hours / app.required_duration_hours * 100))
            duration_note = (
                f"Meeting {pct}% of its {app.required_duration_hours}h "
                f"required duration ({actual_hours}h scheduled)."
            )
        else:
            duration_note = f"Scheduled for {actual_hours}h."

        # Time window analysis
        time_note = ""
        if app.preferred_start_hour is not None or app.preferred_end_hour is not None:
            window_start = app.preferred_start_hour or 0
            window_end = app.preferred_end_hour or 24
            in_window = sum(
                1 for s in range(num_slots)
                if schedule[app_idx][s] == 1
                and (outage_start_hour + s * slot_duration_hours) >= window_start
                and (outage_start_hour + s * slot_duration_hours) < window_end
            )
            if in_window == slots_on:
                time_note = (
                    f" Scheduled within its preferred window "
                    f"({int(window_start):02d}:00–{int(window_end):02d}:00)."
                )
            elif in_window > 0:
                time_note = (
                    f" {in_window}/{slots_on} slots are within the preferred "
                    f"window ({int(window_start):02d}:00–{int(window_end):02d}:00)."
                )

        # Power note
        power_note = f" Consuming {app.power_watts}W per slot."

        explanations.append(
            f"✅ {app.name} is ON at {', '.join(on_times)} because "
            f"{priority_reason}{essential_reason}. "
            f"{duration_note}{time_note}{power_note}"
        )

    return explanations


def generate_warnings(appliances, backup, schedule, num_slots, slot_duration_hours):
    """Generate warning messages for constraint issues."""
    warnings = []
    violations = count_all_violations(
        schedule, appliances, backup, num_slots, slot_duration_hours
    )

    if violations["power_violation_slots"]:
        warnings.append(
            f"⚠️ Power limit exceeded in {len(violations['power_violation_slots'])} "
            f"time slot(s). The optimizer minimized but could not fully eliminate "
            f"these violations."
        )

    if violations["energy_excess_wh"] > 0:
        warnings.append(
            f"⚠️ Total energy consumption exceeds available battery by "
            f"{violations['energy_excess_wh']:.0f} Wh."
        )

    for name, actual, required in violations["essential_violations"]:
        warnings.append(
            f"⚠️ Essential appliance '{name}' only scheduled for {actual:.1f}h "
            f"(minimum required: {required:.1f}h)."
        )

    for app in appliances:
        if app.power_watts > backup.max_power_watts:
            warnings.append(
                f"⛔ {app.name} requires {app.power_watts}W but inverter maximum "
                f"is {backup.max_power_watts}W. This appliance cannot operate."
            )

    return warnings


# ════════════════════════════════════════════
#  Helper: Build schedule metrics for a given solution
# ════════════════════════════════════════════

def compute_schedule_metrics(schedule, appliances, backup, num_slots, slot_duration_hours):
    """Compute summary metrics for any schedule (used for both naive & SA)."""
    total_energy = calculate_total_energy(schedule, appliances, slot_duration_hours)
    remaining = max(0, backup.available_energy_wh - total_energy)
    priority_sat = calculate_priority_satisfaction(schedule, appliances, slot_duration_hours)
    essential_sat = calculate_essential_satisfaction(schedule, appliances, slot_duration_hours)
    powered = sum(1 for i in range(len(appliances)) if sum(schedule[i]) > 0)

    # Calculate backup duration (last slot with energy remaining)
    _, cum_energy, batt_pct = calculate_energy_per_slot(
        schedule, appliances, num_slots, slot_duration_hours, backup
    )
    backup_dur = 0
    for s in range(num_slots):
        if batt_pct[s] > 0:
            backup_dur = (s + 1) * slot_duration_hours
    
    return {
        "energy_consumed": total_energy,
        "remaining_energy": remaining,
        "priority_score": priority_sat,
        "essential_satisfaction": essential_sat,
        "appliances_powered": powered,
        "backup_duration": backup_dur,
    }


# ════════════════════════════════════════════
#  API Endpoints
# ════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AI Power Optimizer"}


@app.get("/api/default-appliances")
def get_default_appliances():
    """Return default appliances and demo scenario configuration."""
    try:
        data = load_defaults()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/validate")
def validate_input(request: OptimizationRequest):
    """
    Validate the optimization request without running the algorithm.
    Returns validation status and any warnings.
    """
    warnings = []

    for app in request.appliances:
        if app.power_watts > request.backup.max_power_watts:
            warnings.append(
                f"{app.name} requires {app.power_watts}W but inverter max is "
                f"{request.backup.max_power_watts}W — it cannot be scheduled."
            )

    available = request.backup.available_energy_wh
    total_required_energy = sum(
        a.power_watts * a.required_duration_hours for a in request.appliances
    )
    if total_required_energy > available:
        warnings.append(
            f"Total required energy ({total_required_energy:.0f} Wh) exceeds "
            f"available battery ({available:.0f} Wh). Not all appliances can "
            f"run for their full required duration."
        )

    return {
        "valid": True,
        "warnings": warnings,
        "available_energy_wh": available,
        "total_required_energy_wh": total_required_energy,
    }


@app.post("/api/optimize")
def optimize(request: OptimizationRequest):
    """
    Run the Simulated Annealing optimization and return the result.

    This is the main endpoint that:
      1. Validates input
      2. Runs SA to find the optimized schedule
      3. Generates a naive baseline for comparison
      4. Computes all statistics and explanations
      5. Returns the complete result
    """
    try:
        backup = request.backup
        appliances = request.appliances
        settings = request.settings

        if len(appliances) == 0:
            raise HTTPException(status_code=400, detail="At least one appliance is required.")

        # Calculate time parameters
        num_slots = calculate_num_slots(
            backup.outage_duration_hours, settings.time_slot_minutes
        )
        slot_duration_hours = settings.time_slot_minutes / 60.0
        time_labels = generate_time_labels(
            num_slots, settings.time_slot_minutes, start_hour=6.0
        )

        # ── Run Simulated Annealing ──
        best_schedule, sa_metrics_dict = run_simulated_annealing(
            appliances, backup, settings,
            num_slots, slot_duration_hours,
            outage_start_hour=6.0,
        )

        # ── Generate Naive Baseline ──
        naive_schedule = generate_naive_schedule(
            appliances, backup, num_slots, slot_duration_hours,
            outage_start_hour=6.0,
        )

        # ── Compute metrics for both schedules ──
        sa_m = compute_schedule_metrics(
            best_schedule, appliances, backup, num_slots, slot_duration_hours
        )
        naive_m = compute_schedule_metrics(
            naive_schedule, appliances, backup, num_slots, slot_duration_hours
        )

        # ── Energy / battery tracking ──
        power_per_slot, cum_energy, batt_pct = calculate_energy_per_slot(
            best_schedule, appliances, num_slots, slot_duration_hours, backup
        )

        # Peak power
        peak_power = max(power_per_slot) if power_per_slot else 0

        # ── Build per-appliance schedule objects ──
        appliance_schedules = []
        for app_idx, app in enumerate(appliances):
            slots = best_schedule[app_idx]
            slots_on = sum(slots)
            energy = app.power_watts * slots_on * slot_duration_hours
            appliance_schedules.append(ApplianceSchedule(
                appliance_name=app.name,
                power_watts=app.power_watts,
                priority=app.priority.value,
                is_essential=app.is_essential,
                slots=slots,
                energy_consumed_wh=energy,
                operating_hours=slots_on * slot_duration_hours,
            ))

        # ── Explanations ──
        explanations = generate_explanations(
            best_schedule, appliances, backup, num_slots,
            slot_duration_hours, time_labels
        )
        warnings = generate_warnings(
            appliances, backup, best_schedule, num_slots, slot_duration_hours
        )

        # ── Energy per slot (for chart) ──
        energy_per_slot_list = [
            p * slot_duration_hours for p in power_per_slot
        ]

        # ── Build result ──
        result = OptimizationResult(
            schedule=appliance_schedules,
            time_slots=time_labels,
            fitness=round(sa_metrics_dict["best_fitness"], 2),
            energy_consumed_wh=round(sa_m["energy_consumed"], 1),
            remaining_energy_wh=round(sa_m["remaining_energy"], 1),
            battery_percentage=round(
                max(0, sa_m["remaining_energy"] / backup.battery_capacity_wh * 100), 1
            ),
            peak_power_watts=round(peak_power, 1),
            priority_satisfaction=sa_m["priority_score"],
            essential_satisfaction=sa_m["essential_satisfaction"],
            appliances_powered=sa_m["appliances_powered"],
            total_appliances=len(appliances),
            backup_duration_hours=sa_m["backup_duration"],
            power_per_slot=[round(p, 1) for p in power_per_slot],
            energy_per_slot=[round(e, 1) for e in energy_per_slot_list],
            battery_percentage_per_slot=batt_pct,
            explanations=explanations,
            warnings=warnings,
            sa_metrics=SAMetrics(**sa_metrics_dict),
            comparison=ComparisonData(
                naive_energy_consumed=round(naive_m["energy_consumed"], 1),
                naive_remaining_energy=round(naive_m["remaining_energy"], 1),
                naive_priority_score=naive_m["priority_score"],
                naive_essential_satisfaction=naive_m["essential_satisfaction"],
                naive_appliances_powered=naive_m["appliances_powered"],
                naive_backup_duration=naive_m["backup_duration"],
                sa_energy_consumed=round(sa_m["energy_consumed"], 1),
                sa_remaining_energy=round(sa_m["remaining_energy"], 1),
                sa_priority_score=sa_m["priority_score"],
                sa_essential_satisfaction=sa_m["essential_satisfaction"],
                sa_appliances_powered=sa_m["appliances_powered"],
                sa_backup_duration=sa_m["backup_duration"],
            ),
        )

        return result

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimization failed: {str(e)}"
        )


# ════════════════════════════════════════════
#  Static file serving (frontend)
# ════════════════════════════════════════════

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# Mount static files AFTER specific routes
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ════════════════════════════════════════════
#  Entry Point
# ════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  AI Power Optimizer — Starting Server")
    print("  http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
