"""
DRIVEWISE — Demo Data Seeder
Runs the simulation headlessly at N× speed to generate a realistic multi-day
dataset without waiting hours in real time.

Usage:
    python backend/persistence/seed_demo_data.py [--hours 72] [--speed 60] [--reset]

Options:
    --hours N    Number of simulated hours to generate (default: 72 = 3 days)
    --speed N    Simulation speed multiplier (default: 60 — runs 1h sim in ~60s)
    --reset      Drop and recreate all tables before seeding

The script injects six fault/degradation scenarios at fixed sim-time offsets
so the resulting database has interesting signal for every query in queries.py.

Fault injection schedule:
  Hour  4  → S2 OVERCURRENT trip    (cleared after 120 sim-seconds)
  Hour 12  → S1 THERMAL_OVERLOAD   (sustained high load 4 sim-hours)
  Hour 24  → S3 UNDERVOLTAGE trip   (brief supply dip, self-clears)
  Hour 36  → S2 bearing degradation spike (2× rate for 2 sim-hours)
  Hour 48  → S1 OVERCURRENT + cascade stops S2/S3
  Hour 60  → S3 THERMAL_OVERLOAD   (repeat scenario)
  Hour  2  → FAT full suite execution (TC001–TC006)
"""
import argparse
import asyncio
import json
import logging
import math
import sys
import os
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from project root or backend/
# ---------------------------------------------------------------------------
_script_dir  = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _backend_dir)

from coordinator import SimulationCoordinator, DriveUnit
from test_engine import TestEngine
from persistence.db import (
    get_engine, create_all_tables,
    tag_readings, alarms, health_snapshots, fat_test_runs,
    alarm_meta,
)
from persistence.writer import (
    _build_tag_row, _build_health_row, _FaultTracker,
    _vibration_rms, persist_fat_run,
)
from sqlalchemy import insert, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seeder")

UNITS = ("S1", "S2", "S3")

# ---------------------------------------------------------------------------
# Fault injection schedule — (sim_hour, action_fn)
# ---------------------------------------------------------------------------

def _schedule(coordinator):
    """
    Return list of (sim_second_trigger, action_callable) pairs,
    sorted ascending.  action_callable receives coordinator as its only arg.
    """
    H = 3600.0  # seconds per sim-hour

    def overcurrent_s2(c):
        log.info("[FAULT] Hour ~4: S2 OVERCURRENT trip")
        c.units["S2"].drive.fault("OVERCURRENT")
        c.units["S2"].prot_overcurrent_trip = True

    def clear_s2_fault(c):
        log.info("[CLEAR] S2 fault cleared")
        c.units["S2"].drive.reset_fault()
        c.units["S2"].prot_overcurrent_trip = False
        c.units["S2"].drive.start()
        c.units["S2"].drive.set_speed_target(c.units["S2"].drive.rated_speed)

    def high_load_s1(c):
        log.info("[FAULT] Hour ~12: S1 high thermal load (200% material)")
        c.units["S1"].conveyor.set_material_load(100)

    def thermal_s1_trip(c):
        log.info("[FAULT] Hour ~16: S1 THERMAL_OVERLOAD trip")
        c.units["S1"].drive.fault("THERMAL_OVERLOAD")
        c.units["S1"].prot_thermal_trip = True

    def clear_s1_thermal(c):
        log.info("[CLEAR] S1 thermal cleared")
        c.units["S1"].drive.reset_fault()
        c.units["S1"].prot_thermal_trip = False
        c.units["S1"].drive.start()
        c.units["S1"].drive.set_speed_target(c.units["S1"].drive.rated_speed)

    def undervoltage_s3(c):
        log.info("[FAULT] Hour ~24: S3 supply voltage dip → UNDERVOLTAGE trip")
        c.units["S3"].supply_voltage_pct = 65.0  # below 70% trip threshold
        c.units["S3"].prot_undervoltage_trip = True
        c.units["S3"].drive.fault("UNDERVOLTAGE")

    def restore_s3_voltage(c):
        log.info("[CLEAR] S3 voltage restored")
        c.units["S3"].supply_voltage_pct = 100.0
        c.units["S3"].drive.reset_fault()
        c.units["S3"].prot_undervoltage_trip = False
        c.units["S3"].drive.start()
        c.units["S3"].drive.set_speed_target(c.units["S3"].drive.rated_speed)

    def bearing_spike_s2(c):
        log.info("[DEGRADE] Hour ~36: S2 bearing degradation rate 10× for 2 hours")
        c.units["S2"].bearing.degradation_rate = 0.01  # 10× normal

    def bearing_restore_s2(c):
        log.info("[RESTORE] S2 bearing degradation rate normalised")
        c.units["S2"].bearing.degradation_rate = 0.001

    def cascade_fault_s1(c):
        log.info("[FAULT] Hour ~48: S1 OVERCURRENT → cascade stops S2/S3")
        c.units["S1"].drive.fault("OVERCURRENT")
        c.units["S1"].prot_overcurrent_trip = True

    def clear_cascade(c):
        log.info("[CLEAR] Cascade fault cleared, all units restarted")
        for uid in UNITS:
            u = c.units[uid]
            u.drive.reset_fault()
            u.prot_overcurrent_trip = False
            u.prot_overvoltage_trip = False
            u.prot_undervoltage_trip = False
            u.prot_thermal_trip = False
            u.drive.start()
            u.drive.set_speed_target(u.drive.rated_speed)

    def thermal_s3_trip(c):
        log.info("[FAULT] Hour ~60: S3 THERMAL_OVERLOAD repeat")
        c.units["S3"].drive.fault("THERMAL_OVERLOAD")
        c.units["S3"].prot_thermal_trip = True

    def clear_s3_thermal(c):
        log.info("[CLEAR] S3 thermal repeat cleared")
        c.units["S3"].drive.reset_fault()
        c.units["S3"].prot_thermal_trip = False
        c.units["S3"].drive.start()
        c.units["S3"].drive.set_speed_target(c.units["S3"].drive.rated_speed)

    return sorted([
        (4 * H,          overcurrent_s2),
        (4 * H + 120,    clear_s2_fault),
        (12 * H,         high_load_s1),
        (16 * H,         thermal_s1_trip),
        (17 * H,         clear_s1_thermal),
        (24 * H,         undervoltage_s3),
        (24 * H + 60,    restore_s3_voltage),
        (36 * H,         bearing_spike_s2),
        (38 * H,         bearing_restore_s2),
        (48 * H,         cascade_fault_s1),
        (48 * H + 300,   clear_cascade),
        (60 * H,         thermal_s3_trip),
        (61 * H,         clear_s3_thermal),
    ], key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Seeder core
# ---------------------------------------------------------------------------

async def run_fat_tests(coordinator, engine, base_ts: datetime, sim_hour_2_offset: float):
    """Run all 6 FAT tests and persist results to fat_test_runs."""
    log.info("[FAT] Running all 6 FAT test cases (headless)…")
    test_engine = TestEngine(coordinator)
    results = await test_engine.run_all()
    for tc in results:
        d = tc.to_dict()
        ts = base_ts + timedelta(seconds=sim_hour_2_offset)
        with engine.begin() as conn:
            conn.execute(
                insert(fat_test_runs).values(
                    timestamp       = ts,
                    test_id         = d["testId"],
                    test_name       = d["name"],
                    pass_fail       = "pass" if d.get("passed") else "fail",
                    assertions_json = json.dumps(d.get("results", [])),
                    report_pdf_path = None,
                )
            )
    log.info("[FAT] %d test results persisted", len(results))


def seed(total_hours: int = 72, speed_mult: int = 60, reset: bool = False):
    """
    Main seeding function.  Synchronous outer shell; FAT test block uses
    asyncio.run() for its async sub-section.
    """
    engine = get_engine()

    if reset:
        log.info("[SEED] Dropping and recreating all tables…")
        from persistence.db import get_metadata
        get_metadata().drop_all(engine)

    create_all_tables()

    coordinator = SimulationCoordinator()
    # Start all drives immediately
    coordinator.speed_multiplier = speed_mult
    coordinator.start_all()

    fault_schedule  = _schedule(coordinator)
    fault_idx       = 0
    fault_tracker   = _FaultTracker()

    total_sim_seconds = total_hours * 3600.0
    effective_dt      = coordinator.dt * speed_mult  # real-time seconds per step

    # We track sim_time manually here (coordinator.sim_time advances in step())
    tag_accum    = 0.0   # accumulator for 1 Hz downsample
    health_accum = 0.0   # accumulator for 60 s health snapshot

    # Wall-clock base — all timestamps are sim-time relative to this anchor
    base_ts = datetime.now(timezone.utc) - timedelta(seconds=total_sim_seconds)

    fat_done = False
    last_pct = -1

    log.info(
        "[SEED] Simulating %d hours at %d× → ~%.0f real-time minutes",
        total_hours, speed_mult, (total_sim_seconds / speed_mult) / 60
    )

    while coordinator.sim_time < total_sim_seconds:
        # --- Fault injection ---
        while fault_idx < len(fault_schedule):
            trigger_t, action = fault_schedule[fault_idx]
            if coordinator.sim_time >= trigger_t:
                action(coordinator)
                fault_idx += 1
            else:
                break

        # --- FAT tests at sim hour 2 ---
        if not fat_done and coordinator.sim_time >= 2 * 3600.0:
            fat_done = True
            asyncio.run(
                run_fat_tests(coordinator, engine, base_ts, coordinator.sim_time)
            )

        # --- Simulation step ---
        coordinator.step()
        tag_accum    += effective_dt
        health_accum += effective_dt

        # --- 1 Hz tag write ---
        if tag_accum >= 1.0:
            tags = coordinator.get_all_tags()
            sim_ts = base_ts + timedelta(seconds=coordinator.sim_time)
            with engine.begin() as conn:
                for unit_id in UNITS:
                    row = _build_tag_row(unit_id, tags, sim_ts)
                    conn.execute(insert(tag_readings).values(**row))
                for unit_id in UNITS:
                    fault_tracker.check_and_record(conn, unit_id, tags)
            tag_accum = 0.0

        # --- 60 s health snapshot ---
        if health_accum >= 60.0:
            tags   = coordinator.get_all_tags()
            sim_ts = base_ts + timedelta(seconds=coordinator.sim_time)
            with engine.begin() as conn:
                for unit_id in UNITS:
                    row = _build_health_row(unit_id, tags, sim_ts)
                    conn.execute(insert(health_snapshots).values(**row))
            health_accum = 0.0

        # --- Progress report every 5% ---
        pct = int(coordinator.sim_time / total_sim_seconds * 100)
        if pct % 5 == 0 and pct != last_pct:
            elapsed_h = coordinator.sim_time / 3600
            tags = coordinator.get_all_tags()
            log.info(
                "[SEED] %3d%%  sim=%.1f h  S1=%.0f rpm  S2=%.0f rpm  S3=%.0f rpm",
                pct, elapsed_h,
                tags.get("S1_speed_actual", 0),
                tags.get("S2_speed_actual", 0),
                tags.get("S3_speed_actual", 0),
            )
            last_pct = pct

    log.info("[SEED] ✓ Seeding complete!")
    _print_summary(engine)


def _print_summary(engine):
    """Print row counts from all tables."""
    with engine.connect() as conn:
        for table in ("tag_readings", "alarms", "health_snapshots", "fat_test_runs"):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            log.info("[SEED]   %-22s  %7d rows", table, count)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed DRIVEWISE database with simulated multi-day data."
    )
    parser.add_argument(
        "--hours",  type=int, default=72,
        help="Simulated hours to generate (default: 72 = 3 days)"
    )
    parser.add_argument(
        "--speed",  type=int, default=60,
        help="Simulation speed multiplier (default: 60x)"
    )
    parser.add_argument(
        "--reset",  action="store_true",
        help="Drop and recreate all tables before seeding"
    )
    args = parser.parse_args()

    seed(total_hours=args.hours, speed_mult=args.speed, reset=args.reset)
