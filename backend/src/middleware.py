
"""
Airline Middleware
Handles connections to Azure services (SQL, AI Search, Redis, OpenAI)
"""
import os
import logging
import asyncio
import uuid
from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

import numpy as np
import aioodbc
import redis.asyncio as redis
from redis.exceptions import ResponseError
import json
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from openai import AsyncAzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)

POLICY_CACHE_TTL_SECONDS = int(os.getenv("POLICY_CACHE_TTL_SECONDS", "600"))
REDIS_RECONNECT_INTERVAL_SECONDS = int(os.getenv("REDIS_RECONNECT_INTERVAL_SECONDS", "30"))

def sanitize_sql_record(record: dict) -> dict:
    return {
        key: (
            value.isoformat() if isinstance(value, (date, time))
            else float(value) if isinstance(value, Decimal)
            else value
        )
        for key, value in record.items()
    }

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

def resolve_airport_terms(name: str) -> list:
    if not name: return []
    key = name.strip().lower()
    terms = {name.strip()}
    if key in AIRPORT_ALIASES: terms.add(AIRPORT_ALIASES[key])
    for city, code in AIRPORT_ALIASES.items():
        if code.lower() == key:
            terms.add(city)
            terms.add(code)
    return list(terms)

class AirlineMiddleware:
    def __init__(self):
        self.sql_pool: Optional[aioodbc.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.search_client: Optional[SearchClient] = None
        self.openai_client: Optional[AsyncAzureOpenAI] = None
        self.embedding_deployment: str = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        self.openai_healthy: bool = False

        self._last_redis_ping = 0.0
        self._last_redis_status = False
        self._redis_reconnect_task: Optional[asyncio.Task] = None
        self._redis_index_task: Optional[asyncio.Task] = None

        max_concurrent = int(os.getenv("MAX_CONCURRENT_VOICE_SESSIONS", "200"))
        self.voice_session_semaphore = asyncio.Semaphore(max_concurrent)

    async def initialize(self):
        await self._init_azure_openai()
        await self._init_azure_sql_pool()
        self._init_azure_search()
        await self._connect_redis()
        self._redis_reconnect_task = asyncio.create_task(self._redis_reconnect_loop())

    async def _init_azure_openai(self):
        try:
            self.openai_client = AsyncAzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                api_version=os.getenv("EMBEDDING_API_VERSION", "2024-02-01"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            await self.openai_client.embeddings.create(
                input="startup health check", model=self.embedding_deployment
            )
            self.openai_healthy = True
            logger.info("✅ Azure OpenAI Embeddings verified working")
        except Exception as e:
            logger.error(f"❌ Azure OpenAI connection/verification failed: {e}")
            self.openai_client = None
            self.openai_healthy = False

    async def get_embedding(self, text: str) -> List[float]:
        response = await self.openai_client.embeddings.create(
            input=text, model=self.embedding_deployment
        )
        return response.data[0].embedding

    async def _init_azure_sql_pool(self):
        try:
            server = os.getenv("SQL_SERVER")
            database = os.getenv("SQL_DATABASE")
            username = os.getenv("SQL_USERNAME")
            password = os.getenv("SQL_PASSWORD")
            driver = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")

            if not all([server, database, username, password]):
                logger.warning("⚠️ Azure SQL credentials not complete")
                return

            dsn = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
            )
            min_pool = int(os.getenv("SQL_POOL_MIN", "10"))
            max_pool = int(os.getenv("SQL_POOL_MAX", "100"))

            self.sql_pool = await aioodbc.create_pool(
                dsn=dsn, minsize=min_pool, maxsize=max_pool, autocommit=True
            )
            logger.info(f"✅ Azure SQL connection pool ready (min={min_pool}, max={max_pool})")
        except Exception as e:
            logger.error(f"❌ Azure SQL pool initialization failed: {e}")
            self.sql_pool = None

    def _init_azure_search(self):
        try:
            endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
            key = os.getenv("AZURE_SEARCH_KEY")
            index_name = os.getenv("SEARCH_INDEX_NAME", "voice-agent-docs")
            if endpoint and key:
                self.search_client = SearchClient(
                    endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(key)
                )
                logger.info("✅ Azure AI Search connected")
        except Exception as e:
            logger.error(f"❌ Azure AI Search connection failed: {e}")

    async def _connect_redis(self) -> bool:
        try:
            redis_host = os.getenv("REDIS_HOST")
            redis_port = int(os.getenv("REDIS_PORT", 10000))
            redis_password = os.getenv("REDIS_PASSWORD")
            redis_ssl = str(os.getenv("REDIS_SSL", "true")).lower() == "true"

            client = redis.Redis(
                host=redis_host, port=redis_port, password=redis_password, ssl=redis_ssl,
                decode_responses=False, socket_connect_timeout=5, socket_timeout=5,
                retry_on_timeout=True, health_check_interval=30
            )
            await client.ping()

            schema = (
                TextField("query_text"), TextField("category"), TextField("response_json"),
                VectorField("query_vector", "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"})
            )

            self.redis_client = client
            await self._setup_redis_index(schema)
            logger.info("✅ Azure Redis Semantic Cache connected")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Redis connection attempt failed: {e}")
            self.redis_client = None
            return False

    async def _redis_reconnect_loop(self):
        was_down = self.redis_client is None
        while True:
            await asyncio.sleep(REDIS_RECONNECT_INTERVAL_SECONDS)
            try:
                if self.redis_client is None:
                    success = await self._connect_redis()
                    if success and was_down:
                        logger.info("✅ Redis recovered — cache, rate limiting, and session resumption re-enabled")
                    was_down = not success
                else:
                    await self.redis_client.ping()
            except Exception as e:
                logger.warning(f"⚠️ Redis connection lost, will keep retrying: {e}")
                self.redis_client = None
                was_down = True

    async def _setup_redis_index(self, schema):
        try:
            await self.redis_client.ft("idx:policy_cache_v2").info()
        except ResponseError:
            try:
                definition = IndexDefinition(prefix=["cache:policy:"], index_type=IndexType.HASH)
                await self.redis_client.ft("idx:policy_cache_v2").create_index(fields=schema, definition=definition)
            except Exception as e:
                logger.warning(f"⚠️ Could not create Redis index: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Redis index check failed: {e}")

    async def is_redis_healthy(self) -> bool:
        if not self.redis_client:
            return False

        now = asyncio.get_event_loop().time()
        if now - self._last_redis_ping < 5.0:
            return self._last_redis_status

        try:
            await self.redis_client.ping()
            self._last_redis_status = True
        except Exception:
            self._last_redis_status = False
        finally:
            self._last_redis_ping = now

        return self._last_redis_status

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> bool:
        if not self.redis_client: return True
        try:
            redis_key = f"ratelimit:{key}"
            pipe = self.redis_client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds, nx=True)
            count, _ = await pipe.execute()
            return int(count) <= limit
        except Exception as e:
            logger.warning(f"⚠️ Rate limit check failed, allowing request: {e}")
            return True

    async def get_flight_status(self, flight_no: str, date: Optional[str] = None) -> Dict[str, Any]:
        if not self.sql_pool: return {"error": "SQL Database connection not available"}
        query = """
            SELECT flight_number, airline, origin, destination, flight_date, departure_time, arrival_time, flight_status, booking_status,
            available_seats, stops, aircraft_type, cabin_class, total_journey_duration_minutes, distance_km, base_fare_inr, taxes_fees_inr, total_fare_inr, currency,
            refundable, changeable, baggage_allowance_kg, cabin_baggage_kg, departure_terminal, departure_gate, check_in_opens_hours_before, check_in_closes_minutes_before
            FROM dbo.voice_agent_data WHERE flight_number = ? AND (? IS NULL OR flight_date = ?)
        """
        try:
            async with self.sql_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (flight_no, date, date))
                    row = await cursor.fetchone()
                    if not row:
                        return {"error": "Flight not found", "flight_no": flight_no}
                    columns = [col[0] for col in cursor.description]
                    return sanitize_sql_record(dict(zip(columns, row)))
        except Exception as e:
            logger.error(f"❌ Database query failed: {e}")
            return {"error": "Database error while fetching flight status."}

    async def search_flights(
        self,
        origin: str,
        destination: str,
        date: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.sql_pool: return {"error": "SQL Database connection not available"}

        origin_terms = resolve_airport_terms(origin)
        dest_terms = resolve_airport_terms(destination)
        if not origin_terms or not dest_terms: return {"error": "origin and destination are required"}

        origin_clause = f"origin IN ({','.join(['?'] * len(origin_terms))})"
        dest_clause = f"destination IN ({','.join(['?'] * len(dest_terms))})"
        params = list(origin_terms) + list(dest_terms)

        select_cols = """
            flight_number, airline, origin, destination, flight_date, departure_time, arrival_time, flight_status, booking_status,
            available_seats, stops, aircraft_type, cabin_class, layover_1_airport, layover_1_city, layover_1_arrival_time,
            layover_1_departure_time, layover_1_duration_minutes, layover_2_airport, layover_2_city, layover_2_arrival_time,
            layover_2_departure_time, layover_2_duration_minutes, total_journey_duration_minutes, base_fare_inr, taxes_fees_inr, total_fare_inr, currency,
            refundable, changeable, baggage_allowance_kg
        """

        try:
            async with self.sql_pool.acquire() as conn:
                async with conn.cursor() as cursor:

                    async def run_flight_query(extra_clause: str, extra_params: list, top: int = 20):
                        # top is a parameter so the range search can ask for more rows
                        q = f"""
                            SELECT TOP {top} {select_cols} FROM dbo.voice_agent_data
                            WHERE ({origin_clause}) AND ({dest_clause}) {extra_clause}
                            AND flight_status != 'Cancelled' ORDER BY flight_date, departure_time
                        """
                        await cursor.execute(q, params + extra_params)
                        rows = await cursor.fetchall()
                        cols = [c[0] for c in cursor.description]
                        return [sanitize_sql_record(dict(zip(cols, row))) for row in rows]

                    # Date-range search: returns EVERY matching flight across
                    # the whole window (capped at 50 rows) instead of collapsing
                    # to a single "nearest date" like the single-date path does.
                    if date_from and date_to:
                        flights = await run_flight_query(
                            "AND flight_date BETWEEN ? AND ?", [date_from, date_to], top=50
                        )
                        if flights:
                            return {"flights": flights, "count": len(flights)}

                        # No flights anywhere in the range — check the
                        # reverse direction, same as the single-date path.
                        note = f"No {origin} to {destination} flights found between {date_from} and {date_to}."

                        reverse_clause_o = f"origin IN ({','.join(['?'] * len(dest_terms))})"
                        reverse_clause_d = f"destination IN ({','.join(['?'] * len(origin_terms))})"
                        reverse_query = f"SELECT TOP 1 origin, destination FROM dbo.voice_agent_data WHERE ({reverse_clause_o}) AND ({reverse_clause_d})"
                        await cursor.execute(reverse_query, list(dest_terms) + list(origin_terms))
                        reverse_row = await cursor.fetchone()
                        if reverse_row:
                            note += f" However, {destination} to {origin} is available."
                        return {"flights": [], "count": 0, "note": note}

                    elif date:
                        flights = await run_flight_query("AND flight_date = ?", [date])
                        if flights: return {"flights": flights, "count": len(flights)}

                        nearest_query = f"""
                            SELECT DISTINCT flight_date FROM dbo.voice_agent_data
                            WHERE ({origin_clause}) AND ({dest_clause}) AND flight_status != 'Cancelled'
                        """
                        await cursor.execute(nearest_query, params)
                        all_dates_rows = await cursor.fetchall()
                        target_date = datetime.strptime(date, "%Y-%m-%d").date()

                        def _as_date(value):
                            if hasattr(value, "isoformat"):
                                return value if not hasattr(value, "date") else value.date()
                            return datetime.strptime(str(value), "%Y-%m-%d").date()

                        all_dates = sorted((_as_date(r[0]) for r in all_dates_rows), key=lambda d: abs((d - target_date).days))
                        nearest_dates = [d.isoformat() for d in all_dates[:5]]

                        if nearest_dates:
                            closest_date = nearest_dates[0]
                            flights = await run_flight_query("AND flight_date = ?", [closest_date])
                            other_dates = [d for d in nearest_dates[1:] if d != closest_date]

                            if flights:
                                first = flights[0]
                                connection_hint = ""
                                if first.get("stops") not in (None, 0):
                                    via_city = first.get("layover_1_city") or first.get("layover_1_airport")
                                    if via_city:
                                        lm = first.get("layover_1_duration_minutes")
                                        connection_hint = f", connecting via {via_city}{f', about {int(lm)} minutes layover' if lm else ''}"
                                note = f"No {origin} to {destination} flights on {date}, but flight {first.get('flight_number')} ({first.get('airline')}) departs at {first.get('departure_time')} on {closest_date}{connection_hint}."
                                if other_dates: note += f" Also available on {', '.join(other_dates)}."
                            else:
                                note = f"No {origin} to {destination} flights on {date}, but the route is available on {closest_date}."
                            return {"flights": flights, "count": len(flights), "note": note}
                    else:
                        flights = await run_flight_query("AND flight_date >= CAST(GETDATE() AS DATE)", [])
                        if flights: return {"flights": flights, "count": len(flights)}

                    reverse_clause_o = f"origin IN ({','.join(['?'] * len(dest_terms))})"
                    reverse_clause_d = f"destination IN ({','.join(['?'] * len(origin_terms))})"
                    reverse_query = f"SELECT TOP 1 origin, destination FROM dbo.voice_agent_data WHERE ({reverse_clause_o}) AND ({reverse_clause_d})"
                    await cursor.execute(reverse_query, list(dest_terms) + list(origin_terms))
                    reverse_row = await cursor.fetchone()
                    note = f"No {origin} to {destination} flights are scheduled in our system" + (f", though {destination} to {origin} is available." if reverse_row else ".")
                    return {"flights": [], "count": 0, "note": note}
        except Exception as e:
            logger.error(f"❌ Flight search query failed: {e}")
            return {"error": "Database error while searching for flights."}

    async def search_policy(self, query: str, category: Optional[str] = None, limit: int = 3) -> Dict[str, Any]:
        fallback = {"results": [], "query": query, "category": category, "total": 0, "low_confidence": True, "error": "Policy services unavailable."}
        if not self.openai_client or not self.search_client: return fallback

        try:
            query_vector = await self.get_embedding(query)
            query_vector_bytes = np.array(query_vector, dtype=np.float32).tobytes()
        except Exception as e:
            logger.error(f"❌ Embeddings generation failed: {e}")
            return fallback

        if self.redis_client:
            try:
                redis_query = Query("(*)=>[KNN 1 @query_vector $vec AS score]").sort_by("score").return_fields("response_json", "score").dialect(2)
                cache_results = await self.redis_client.ft("idx:policy_cache_v2").search(redis_query, query_params={"vec": query_vector_bytes})
                if cache_results.docs and float(cache_results.docs[0].score) <= 0.15:
                    return json.loads(cache_results.docs[0].response_json)
            except Exception as e:
                logger.warning(f"⚠️ Redis cache read failed: {e}")

        try:
            vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=limit, fields="embedding")
            results = await self.search_client.search(search_text=query, vector_queries=[vector_query], select=["id", "source", "content"], top=limit)
            formatted_results = [{"id": doc.get("id", str(uuid.uuid4())), "source": doc.get("source", "Policy Document"), "content": doc.get("content", ""), "score": doc.get("@search.score", 0.0)} async for doc in results]
            is_low_conf = not formatted_results or formatted_results[0]["score"] < 0.015
            response = {"results": formatted_results, "query": query, "category": category, "total": len(formatted_results), "low_confidence": is_low_conf}

            if self.redis_client and not is_low_conf:
                try:
                    cache_id = f"cache:policy:{uuid.uuid4().hex}"
                    await self.redis_client.hset(cache_id, mapping={"query_text": query, "category": category or "none", "response_json": json.dumps(response, default=str), "query_vector": query_vector_bytes})
                    await self.redis_client.expire(cache_id, POLICY_CACHE_TTL_SECONDS)
                except Exception as e:
                    logger.warning(f"⚠️ Redis cache write failed: {e}")
            return response
        except Exception as e:
            logger.error(f"❌ Azure AI Search query failed: {e}")
            return fallback

    async def invalidate_policy_cache(self) -> int:
        if not self.redis_client: return 0
        deleted = 0
        try:
            async for key in self.redis_client.scan_iter(match="cache:policy:*"):
                await self.redis_client.delete(key)
                deleted += 1
        except Exception as e:
            logger.warning(f"⚠️ Cache invalidation failed: {e}")
        return deleted

    async def close(self):
        if self._redis_reconnect_task:
            self._redis_reconnect_task.cancel()
            try:
                await self._redis_reconnect_task
            except asyncio.CancelledError:
                pass
        if self.sql_pool:
            self.sql_pool.close()
            await self.sql_pool.wait_closed()
        if self.redis_client: await self.redis_client.close()
        if self.search_client: await self.search_client.close()