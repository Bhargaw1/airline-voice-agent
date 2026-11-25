"""
Dynamic structured-data flow (no hardcoded SQL anywhere):
Pure SQL Microservice Pipeline.

question -> LLM writes T-SQL -> execute_query (read-only guardrails) -> LLM writes spoken answer
"""
import os
import re
import sys
import json
import time
import logging
import pandas as pd
from typing import Optional
from sqlalchemy import text
from openai import AzureOpenAI, BadRequestError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *  # engine, AZURE_OPENAI_*, GPT4_LLM_MODEL_DEPLOYMENT_NAME

logger = logging.getLogger(__name__)

TABLE = "dbo.voice_agent_data"
MODEL = GPT4_LLM_MODEL_DEPLOYMENT_NAME
EFFORT = os.getenv("SQL_FLOW_REASONING_EFFORT", "minimal")
MAX_ROWS = int(os.getenv("SQL_FLOW_MAX_ROWS", "50"))
SCHEMA_TTL = 600
VOICE_FAST = os.getenv("SQL_VOICE_FAST", "true").lower() in ("1", "true", "yes")
ZERO_ROW_RETRY = os.getenv("SQL_FLOW_ZERO_ROW_RETRY", "false").lower() in ("1", "true", "yes")
LIGHT_SCHEMA = os.getenv("SQL_LIGHT_SCHEMA", "true").lower() in ("1", "true", "yes")
FLIGHT_CACHE_TTL = float(os.getenv("FLIGHT_CACHE_TTL_SECONDS", "60"))
_FLIGHT_CACHE: dict[str, tuple[float, list, str]] = {}

_FLIGHT_COLS = (
    "flight_number, airline, origin, destination, flight_date, departure_time, arrival_time, "
    "flight_status, booking_status, available_seats, total_fare_inr, currency"
)
_IST_TODAY = "CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE)"

_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_API_BASE,
)

# City-name -> IATA mapping prompt hint. NOT used to build queries in Python.
AIRPORT_ALIASES = {
    "bengaluru": "BLR", "bangalore": "BLR", "blr": "BLR",
    "delhi": "DEL", "new delhi": "DEL", "del": "DEL",
    "mumbai": "BOM", "bombay": "BOM", "bom": "BOM",
    "chennai": "MAA", "madras": "MAA", "maa": "MAA",
    "kolkata": "CCU", "calcutta": "CCU", "ccu": "CCU",
    "hyderabad": "HYD", "hyd": "HYD",
    "pune": "PNQ", "pnq": "PNQ",
    "ahmedabad": "AMD", "amd": "AMD",
    "jaipur": "JAI", "jai": "JAI",
    "kochi": "COK", "cochin": "COK", "cok": "COK",
    "goa": "GOI", "goi": "GOI",
    "lucknow": "LKO", "lko": "LKO",
    "dubai": "DXB", "dxb": "DXB",
    "london": "LHR", "lhr": "LHR",
    "singapore": "SIN", "sin": "SIN",
    "doha": "DOH", "doh": "DOH",
    "bangkok": "BKK", "bkk": "BKK",
    "frankfurt": "FRA", "fra": "FRA",
    "istanbul": "IST", "ist": "IST",
    "kuala lumpur": "KUL", "kul": "KUL",
    "jeddah": "JED", "jed": "JED",
    "abu dhabi": "AUH", "auh": "AUH",
    "tokyo": "NRT", "narita": "NRT", "nrt": "NRT",
}

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|merge|create|grant|revoke|exec|execute|into|"
    r"openrowset|opendatasource|xp_\w+|sp_\w+)\b",
    re.IGNORECASE,
)

_schema = {"text": None, "at": 0.0}

def _sql_lit(value: str) -> str:
    return (value or "").replace("'", "''")


def resolve_iata(value: str) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip()
    if re.match(r"^[A-Za-z]{3}$", raw):
        return raw.upper()
    return AIRPORT_ALIASES.get(raw.lower())


def build_fast_search_sql(
    origin: str,
    destination: str,
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Optional[str]:
    """Deterministic BLR→DEL-style lookup without an LLM round-trip."""
    o, d = resolve_iata(origin), resolve_iata(destination)
    if not o or not d:
        return None
    clauses = [
        f"origin = '{_sql_lit(o)}'",
        f"destination = '{_sql_lit(d)}'",
        "flight_status != 'Cancelled'",
        f"flight_date >= {_IST_TODAY}",
    ]
    if date:
        clauses.append(f"flight_date = '{_sql_lit(str(date))}'")
    elif date_from and date_to:
        clauses.append(f"flight_date >= '{_sql_lit(str(date_from))}'")
        clauses.append(f"flight_date <= '{_sql_lit(str(date_to))}'")
    where = " AND ".join(clauses)
    return (
        f"SELECT TOP {MAX_ROWS} {_FLIGHT_COLS} FROM {TABLE} WHERE {where} "
        "ORDER BY flight_date ASC, departure_time ASC"
    )


def build_fast_status_sql(flight_no: str, date: Optional[str] = None) -> Optional[str]:
    if not flight_no:
        return None
    fn = _sql_lit(str(flight_no).strip().upper())
    clauses = [f"UPPER(flight_number) LIKE '%{fn}%'", "flight_status != 'Cancelled'"]
    if date and str(date).strip().lower() not in ("", "today"):
        clauses.append(f"flight_date = '{_sql_lit(str(date))}'")
    else:
        clauses.append(f"flight_date >= {_IST_TODAY}")
    where = " AND ".join(clauses)
    return (
        f"SELECT TOP {MAX_ROWS} {_FLIGHT_COLS} FROM {TABLE} WHERE {where} "
        "ORDER BY flight_date ASC, departure_time ASC"
    )


def flight_search_cache_key(args: dict) -> str:
    parts = (
        "search",
        (args.get("origin") or "").strip().lower(),
        (args.get("destination") or "").strip().lower(),
        (args.get("date") or "").strip(),
        (args.get("date_from") or "").strip(),
        (args.get("date_to") or "").strip(),
    )
    return "|".join(parts)


def flight_status_cache_key(args: dict) -> str:
    return "|".join(
        ("status", (args.get("flight_no") or "").strip().upper(), (args.get("date") or "").strip())
    )


def _flight_cache_get(key: str) -> Optional[tuple[list, str]]:
    if not key:
        return None
    hit = _FLIGHT_CACHE.get(key)
    if not hit:
        return None
    ts, rows, sql = hit
    if time.time() - ts > FLIGHT_CACHE_TTL:
        _FLIGHT_CACHE.pop(key, None)
        return None
    return rows, sql


def _flight_cache_set(key: str, rows: list, sql: str) -> None:
    if key and rows is not None:
        _FLIGHT_CACHE[key] = (time.time(), rows, sql)


def get_schema_context() -> str:
    """Columns + real distinct values, read from the DB (cached)."""
    if _schema["text"] and time.time() - _schema["at"] < SCHEMA_TTL:
        return _schema["text"]
    try:
        cols = pd.read_sql(text(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='voice_agent_data' ORDER BY ORDINAL_POSITION"), engine)
        col_txt = ", ".join(f"{r.COLUMN_NAME} ({r.DATA_TYPE})" for r in cols.itertuples())

        grouped = {}
        for alias, code in AIRPORT_ALIASES.items():
            if alias.lower() != code.lower():
                grouped.setdefault(code, []).append(alias.title())
        alias_txt = "\n".join(f"- {c}: {', '.join(n)}" for c, n in sorted(grouped.items()))

        if LIGHT_SCHEMA:
            ctx = (
                f"Database: Azure SQL (T-SQL). Single table: {TABLE}\n"
                f"Columns: {col_txt}\n"
                f"City aliases (user may say these; DB holds IATA codes):\n{alias_txt}"
            )
        else:
            def distinct(col):
                df = pd.read_sql(text(f"SELECT DISTINCT {col} AS v FROM {TABLE} WHERE {col} IS NOT NULL"), engine)
                return sorted(str(v) for v in df["v"].tolist())[:20]

            rng = pd.read_sql(text(f"SELECT MIN(flight_date) AS lo, MAX(flight_date) AS hi FROM {TABLE}"), engine)
            lo, hi = rng["lo"][0], rng["hi"][0]
            ctx = (
                f"Database: Azure SQL (T-SQL). Single table: {TABLE}\n"
                f"Columns: {col_txt}\n"
                f"Data date range: {lo if not pd.isna(lo) else 'N/A'} to {hi if not pd.isna(hi) else 'N/A'}\n"
                f"origin values in DB: {', '.join(distinct('origin'))}\n"
                f"destination values in DB: {', '.join(distinct('destination'))}\n"
                f"flight_status values: {', '.join(distinct('flight_status'))}\n"
                f"City aliases (user may say these; DB holds the codes):\n{alias_txt}"
            )
        _schema.update(text=ctx, at=time.time())
        return ctx
    except Exception as e:
        logger.error(f"Failed to get schema context: {e}")
        return "Schema fetch failed."

def _llm(system: str, user: str) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = _client.chat.completions.create(model=MODEL, messages=msgs, reasoning_effort=EFFORT)
    except BadRequestError: 
        r = _client.chat.completions.create(model=MODEL, messages=msgs)
    return (r.choices[0].message.content or "").strip()

def route_question(question: str) -> dict:
    """
    LLM Intent Classifier (Used by API Gateway).
    """
    system = """Classify the airline customer's question. Reply with ONLY a JSON object, no markdown:
{"route": "sql" | "policy" | "mixed", "sql_question": "...", "policy_question": "..."}

sql    = structured data: flight status, schedules, search, fares, seats, stops, gates, terminals, refundable/changeable flags of a flight
policy = unstructured rules: baggage rules, cancellation/refund/change policy, check-in rules, special items
mixed  = needs BOTH (e.g. "cheapest BLR to DEL tomorrow and what is the cancellation policy?")

For sql: sql_question = the question, policy_question = "".
For policy: policy_question = the question, sql_question = "".
For mixed: split into two self-contained questions. Keep the user's wording, cities, flight numbers and dates."""
    fallback = {"route": "sql", "sql_question": question, "policy_question": ""}
    try:
        out = _llm(system, question)
        out = re.sub(r"^```(?:json)?|```$", "", out, flags=re.I | re.M).strip()
        data = json.loads(out)
        route = str(data.get("route", "")).lower()
        if route not in ("sql", "policy", "mixed"): return fallback
        
        sql_q = (data.get("sql_question") or "").strip() or (question if route == "sql" else "")
        pol_q = (data.get("policy_question") or "").strip() or (question if route == "policy" else "")
        
        if route == "mixed" and not (sql_q and pol_q): return fallback
        return {"route": route, "sql_question": sql_q, "policy_question": pol_q}
    except Exception as e:
        logger.warning(f"Router failed, defaulting to sql: {e}")
        return fallback

def generate_sql(question: str, feedback: str = "") -> str:
    system = f"""You write ONE T-SQL SELECT for Azure SQL.
{get_schema_context()}

Rules:
- Query only {TABLE}. SELECT only. One statement. Use TOP {MAX_ROWS}.
- Airports: map city names to 3-letter IATA codes using the aliases provided.
- Status: For availability searches, always add: flight_status != 'Cancelled'.
- Today's date reference: CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE).
- DATE RULES:
  * Reference Date: Today is October 5, 2026.
  * Dynamic Expression: CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE).
  * ALWAYS filter out past dates: `flight_date >= CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE)`.
  * When the user asks for "this month" or upcoming flights:
    Apply:
    WHERE flight_date >= CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE)
      AND flight_date <= EOMONTH(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'India Standard Time' AS DATE))
      AND flight_status != 'Cancelled'
  * NEVER return any flight dated before today (before 2026-10-05).
  * Always ORDER BY flight_date ASC, departure_time ASC so the earliest upcoming flights appear first.
- If the user asks for "fastest", "shortest duration", or "sabse jaldi":
  Order by DATEDIFF(minute, departure_time, arrival_time) ASC, flight_date ASC.
  Calculate and select the duration in minutes as [duration_minutes].
- If user asks for day-wise schedules (e.g. Tuesday, this month):
  Include flight_date, DATENAME(weekday, flight_date) as [day_name], departure_time, flight_no, airline, fare.
  Order by flight_date ASC, departure_time ASC.
Return ONLY the SQL. No markdown, no explanation."""
    user = question + (f"\n\nPrevious attempt problem: {feedback}" if feedback else "")
    sql = _llm(system, user)
    return re.sub(r"^```(?:sql)?|```$", "", sql, flags=re.I | re.M).strip().rstrip(";").strip()


import asyncio

import concurrent.futures

def execute_query(sql: str):
    if not re.match(r"^\s*(select|with)\b", sql, re.I): return [], "Only SELECT queries allowed."
    if ";" in sql or _FORBIDDEN.search(sql): return [], "Forbidden keyword detected."
    if TABLE.lower() not in sql.lower(): return [], f"Query must read from {TABLE}."
    
    logger.info(f"Generated SQL: {sql}")

    def _run():
        with engine.connect().execution_options(timeout=7) as conn:
            df = pd.read_sql(text(sql), conn)
            return json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))

    # To fully avoid loop.run_until_complete() collision inside FastAPI's running event loop,
    # we use a clean ThreadPoolExecutor to run the database fetch task synchronously with a strict 7-second cutoff.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            res = future.result(timeout=7.0)
            logger.info(f"Query returned {len(res)} rows.")
            return res, None
        except concurrent.futures.TimeoutError:
            logger.error("❌ SQL Query execution timed out after 7 seconds.")
            return [], "Database query timed out."
        except Exception as e:
            logger.error(f"❌ SQL Execution failed: {e}")
            return [], f"Database query failed: {e}"


def generate_answer(question: str, rows: list) -> str:
    system = """You are the answer generation engine for an airline voice assistant.
Use ONLY the provided SQL rows. Do NOT hallucinate. Fares are in INR.
Keep tone conversational, precise, and voice-ready.

Formatting Rules:
- Only summarize flights scheduled on or after October 5, 2026. Ignore any historical/past dates if present.
1. Shortest/Fastest Flight Intent:
   State the exact flight number, airline, departure time, and total duration (e.g., "Air India flight 102 takes only 1 hour and 45 minutes, departing at 6:00 AM").
2. Schedule / Multi-flight Intent:
   If multiple dates or times exist, group them clearly by date and departure slot instead of saying "there are too many flights". Mention up to 3-4 clear options with flight number and time.
3. Zero Rows:
   If 0 rows are returned, say directly: "Is route ya date par koi direct flight schedule nahi mili." Do NOT claim flights exist before checking.
4. Keep the final response under 4 sentences."""

    # Send up to 25 rows instead of just 10 so LLM has the full schedule context
    return _llm(system, f"Question: {question}\nRows ({len(rows)}): {json.dumps(rows[:25])}")

def run_sql_pipeline(
    question: str,
    *,
    voice_mode: bool = False,
    fast_sql: Optional[str] = None,
    cache_key: Optional[str] = None,
) -> dict:
    """Pure SQL pipeline. Voice mode skips answer LLM and uses fast SQL / cache when possible."""
    t0 = time.perf_counter()
    voice = voice_mode or VOICE_FAST
    skip_answer = voice
    fallback_res = {
        "query": "",
        "rows": [],
        "count": 0,
        "answer": "Could not retrieve flight schedules at this moment due to a database timeout. Please try again.",
        "error": "Database query timed out or failed.",
        "timings": {"sql_pipeline": 0.0},
    }

    cached = _flight_cache_get(cache_key) if cache_key else None
    if cached:
        rows, sql = cached
        timings = {"sql_pipeline": round(time.perf_counter() - t0, 3)}
        logger.info(f"⏱️ SQL cache hit ({len(rows)} rows) in {timings['sql_pipeline']}s")
        return {
            "query": sql,
            "rows": rows[:25],
            "count": len(rows),
            "answer": "",
            "error": None,
            "timings": timings,
        }

    try:
        used_fast = False
        if fast_sql:
            sql = fast_sql
            rows, err = execute_query(sql)
            used_fast = True
            if err:
                sql = generate_sql(question)
                rows, err = execute_query(sql)
                used_fast = False
            elif not rows and voice and not ZERO_ROW_RETRY:
                pass
            elif not rows and (not voice or ZERO_ROW_RETRY):
                sql2 = generate_sql(question, feedback="Returned 0 rows. Rewrite to return nearest available dates.")
                rows2, err2 = execute_query(sql2)
                if rows2 and not err2:
                    sql, rows = sql2, rows2
        else:
            sql = generate_sql(question)
            rows, err = execute_query(sql)

            if err:
                sql = generate_sql(question, feedback=f"{err}\nSQL was: {sql}")
                rows, err = execute_query(sql)
            elif not rows and ZERO_ROW_RETRY:
                sql2 = generate_sql(question, feedback="Returned 0 rows. Rewrite to return nearest available dates.")
                rows2, err2 = execute_query(sql2)
                if rows2 and not err2:
                    sql, rows = sql2, rows2

        if err:
            return {
                "query": sql,
                "rows": [],
                "count": 0,
                "answer": fallback_res["answer"] if not skip_answer else "",
                "error": err,
                "timings": {"sql_pipeline": round(time.perf_counter() - t0, 2)},
            }

        answer = "" if skip_answer else generate_answer(question, rows)
        timings = {"sql_pipeline": round(time.perf_counter() - t0, 2)}
        path = "fast_sql" if used_fast else "llm_sql"
        logger.info(f"⏱️ SQL pipeline ({path}) finished in {timings['sql_pipeline']}s")

        if cache_key and rows:
            _flight_cache_set(cache_key, rows, sql)

        return {
            "query": sql,
            "rows": rows[:25],
            "count": len(rows),
            "answer": answer,
            "error": None,
            "timings": timings,
        }
    except Exception as e:
        logger.error(f"❌ Exception in SQL pipeline execution: {e}")
        return fallback_res

def db_healthy() -> bool:
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        return True
    except Exception: return False

def warm_up():
    get_schema_context()