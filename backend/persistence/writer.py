"""
DRIVEWISE — Async Persistence Writer
Hooks into the simulation loop and writes to the database at:
  - 1 Hz  → tag_readings (one row per unit per second)
  - 60 s  → health_snapshots (one row per unit per minute)
  - Event → alarms (immediately on fault state change)

Designed as an asyncio task that runs alongside broadcast_tags().
It calls coordinator.get_all_tags() independently — no coupling to
the WebSocket broadcast path.
"""
import asyncio
import json
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import insert, update

from persistence.db import (
    get_engine, create_all_tables,
    tag_readings, alarms, health_snapshots,
    alarm_meta,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interval configuration
# ---------------------------------------------------------------------------
TAG_WRITE_INTERVAL     = 1.0   # seconds  (downsample 10 Hz → 1 Hz)
HEALTH_WRITE_INTERVAL  = 60.0  # seconds
UNITS                  = ("S1", "S2", "S3")


# ---------------------------------------------------------------------------
# Fault state tracker — detects rising edges in drive fault signals
# ---------------------------------------------------------------------------
class _FaultTracker:
    """
    Remembers the last fault code per unit so we can detect the moment a
    new fault appears and insert exactly one alarm row per event.
    """
    def __init__(self):
        # unit_id → (is_faulted: bool, alarm_db_id: int | None)
        self._state: dict[str, tuple[bool, int | None]] = {
            u: (False, None) for u in UNITS
        }

    def check_and_record(self, conn, unit_id: str, tags: dict) -> None:
        """
        Inspect current tags for a unit; insert alarm row on rising fault edge,
        update cleared_timestamp on falling edge.
        """
        prefix       = unit_id
        status       = tags.get(f"{prefix}_status", "STOPPED")
        is_faulted   = (status == "FAULT")
        fault_code   = tags.get(f"{prefix}_fault_code")  # may be absent from tag dict
        # Derive fault code from protection trip flags if not a direct tag
        if not fault_code and is_faulted:
            fault_code = _infer_fault_code(unit_id, tags)

        was_faulted, open_alarm_id = self._state[unit_id]

        if is_faulted and not was_faulted:
            # --- Rising edge: new alarm ---
            code = fault_code or "UNKNOWN_FAULT"
            priority, category, description = alarm_meta(code)
            result = conn.execute(
                insert(alarms).values(
                    timestamp         = datetime.now(timezone.utc),
                    unit_id           = unit_id,
                    alarm_code        = code,
                    priority          = priority,
                    category          = category,
                    description       = description,
                    ack_status        = "ACTIVE",
                    cleared_timestamp = None,
                )
            )
            alarm_id = result.inserted_primary_key[0]
            self._state[unit_id] = (True, alarm_id)
            log.info("[ALARM] %s %s raised (id=%s)", unit_id, code, alarm_id)

        elif not is_faulted and was_faulted and open_alarm_id is not None:
            # --- Falling edge: alarm cleared ---
            conn.execute(
                update(alarms)
                .where(alarms.c.id == open_alarm_id)
                .values(
                    ack_status        = "CLEARED",
                    cleared_timestamp = datetime.now(timezone.utc),
                )
            )
            self._state[unit_id] = (False, None)
            log.info("[ALARM] %s alarm id=%s cleared", unit_id, open_alarm_id)

        else:
            # Steady state: just update faulted flag
            self._state[unit_id] = (is_faulted, open_alarm_id)


def _infer_fault_code(unit_id: str, tags: dict) -> str:
    """
    Derive the most likely fault code from protection trip flag tags when
    the drive model doesn't expose fault_code directly as a tag.
    """
    p = unit_id
    if tags.get(f"{p}_prot_overcurrent_trip"):   return "OVERCURRENT"
    if tags.get(f"{p}_prot_overvoltage_trip"):   return "OVERVOLTAGE"
    if tags.get(f"{p}_prot_undervoltage_trip"):  return "UNDERVOLTAGE"
    if tags.get(f"{p}_prot_thermal_trip"):       return "THERMAL_OVERLOAD"
    if tags.get(f"{p}_prot_earthfault_trip"):    return "EARTHFAULT"
    return "UNKNOWN_FAULT"


def _vibration_rms(spectrum: list) -> float:
    """Compute vibration RMS from the 32-bin spectrum array."""
    if not spectrum:
        return 0.0
    mean_sq = sum(v * v for v in spectrum) / len(spectrum)
    return math.sqrt(mean_sq)


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _build_tag_row(unit_id: str, tags: dict, now: datetime) -> dict:
    p = unit_id
    spectrum = tags.get(f"{p}_vibration_spectrum", [])
    return dict(
        timestamp       = now,
        unit_id         = unit_id,
        speed_rpm       = tags.get(f"{p}_speed_actual",  0.0),
        torque_nm       = tags.get(f"{p}_torque",         0.0),
        current_a       = tags.get(f"{p}_current",        0.0),
        power_kw        = tags.get(f"{p}_power",          0.0),
        dc_bus_voltage  = tags.get(f"{p}_dc_bus_voltage", 0.0),
        stator_temp     = tags.get(f"{p}_winding_temp",   25.0),
        rotor_temp      = tags.get(f"{p}_rotor_temp",     25.0),
        vibration_rms   = _vibration_rms(spectrum),
        belt_load_pct   = tags.get(f"{p}_material_load",  0.0),
        drive_status    = tags.get(f"{p}_status",         "STOPPED"),
    )


def _build_health_row(unit_id: str, tags: dict, now: datetime) -> dict:
    p = unit_id
    ins  = tags.get(f"{p}_insulation_health", 100.0)
    bear = tags.get(f"{p}_bearing_health",    100.0)
    return dict(
        timestamp             = now,
        unit_id               = unit_id,
        insulation_health_pct = ins,
        bearing_health_pct    = bear,
        rul_hours             = tags.get(f"{p}_rul_hours",    50000.0),
        iso10816_severity     = tags.get(f"{p}_bearing_iso",  "Good"),
        combined_health_pct   = (ins + bear) / 2.0,
    )


# ---------------------------------------------------------------------------
# Main writer task
# ---------------------------------------------------------------------------

async def persistence_writer_loop(coordinator) -> None:
    """
    Long-running asyncio task.  Runs alongside the WebSocket broadcast loop.
    Call with:  asyncio.create_task(persistence_writer_loop(coordinator))
    """
    # Ensure tables exist (idempotent)
    create_all_tables()
    engine       = get_engine()
    fault_tracker = _FaultTracker()

    health_counter = 0.0   # accumulates elapsed real-seconds for 60s health writes
    log.info("[WRITER] Persistence writer started (tag=1Hz, health=60s)")

    while True:
        await asyncio.sleep(TAG_WRITE_INTERVAL)
        health_counter += TAG_WRITE_INTERVAL

        try:
            tags = coordinator.get_all_tags()
            now  = datetime.now(timezone.utc)

            with engine.begin() as conn:
                # --- 1 Hz tag rows ---
                for unit_id in UNITS:
                    row = _build_tag_row(unit_id, tags, now)
                    conn.execute(insert(tag_readings).values(**row))

                # --- Alarm detection (every tick) ---
                for unit_id in UNITS:
                    fault_tracker.check_and_record(conn, unit_id, tags)

                # --- 60 s health snapshot ---
                if health_counter >= HEALTH_WRITE_INTERVAL:
                    for unit_id in UNITS:
                        row = _build_health_row(unit_id, tags, now)
                        conn.execute(insert(health_snapshots).values(**row))
                    health_counter = 0.0

        except Exception as exc:
            log.error("[WRITER] Write error (will retry next tick): %s", exc)


# ---------------------------------------------------------------------------
# Utility: persist a completed FAT test run (called from main.py or seeder)
# ---------------------------------------------------------------------------

def persist_fat_run(test_case_dict: dict, report_pdf_path: str = None) -> None:
    """
    Write one row to fat_test_runs from a TestCase.to_dict() payload.
    This is synchronous — call from a regular (non-async) context or
    via loop.run_in_executor for async callers.
    """
    from persistence.db import fat_test_runs
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            insert(fat_test_runs).values(
                timestamp       = datetime.now(timezone.utc),
                test_id         = test_case_dict["testId"],
                test_name       = test_case_dict["name"],
                pass_fail       = "pass" if test_case_dict.get("passed") else "fail",
                assertions_json = json.dumps(test_case_dict.get("results", [])),
                report_pdf_path = report_pdf_path,
            )
        )
    log.info(
        "[WRITER] FAT run persisted: %s %s",
        test_case_dict["testId"],
        "PASS" if test_case_dict.get("passed") else "FAIL",
    )
