"""
DRIVEWISE — Persistence DB Layer
SQLAlchemy Core schema definition + engine factory.

Tries PostgreSQL first (reads DATABASE_URL env var).
Falls back to SQLite at backend/drivewise.db if Postgres is unavailable.

Usage:
    from persistence.db import get_engine, get_metadata, create_all_tables
    engine = get_engine()
"""
import os
import logging

from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    Integer, BigInteger, Float, String, Text, DateTime, Boolean,
    Index, text
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine singleton
# ---------------------------------------------------------------------------
_engine = None
_metadata = MetaData()
_db_dialect = None   # 'postgresql' or 'sqlite'


def get_engine():
    """Return the SQLAlchemy engine, creating it on first call."""
    global _engine, _db_dialect
    if _engine is not None:
        return _engine

    # --- Try PostgreSQL first ---
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://localhost/drivewise"
    )

    if not db_url.startswith("sqlite"):
        try:
            import psycopg2  # noqa: F401  (triggers ImportError on NixOS if missing)
            eng = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                echo=False,
            )
            # Probe the connection
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            _engine = eng
            _db_dialect = "postgresql"
            log.info("[DB] Connected to PostgreSQL: %s", db_url)
            return _engine
        except Exception as exc:
            log.warning(
                "[DB] PostgreSQL unavailable (%s). Falling back to SQLite.", exc
            )

    # --- SQLite fallback ---
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "drivewise.db",
    )
    sqlite_url = f"sqlite:///{db_path}"
    _engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    _db_dialect = "sqlite"
    log.info("[DB] Connected to SQLite: %s", db_path)

    # Enable WAL mode for concurrent readers (writer.py + agent queries)
    with _engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA cache_size=-32768"))   # 32 MB page cache

    return _engine


def get_dialect() -> str:
    """Return 'postgresql' or 'sqlite' for dialect-specific SQL."""
    get_engine()  # ensure initialised
    return _db_dialect


def get_metadata() -> MetaData:
    return _metadata


# ---------------------------------------------------------------------------
# Schema definition — SQLAlchemy Core (explicit, interview-transparent)
# ---------------------------------------------------------------------------

# tag_readings — 1 row / second / unit
# Downsampled from the 10 Hz simulation tick by the async writer.
tag_readings = Table(
    "tag_readings",
    _metadata,
    Column("id",             Integer,    primary_key=True, autoincrement=True),
    Column("timestamp",      DateTime,   nullable=False),
    Column("unit_id",        String(4),  nullable=False),   # S1 / S2 / S3
    # Drive electrical
    Column("speed_rpm",      Float,      nullable=False),
    Column("torque_nm",      Float,      nullable=False),
    Column("current_a",      Float,      nullable=False),
    Column("power_kw",       Float,      nullable=False),
    Column("dc_bus_voltage", Float,      nullable=False),
    # Motor thermal
    Column("stator_temp",    Float,      nullable=False),   # winding_temp
    Column("rotor_temp",     Float,      nullable=False),
    # Mechanical
    Column("vibration_rms",  Float,      nullable=False),   # sqrt(mean(spectrum²))
    Column("belt_load_pct",  Float,      nullable=False),   # material_load
    Column("drive_status",   String(16), nullable=False),   # RUNNING/STOPPED/FAULT
    # Indexes for common query patterns
    Index("ix_tag_unit_ts", "unit_id", "timestamp"),
    Index("ix_tag_ts",      "timestamp"),
)

# alarms — ISA-18.2 lifecycle
# One row per alarm activation event.  State transitions (ACTIVE → ACK → CLEARED)
# are represented by updating ack_status + cleared_timestamp in-place.
alarms = Table(
    "alarms",
    _metadata,
    Column("id",                Integer,     primary_key=True, autoincrement=True),
    Column("timestamp",         DateTime,    nullable=False),    # raised_at
    Column("unit_id",           String(4),   nullable=False),
    Column("alarm_code",        String(32),  nullable=False),    # OVERCURRENT, THERMAL_OVERLOAD …
    Column("priority",          String(16),  nullable=False),    # CRITICAL / HIGH / MEDIUM
    Column("category",          String(16),  nullable=False),    # PROTECTION / THERMAL / MECHANICAL
    Column("description",       Text,        nullable=False),
    Column("ack_status",        String(16),  nullable=False, default="ACTIVE"),
    Column("cleared_timestamp", DateTime,    nullable=True),
    Index("ix_alarms_unit_ts",  "unit_id", "timestamp"),
    Index("ix_alarms_code",     "alarm_code"),
)

# health_snapshots — sampled every 60 s per unit
# Used for trend analysis and health-alarm correlation queries.
health_snapshots = Table(
    "health_snapshots",
    _metadata,
    Column("id",                  Integer,    primary_key=True, autoincrement=True),
    Column("timestamp",           DateTime,   nullable=False),
    Column("unit_id",             String(4),  nullable=False),
    Column("insulation_health_pct", Float,    nullable=False),   # insulation_health
    Column("bearing_health_pct",  Float,      nullable=False),   # bearing.health
    Column("rul_hours",           Float,      nullable=False),   # remaining_useful_life_hours
    Column("iso10816_severity",   String(16), nullable=False),   # Good/Satisfactory/…
    Column("combined_health_pct", Float,      nullable=False),   # avg(insulation, bearing)
    Index("ix_health_unit_ts",    "unit_id", "timestamp"),
)

# fat_test_runs — one row per test-case execution
# assertions_json stores the full list from TestCase.to_dict()['results'].
fat_test_runs = Table(
    "fat_test_runs",
    _metadata,
    Column("id",              Integer,    primary_key=True, autoincrement=True),
    Column("timestamp",       DateTime,   nullable=False),
    Column("test_id",         String(8),  nullable=False),   # TC001 … TC006
    Column("test_name",       Text,       nullable=False),
    Column("pass_fail",       String(8),  nullable=False),   # pass / fail
    Column("assertions_json", Text,       nullable=False),   # JSON string (portable)
    Column("report_pdf_path", Text,       nullable=True),
    Index("ix_fat_test_id",   "test_id"),
    Index("ix_fat_ts",        "timestamp"),
)


def create_all_tables():
    """Create all tables if they don't already exist."""
    engine = get_engine()
    _metadata.create_all(engine, checkfirst=True)
    log.info("[DB] Schema ready (dialect=%s)", _db_dialect)


# ---------------------------------------------------------------------------
# Priority / category mapping for alarm codes
# ---------------------------------------------------------------------------
ALARM_META = {
    "OVERCURRENT":      ("CRITICAL", "PROTECTION",  "Overcurrent protection trip — IEC 60255 inverse time"),
    "OVERVOLTAGE":      ("CRITICAL", "PROTECTION",  "DC bus overvoltage trip"),
    "UNDERVOLTAGE":     ("HIGH",     "PROTECTION",  "Supply undervoltage below ride-through threshold"),
    "THERMAL_OVERLOAD": ("CRITICAL", "THERMAL",     "Motor winding temperature exceeded class-F limit (155 °C)"),
    "EARTHFAULT":       ("CRITICAL", "PROTECTION",  "Earth fault — residual current above threshold"),
}

def alarm_meta(code: str):
    """Return (priority, category, description) for an alarm code."""
    return ALARM_META.get(
        code,
        ("MEDIUM", "PROTECTION", f"Drive fault: {code}")
    )
