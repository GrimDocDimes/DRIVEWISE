"""
DRIVEWISE — Natural Language Query Agent
Generates SQL queries from natural language, validates/runs them,
and interprets the results in natural language.
Uses Anthropic's Claude 3.5 Sonnet (claude-3-5-sonnet-20241022 or similar).
"""
import os
import re
import json
import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy import text
from anthropic import Anthropic
from persistence.db import get_engine, get_dialect

log = logging.getLogger(__name__)

import urllib.request
import urllib.error

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Routing & Configuration
# ---------------------------------------------------------------------------
def call_llm(system_prompt: str, user_question: str, temperature: float = 0.0) -> str:
    """
    Routes the LLM request to either Anthropic (if ANTHROPIC_API_KEY is set)
    or an OpenAI-compatible/Ollama endpoint (via OLLAMA_API_KEY / OPENAI_API_KEY).
    
    Reads from environment:
      - ANTHROPIC_API_KEY: if set, uses Anthropic Claude Sonnet
      - OLLAMA_API_KEY / OPENAI_API_KEY: key for local/hosted Ollama/OpenAI proxy
      - OLLAMA_API_BASE / OPENAI_API_BASE: base URL (defaults to http://localhost:11434/v1)
      - OLLAMA_MODEL / OPENAI_MODEL: model name (defaults to llama3)
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        # Use Anthropic SDK
        client = Anthropic(api_key=anthropic_key)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_question}
            ]
        )
        return message.content[0].text.strip()

    # Fallback to OpenAI / Ollama compatible endpoint
    api_key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OLLAMA_API_BASE") or os.environ.get("OPENAI_API_BASE") or "http://localhost:11434/v1"
    model = os.environ.get("OLLAMA_MODEL") or os.environ.get("OPENAI_MODEL") or "llama3"

    # Standardise the URL path
    url = api_base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    log.info("[LLM] Routing request to OpenAI/Ollama compatible endpoint: %s (Model: %s)", url, model)

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question}
        ],
        "temperature": temperature
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        log.error("[LLM] HTTP Error %d from API: %s", e.code, body)
        raise ValueError(f"LLM API returned error status {e.code}: {body}")
    except Exception as e:
        log.error("[LLM] Connection to API failed: %s", e)
        raise ConnectionError(f"Failed to connect to LLM API at {url}: {str(e)}")



# ---------------------------------------------------------------------------
# SQL Guardrail Validation
# ---------------------------------------------------------------------------
def validate_sql(sql_query: str) -> bool:
    """
    Basic guardrail to ensure only read-only SELECT queries are executed.
    Rejects modification keywords and multiple/chained statements.
    """
    # Normalize whitespaces
    q = sql_query.strip().upper()
    
    # Must start with SELECT or WITH
    if not (q.startswith("SELECT") or q.startswith("WITH")):
        return False
        
    # Check for forbidden mutation keywords
    forbidden = [
        r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b", 
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bCREATE\b", r"\bREPLACE\b",
        r"\bGRANT\b", r"\bREVOKE\b"
    ]
    for pattern in forbidden:
        if re.search(pattern, q):
            return False
            
    # Check for chained statements / SQL injection attempts
    # (e.g., semicolon followed by another instruction)
    if ";" in q:
        # A trailing semicolon is fine, but not one in the middle of text
        parts = [p.strip() for p in q.split(";")]
        # If there's more than one non-empty part, it's chained
        non_empty = [p for p in parts if p]
        if len(non_empty) > 1:
            return False
            
    return True


# ---------------------------------------------------------------------------
# System Prompt & DDL Schema Context
# ---------------------------------------------------------------------------
def _get_system_prompt(dialect: str) -> str:
    return f"""You are an expert industrial data analyst and SQL database engineer specializing in power transmission systems, variable speed drives (VFDs), and motor reliability.
Your task is to convert natural language questions about telemetry data, alarms, health scores, and factory acceptance test (FAT) runs into a SINGLE read-only SQL query.

The target database dialect is: {dialect.upper()}. 
You must output ONLY valid {dialect.upper()} SQL.

Here is the database schema:

---
Table: tag_readings
Columns:
- id (BIGINT, Primary Key)
- timestamp (TIMESTAMP / DATETIME)
- unit_id (VARCHAR(4)) - Represents drive section ('S1', 'S2', 'S3')
- speed_rpm (FLOAT) - Motor actual speed in RPM
- torque_nm (FLOAT) - Motor torque in Nm
- current_a (FLOAT) - Motor current in Amperes
- power_kw (FLOAT) - Motor active power in kW
- dc_bus_voltage (FLOAT) - DC Link Voltage in Volts
- stator_temp (FLOAT) - Stator winding temperature in Celsius
- rotor_temp (FLOAT) - Rotor temperature in Celsius
- vibration_rms (FLOAT) - Motor vibration RMS in mm/s
- belt_load_pct (FLOAT) - Conveyor material load percentage (0 to 100)
- drive_status (VARCHAR(16)) - VFD state ('RUNNING', 'STOPPED', 'FAULT', 'STARTING')

Table: alarms
Columns:
- id (BIGINT, Primary Key)
- timestamp (TIMESTAMP / DATETIME) - Time when alarm was raised
- unit_id (VARCHAR(4)) - 'S1', 'S2', or 'S3'
- alarm_code (VARCHAR(32)) - 'OVERCURRENT', 'OVERVOLTAGE', 'UNDERVOLTAGE', 'THERMAL_OVERLOAD', 'EARTHFAULT'
- priority (VARCHAR(16)) - 'CRITICAL', 'HIGH', or 'MEDIUM'
- category (VARCHAR(16)) - 'PROTECTION' or 'THERMAL'
- description (TEXT) - Alarm detail
- ack_status (VARCHAR(16)) - 'ACTIVE' or 'CLEARED'
- cleared_timestamp (TIMESTAMP / DATETIME) - Time when alarm cleared (nullable)

Table: health_snapshots
Columns:
- id (BIGINT, Primary Key)
- timestamp (TIMESTAMP / DATETIME) - Sample timestamp (every 60 seconds)
- unit_id (VARCHAR(4)) - 'S1', 'S2', or 'S3'
- insulation_health_pct (FLOAT) - Winding insulation remaining life % (100 is pristine)
- bearing_health_pct (FLOAT) - Bearing mechanical health % (100 is pristine)
- rul_hours (FLOAT) - Remaining Useful Life estimate in hours
- iso10816_severity (VARCHAR(16)) - Vibration classification ('Good', 'Satisfactory', 'Unsatisfactory', 'Unacceptable')
- combined_health_pct (FLOAT) - Average health score of insulation and bearing (0 to 100)

Table: fat_test_runs
Columns:
- id (BIGINT, Primary Key)
- timestamp (TIMESTAMP / DATETIME) - Test run execution time
- test_id (VARCHAR(8)) - 'TC001', 'TC002', 'TC003', 'TC004', 'TC005', or 'TC006'
- test_name (TEXT) - Case title
- pass_fail (VARCHAR(8)) - 'pass' or 'fail'
- assertions_json (TEXT) - JSON-formatted validation details
- report_pdf_path (TEXT) - File path to local PDF summary (nullable)
---

DIALECT DIFFERENCES RULES:
1. To subtract minutes or hours from a timestamp:
   - For POSTGRESQL: Use `timestamp - INTERVAL 'N minutes'` or `timestamp - INTERVAL 'N hours'`
   - For SQLITE: Use `datetime(timestamp, '-N minutes')` or `datetime(timestamp, '-N hours')`
2. To extract epoch (total seconds) from a timestamp difference:
   - For POSTGRESQL: Use `EXTRACT(EPOCH FROM (ts1 - ts2))`
   - For SQLITE: Use `(strftime('%s', ts1) - strftime('%s', ts2))`
3. To extract dates:
   - For POSTGRESQL: Use `timestamp::date` or `CAST(timestamp AS DATE)`
   - For SQLITE: Use `date(timestamp)`

QUERY EXAMPLES:
- Q: "Which drive had the most overcurrent trips this week?"
  SQL ({dialect}):
  {"postgresql": "SELECT unit_id, COUNT(*) as trip_count FROM alarms WHERE alarm_code = 'OVERCURRENT' AND timestamp >= NOW() - INTERVAL '7 days' GROUP BY unit_id ORDER BY trip_count DESC LIMIT 1;", "sqlite": "SELECT unit_id, COUNT(*) as trip_count FROM alarms WHERE alarm_code = 'OVERCURRENT' AND timestamp >= datetime('now', '-7 days') GROUP BY unit_id ORDER BY trip_count DESC LIMIT 1;"}[dialect]
  
- Q: "Show S2's temperature trend during the last thermal alarm"
  SQL ({dialect}):
  {"postgresql": "WITH last_alarm AS (SELECT timestamp, cleared_timestamp FROM alarms WHERE unit_id = 'S2' AND alarm_code = 'THERMAL_OVERLOAD' ORDER BY timestamp DESC LIMIT 1) SELECT t.timestamp, t.stator_temp, t.rotor_temp FROM tag_readings t, last_alarm la WHERE t.unit_id = 'S2' AND t.timestamp BETWEEN la.timestamp - INTERVAL '15 minutes' AND COALESCE(la.cleared_timestamp, NOW()) ORDER BY t.timestamp ASC;", "sqlite": "WITH last_alarm AS (SELECT timestamp, cleared_timestamp FROM alarms WHERE unit_id = 'S2' AND alarm_code = 'THERMAL_OVERLOAD' ORDER BY timestamp DESC LIMIT 1) SELECT t.timestamp, t.stator_temp, t.rotor_temp FROM tag_readings t, last_alarm la WHERE t.unit_id = 'S2' AND t.timestamp BETWEEN datetime(la.timestamp, '-15 minutes') AND COALESCE(la.cleared_timestamp, datetime('now')) ORDER BY t.timestamp ASC;"}[dialect]

You must output ONLY a JSON object containing the compiled SQL query, a suitable visualization suggestion ('line' for time-series trends, 'bar' for categories/aggregates, or 'none'), and a technical explanation.
Output format:
{{
  "sql": "your SQL query goes here",
  "chart_type": "line" | "bar" | "none",
  "explanation": "brief overview of the SQL logic"
}}

Ensure no extra text, backticks, or markdown blocks surround the JSON payload. Returning valid, clean JSON is absolute.
"""


# ---------------------------------------------------------------------------
# Natural Language Query Agent Class
# ---------------------------------------------------------------------------
class NLQueryAgent:
    def __init__(self):
        self.engine = get_engine()
        self.dialect = get_dialect()
    def _call_llm_json(self, system_prompt: str, user_question: str) -> dict:
        """Call LLM to generate the query JSON."""
        prompt = f"Translate this question into the JSON format containing the SQL query: '{user_question}'"
        text_content = call_llm(system_prompt, prompt, temperature=0.0)
        
        # Parse the JSON response
        # Clean any accidental markdown code fences
        if text_content.startswith("```json"):
            text_content = text_content[7:]
        if text_content.endswith("```"):
            text_content = text_content[:-3]
        text_content = text_content.strip()
        
        return json.loads(text_content)

    def _execute_query(self, sql_query: str) -> pd.DataFrame:
        """Execute query safely and return pandas DataFrame."""
        if not validate_sql(sql_query):
            raise PermissionError("SQL validation failed. Only SELECT statements are permitted, and chained statements are blocked.")
            
        with self.engine.connect() as conn:
            df = pd.read_sql_query(text(sql_query), conn)
        return df

    def _generate_narrative_answer(self, question: str, sql_query: str, df: pd.DataFrame) -> str:
        """Use LLM to generate a concise, natural-language response based on actual data results."""
        # Limit rows passed to LLM to prevent context overflow
        data_summary = df.head(50).to_string()
        if len(df) > 50:
            data_summary += f"\n... (truncated {len(df) - 50} more rows)"
            
        system_prompt = "You are the DRIVEWISE GenAI Agent. Respond to the operator's question using only the provided database query results. Keep your explanation concise, technically accurate, and focused directly on what the data shows. Do not speculate beyond the data."
        user_msg = f"""Operator Question: {question}
Executed SQL: {sql_query}
Query Results (up to 50 rows):
{data_summary}

Please provide the final natural language answer to the operator:"""

        return call_llm(system_prompt, user_msg, temperature=0.2)

    def query(self, question: str) -> dict:
        """
        Processes a natural language question.
        Returns:
            dict: {
                "question": str,
                "sql": str,
                "chart_type": str,
                "data": list[dict],
                "answer": str
            }
        """
        system_prompt = _get_system_prompt(self.dialect)
        
        # Phase 3 - Step 1: Get LLM translation
        try:
            agent_plan = self._call_llm_json(system_prompt, question)
        except Exception as e:
            log.error("LLM translation failed: %s", e)
            return {
                "question": question,
                "sql": "",
                "chart_type": "none",
                "data": [],
                "answer": f"Error interacting with the AI Agent: {str(e)}"
            }
            
        sql = agent_plan.get("sql", "").strip()
        chart_type = agent_plan.get("chart_type", "none")
        
        if not sql:
            return {
                "question": question,
                "sql": "",
                "chart_type": "none",
                "data": [],
                "answer": "The agent was unable to formulate a SQL query for this question."
            }

        # Phase 3 - Step 3: Execute SQL with error self-correction retry
        try:
            log.info("Executing query: %s", sql)
            df = self._execute_query(sql)
        except Exception as first_error:
            log.warning("SQL execution failed. Attempting self-correction: %s", first_error)
            
            # Formulate correction prompt
            correction_prompt = f"""{system_prompt}
            
CRITICAL: The previous SQL query you generated failed with an error.
Generated SQL: {sql}
Database Error: {str(first_error)}

Analyze the error, correct any dialect syntax issues, column names, table names, joins, or expressions, and return the CORRECTED JSON payload."""

            try:
                agent_plan = self._call_llm_json(correction_prompt, question)
                sql = agent_plan.get("sql", "").strip()
                chart_type = agent_plan.get("chart_type", "none")
                log.info("Executing corrected query: %s", sql)
                df = self._execute_query(sql)
            except Exception as second_error:
                log.error("Correction failed: %s", second_error)
                return {
                    "question": question,
                    "sql": sql,
                    "chart_type": "none",
                    "data": [],
                    "answer": f"Database Query Error: {str(second_error)}\nOriginal Error: {str(first_error)}"
                }

        # Format DataFrame results into standard JSON serializable dict list
        # Handle datetime serialization nicely
        data_records = json.loads(df.to_json(orient="records", date_format="iso"))
        
        # Phase 3 - Step 4: Interpret results
        try:
            answer = self._generate_narrative_answer(question, sql, df)
        except Exception as e:
            log.error("Narrative generation failed: %s", e)
            answer = f"Successfully queried the database and found {len(df)} results, but failed to generate summary explanation: {str(e)}"
            
        return {
            "question": question,
            "sql": sql,
            "chart_type": chart_type,
            "data": data_records,
            "answer": answer
        }
