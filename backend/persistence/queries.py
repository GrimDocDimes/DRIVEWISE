"""
DRIVEWISE — Advanced SQL Query Library
Contains parameterized, reusable queries returning pandas DataFrames.
Demonstrates window functions, state-change gap detection (LAG/LEAD),
alarm frequencies, degradation rates, and multi-table self-joins / CTEs.

Compatible with both PostgreSQL and SQLite backends.
"""
import pandas as pd
from datetime import datetime
from sqlalchemy import text
from persistence.db import get_engine, get_dialect

# ---------------------------------------------------------------------------
# Query 1: Rolling 1-Hour Average (Window Function)
# ---------------------------------------------------------------------------
def rolling_avg_speed_torque_current(unit_id: str, start_time: datetime, end_time: datetime, window_seconds: int = 3600) -> pd.DataFrame:
    """
    Computes rolling averages for speed, torque, and current for a specific drive unit
    using SQL window functions (moving average over preceding time window).
    
    Raw SQL:
    \"\"\"
    SELECT 
        timestamp,
        speed_rpm,
        AVG(speed_rpm) OVER (
            ORDER BY timestamp 
            RANGE BETWEEN INTERVAL '3600 seconds' PRECEDING AND CURRENT ROW
        ) AS rolling_avg_speed,
        torque_nm,
        AVG(torque_nm) OVER (
            ORDER BY timestamp 
            RANGE BETWEEN INTERVAL '3600 seconds' PRECEDING AND CURRENT ROW
        ) AS rolling_avg_torque,
        current_a,
        AVG(current_a) OVER (
            ORDER BY timestamp 
            RANGE BETWEEN INTERVAL '3600 seconds' PRECEDING AND CURRENT ROW
        ) AS rolling_avg_current
    FROM tag_readings
    WHERE unit_id = :unit_id 
      AND timestamp BETWEEN :start_time AND :end_time
    ORDER BY timestamp ASC;
    \"\"\"
    """
    engine = get_engine()
    dialect = get_dialect()
    
    if dialect == "postgresql":
        query = text(f"""
            SELECT 
                timestamp,
                speed_rpm,
                AVG(speed_rpm) OVER (
                    ORDER BY timestamp 
                    RANGE BETWEEN INTERVAL '{window_seconds} seconds' PRECEDING AND CURRENT ROW
                ) AS rolling_avg_speed,
                torque_nm,
                AVG(torque_nm) OVER (
                    ORDER BY timestamp 
                    RANGE BETWEEN INTERVAL '{window_seconds} seconds' PRECEDING AND CURRENT ROW
                ) AS rolling_avg_torque,
                current_a,
                AVG(current_a) OVER (
                    ORDER BY timestamp 
                    RANGE BETWEEN INTERVAL '{window_seconds} seconds' PRECEDING AND CURRENT ROW
                ) AS rolling_avg_current
            FROM tag_readings
            WHERE unit_id = :unit_id 
              AND timestamp BETWEEN :start_time AND :end_time
            ORDER BY timestamp ASC
        """)
    else:
        # SQLite fallback: since SQLite doesn't natively support datetime RANGE offsets
        # easily in older versions, we fallback to ROWS windowing, or standard ROWS windowing
        # assuming 1Hz downsampled data (1 row per second = window_seconds rows)
        query = text(f"""
            SELECT 
                timestamp,
                speed_rpm,
                AVG(speed_rpm) OVER (
                    ORDER BY timestamp 
                    ROWS BETWEEN {window_seconds} PRECEDING AND CURRENT ROW
                ) AS rolling_avg_speed,
                torque_nm,
                AVG(torque_nm) OVER (
                    ORDER BY timestamp 
                    ROWS BETWEEN {window_seconds} PRECEDING AND CURRENT ROW
                ) AS rolling_avg_torque,
                current_a,
                AVG(current_a) OVER (
                    ORDER BY timestamp 
                    ROWS BETWEEN {window_seconds} PRECEDING AND CURRENT ROW
                ) AS rolling_avg_current
            FROM tag_readings
            WHERE unit_id = :unit_id 
              AND timestamp BETWEEN :start_time AND :end_time
            ORDER BY timestamp ASC
        """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query, 
            conn, 
            params={"unit_id": unit_id, "start_time": start_time, "end_time": end_time}
        )
    return df


# ---------------------------------------------------------------------------
# Query 2: Downtime Duration (State-Change / Gap Detection)
# ---------------------------------------------------------------------------
def downtime_duration(unit_id: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """
    Detects continuous downtime intervals (non-RUNNING state gaps) using LAG and
    a state-change accumulation technique to group contiguous periods.
    
    Raw SQL:
    \"\"\"
    WITH StatusChanges AS (
        SELECT 
            timestamp,
            drive_status,
            CASE 
                -- Mark 1 if state changes, otherwise 0
                WHEN LAG(drive_status) OVER (ORDER BY timestamp) = drive_status THEN 0
                ELSE 1 
            END AS is_change
        FROM tag_readings
        WHERE unit_id = :unit_id 
          AND timestamp BETWEEN :start_time AND :end_time
    ),
    GroupedStates AS (
        SELECT 
            timestamp,
            drive_status,
            -- Cumulative sum of changes creates a unique group ID for each contiguous state run
            SUM(is_change) OVER (ORDER BY timestamp) AS state_group_id
        FROM StatusChanges
    )
    SELECT 
        drive_status,
        MIN(timestamp) AS start_timestamp,
        MAX(timestamp) AS end_timestamp,
        -- Duration in seconds
        EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) AS duration_seconds
    FROM GroupedStates
    WHERE drive_status != 'RUNNING'
    GROUP BY state_group_id, drive_status
    ORDER BY start_timestamp ASC;
    \"\"\"
    """
    engine = get_engine()
    dialect = get_dialect()
    
    if dialect == "postgresql":
        query = text("""
            WITH StatusChanges AS (
                SELECT 
                    timestamp,
                    drive_status,
                    CASE 
                        WHEN LAG(drive_status) OVER (ORDER BY timestamp) = drive_status THEN 0
                        ELSE 1 
                    END AS is_change
                FROM tag_readings
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            ),
            GroupedStates AS (
                SELECT 
                    timestamp,
                    drive_status,
                    SUM(is_change) OVER (ORDER BY timestamp) AS state_group_id
                FROM StatusChanges
            )
            SELECT 
                drive_status,
                MIN(timestamp) AS start_timestamp,
                MAX(timestamp) AS end_timestamp,
                EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) AS duration_seconds
            FROM GroupedStates
            WHERE drive_status != 'RUNNING'
            GROUP BY state_group_id, drive_status
            ORDER BY start_timestamp ASC
        """)
    else:
        # SQLite fallback: use strftime/julianday for durations
        query = text("""
            WITH StatusChanges AS (
                SELECT 
                    timestamp,
                    drive_status,
                    CASE 
                        WHEN LAG(drive_status) OVER (ORDER BY timestamp) = drive_status THEN 0
                        ELSE 1 
                    END AS is_change
                FROM tag_readings
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            ),
            GroupedStates AS (
                SELECT 
                    timestamp,
                    drive_status,
                    SUM(is_change) OVER (ORDER BY timestamp) AS state_group_id
                FROM StatusChanges
            )
            SELECT 
                drive_status,
                MIN(timestamp) AS start_timestamp,
                MAX(timestamp) AS end_timestamp,
                (strftime('%s', MAX(timestamp)) - strftime('%s', MIN(timestamp))) AS duration_seconds
            FROM GroupedStates
            WHERE drive_status != 'RUNNING'
            GROUP BY state_group_id, drive_status
            ORDER BY start_timestamp ASC
        """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query, 
            conn, 
            params={"unit_id": unit_id, "start_time": start_time, "end_time": end_time}
        )
    return df


# ---------------------------------------------------------------------------
# Query 3: Alarm Frequency & MTBA (Mean Time Between Alarms)
# ---------------------------------------------------------------------------
def alarm_frequency_mtba(unit_id: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """
    Computes alarm frequencies and MTBA (Mean Time Between Alarms) grouped by alarm category/code.
    Calculates the gap between consecutive alarms to find the average time between them.
    """
    engine = get_engine()
    dialect = get_dialect()
    
    if dialect == "postgresql":
        query = text("""
            WITH OrderedAlarms AS (
                SELECT 
                    unit_id,
                    alarm_code,
                    category,
                    timestamp,
                    LAG(timestamp) OVER (PARTITION BY unit_id ORDER BY timestamp) AS prev_timestamp
                FROM alarms
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            ),
            AlarmIntervals AS (
                SELECT 
                    alarm_code,
                    category,
                    EXTRACT(EPOCH FROM (timestamp - prev_timestamp)) AS interval_seconds
                FROM OrderedAlarms
                WHERE prev_timestamp IS NOT NULL
            )
            SELECT 
                a.alarm_code,
                a.category,
                COUNT(a.timestamp) AS alarm_count,
                COALESCE(AVG(i.interval_seconds) / 3600.0, 0.0) AS mtba_hours
            FROM OrderedAlarms a
            LEFT JOIN AlarmIntervals i ON a.alarm_code = i.alarm_code AND a.category = i.category
            GROUP BY a.alarm_code, a.category
            ORDER BY alarm_count DESC
        """)
    else:
        query = text("""
            WITH OrderedAlarms AS (
                SELECT 
                    unit_id,
                    alarm_code,
                    category,
                    timestamp,
                    LAG(timestamp) OVER (PARTITION BY unit_id ORDER BY timestamp) AS prev_timestamp
                FROM alarms
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            ),
            AlarmIntervals AS (
                SELECT 
                    alarm_code,
                    category,
                    (strftime('%s', timestamp) - strftime('%s', prev_timestamp)) AS interval_seconds
                FROM OrderedAlarms
                WHERE prev_timestamp IS NOT NULL
            )
            SELECT 
                a.alarm_code,
                a.category,
                COUNT(a.timestamp) AS alarm_count,
                COALESCE(AVG(i.interval_seconds) / 3600.0, 0.0) AS mtba_hours
            FROM OrderedAlarms a
            LEFT JOIN AlarmIntervals i ON a.alarm_code = i.alarm_code AND a.category = i.category
            GROUP BY a.alarm_code, a.category
            ORDER BY alarm_count DESC
        """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query, 
            conn, 
            params={"unit_id": unit_id, "start_time": start_time, "end_time": end_time}
        )
    return df


# ---------------------------------------------------------------------------
# Query 4: Health Degradation Trend
# ---------------------------------------------------------------------------
def health_trend_degradation(unit_id: str, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """
    Computes linear degradation rate (% health lost per day) over a window.
    Calculates first/last values difference divided by total days elapsed to get a stable trend.
    """
    engine = get_engine()
    dialect = get_dialect()
    
    if dialect == "postgresql":
        query = text("""
            WITH HealthStats AS (
                SELECT 
                    timestamp,
                    insulation_health_pct,
                    bearing_health_pct,
                    combined_health_pct,
                    FIRST_VALUE(combined_health_pct) OVER (ORDER BY timestamp ASC) AS first_val,
                    LAST_VALUE(combined_health_pct) OVER (ORDER BY timestamp ASC RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_val,
                    FIRST_VALUE(timestamp) OVER (ORDER BY timestamp ASC) AS first_ts,
                    LAST_VALUE(timestamp) OVER (ORDER BY timestamp ASC RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_ts
                FROM health_snapshots
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            )
            SELECT 
                :unit_id AS unit_id,
                MAX(first_val) AS initial_health,
                MAX(last_val) AS current_health,
                MAX(first_val) - MAX(last_val) AS total_degradation,
                CASE 
                    WHEN EXTRACT(EPOCH FROM (MAX(last_ts) - MAX(first_ts))) > 0
                    THEN ((MAX(first_val) - MAX(last_val)) / (EXTRACT(EPOCH FROM (MAX(last_ts) - MAX(first_ts))) / 86400.0))
                    ELSE 0.0
                END AS degradation_rate_pct_per_day
            FROM HealthStats
        """)
    else:
        query = text("""
            WITH HealthStats AS (
                SELECT 
                    timestamp,
                    combined_health_pct,
                    (SELECT combined_health_pct FROM health_snapshots WHERE unit_id = :unit_id AND timestamp BETWEEN :start_time AND :end_time ORDER BY timestamp ASC LIMIT 1) AS first_val,
                    (SELECT combined_health_pct FROM health_snapshots WHERE unit_id = :unit_id AND timestamp BETWEEN :start_time AND :end_time ORDER BY timestamp DESC LIMIT 1) AS last_val,
                    (SELECT timestamp FROM health_snapshots WHERE unit_id = :unit_id AND timestamp BETWEEN :start_time AND :end_time ORDER BY timestamp ASC LIMIT 1) AS first_ts,
                    (SELECT timestamp FROM health_snapshots WHERE unit_id = :unit_id AND timestamp BETWEEN :start_time AND :end_time ORDER BY timestamp DESC LIMIT 1) AS last_ts
                FROM health_snapshots
                WHERE unit_id = :unit_id 
                  AND timestamp BETWEEN :start_time AND :end_time
            )
            SELECT 
                :unit_id AS unit_id,
                MAX(first_val) AS initial_health,
                MAX(last_val) AS current_health,
                MAX(first_val) - MAX(last_val) AS total_degradation,
                CASE 
                    WHEN (strftime('%s', MAX(last_ts)) - strftime('%s', MAX(first_ts))) > 0
                    THEN ((MAX(first_val) - MAX(last_val)) / ((strftime('%s', MAX(last_ts)) - strftime('%s', MAX(first_ts))) / 86400.0))
                    ELSE 0.0
                END AS degradation_rate_pct_per_day
            FROM HealthStats
            LIMIT 1
        """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query, 
            conn, 
            params={"unit_id": unit_id, "start_time": start_time, "end_time": end_time}
        )
    return df


# ---------------------------------------------------------------------------
# Query 5: Correlation Surface (Alarms near Health Drops)
# ---------------------------------------------------------------------------
def alarm_health_correlation(unit_id: str, health_threshold: float, window_minutes: int, start_time: datetime, end_time: datetime) -> pd.DataFrame:
    """
    Self-joins and CTEs to locate alarms that occurred within N minutes of
    health snapshots dropping below a threshold.
    """
    engine = get_engine()
    dialect = get_dialect()
    
    if dialect == "postgresql":
        query = text(f"""
            WITH LowHealth AS (
                SELECT 
                    timestamp AS health_timestamp,
                    combined_health_pct,
                    insulation_health_pct,
                    bearing_health_pct
                FROM health_snapshots
                WHERE unit_id = :unit_id 
                  AND combined_health_pct < :health_threshold
                  AND timestamp BETWEEN :start_time AND :end_time
            )
            SELECT 
                h.health_timestamp,
                h.combined_health_pct,
                a.timestamp AS alarm_timestamp,
                a.alarm_code,
                a.category,
                a.description,
                EXTRACT(EPOCH FROM (a.timestamp - h.health_timestamp)) / 60.0 AS time_difference_minutes
            FROM LowHealth h
            JOIN alarms a ON a.unit_id = :unit_id
              AND a.timestamp BETWEEN (h.health_timestamp - INTERVAL '{window_minutes} minutes') 
                                  AND (h.health_timestamp + INTERVAL '{window_minutes} minutes')
            ORDER BY h.health_timestamp ASC, a.timestamp ASC
        """)
    else:
        query = text(f"""
            WITH LowHealth AS (
                SELECT 
                    timestamp AS health_timestamp,
                    combined_health_pct,
                    insulation_health_pct,
                    bearing_health_pct
                FROM health_snapshots
                WHERE unit_id = :unit_id 
                  AND combined_health_pct < :health_threshold
                  AND timestamp BETWEEN :start_time AND :end_time
            )
            SELECT 
                h.health_timestamp,
                h.combined_health_pct,
                a.timestamp AS alarm_timestamp,
                a.alarm_code,
                a.category,
                a.description,
                (strftime('%s', a.timestamp) - strftime('%s', h.health_timestamp)) / 60.0 AS time_difference_minutes
            FROM LowHealth h
            JOIN alarms a ON a.unit_id = :unit_id
              AND strftime('%s', a.timestamp) BETWEEN (strftime('%s', h.health_timestamp) - {window_minutes} * 60)
                                                 AND (strftime('%s', h.health_timestamp) + {window_minutes} * 60)
            ORDER BY h.health_timestamp ASC, a.timestamp ASC
        """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(
            query, 
            conn, 
            params={"unit_id": unit_id, "health_threshold": health_threshold, "start_time": start_time, "end_time": end_time}
        )
    return df


# ---------------------------------------------------------------------------
# Query 6: FAT Test Pass Rate Over Time
# ---------------------------------------------------------------------------
def fat_pass_rate_over_time() -> pd.DataFrame:
    """
    Aggregates test run outcomes over time, providing cumulative and daily pass rates.
    """
    engine = get_engine()
    
    # Simple query since we don't have heavy dialect variance for test records
    query = text("""
        SELECT 
            test_id,
            test_name,
            COUNT(*) AS total_runs,
            SUM(CASE WHEN pass_fail = 'pass' THEN 1 ELSE 0 END) AS passed_runs,
            (CAST(SUM(CASE WHEN pass_fail = 'pass' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) * 100.0 AS pass_rate_pct,
            MIN(timestamp) AS first_run,
            MAX(timestamp) AS last_run
        FROM fat_test_runs
        GROUP BY test_id, test_name
        ORDER BY test_id ASC
    """)
        
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return df
