"""
Airline Middleware (Unstructured RAG Microservice)
Handles connections to Azure OpenAI (embeddings), AI Search (policy documents),
and Azure Redis (semantic cache).
"""
import os
import json
import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List

import numpy as np
import redis.asyncio as redis
from redis.exceptions import ResponseError
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
POLICY_CACHE_MAX_DISTANCE = float(os.getenv("POLICY_CACHE_MAX_DISTANCE", "0.15"))
POLICY_LOW_CONFIDENCE_SCORE = float(os.getenv("POLICY_LOW_CONFIDENCE_SCORE", "0.015"))

class AirlineMiddleware:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_disabled: bool = False  # Persistent flag to permanently skip retry overhead
        self.search_client: Optional[SearchClient] = None
        self.openai_client: Optional[AsyncAzureOpenAI] = None
        self.embedding_deployment: str = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        self.openai_healthy: bool = False
        self._last_redis_ping = 0.0
        self._last_redis_status = False
        self._redis_reconnect_task: Optional[asyncio.Task] = None
        max_concurrent = int(os.getenv("MAX_CONCURRENT_VOICE_SESSIONS", "200"))
        self.voice_session_semaphore = asyncio.Semaphore(max_concurrent)

    async def initialize(self):
        await self._init_azure_openai()
        self._init_azure_search()
        await self._connect_redis()
        if not self.redis_disabled:
            self._redis_reconnect_task = asyncio.create_task(self._redis_reconnect_loop())

    async def _init_azure_openai(self):
        try:
            self.openai_client = AsyncAzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                api_version=os.getenv("EMBEDDING_API_VERSION", "2024-02-01"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            )
            await self.openai_client.embeddings.create(input="startup", model=self.embedding_deployment)
            self.openai_healthy = True
            logger.info("✅ Azure OpenAI Embeddings verified working")
        except Exception as e:
            logger.error(f"❌ Azure OpenAI connection failed: {e}")
            self.openai_client = None
            self.openai_healthy = False

    async def get_embedding(self, text: str) -> List[float]:
        response = await self.openai_client.embeddings.create(input=text, model=self.embedding_deployment)
        return response.data[0].embedding

    def _init_azure_search(self):
        try:
            endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
            key = os.getenv("AZURE_SEARCH_KEY")
            index_name = os.getenv("SEARCH_INDEX_NAME", "voice-agent-docs")
            if endpoint and key:
                self.search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(key))
                logger.info("✅ Azure AI Search connected")
        except Exception as e:
            logger.error(f"❌ Azure AI Search connection failed: {e}")

    async def _connect_redis(self) -> bool:
        if self.redis_disabled:
            return False
        try:
            client = redis.Redis(
                host=os.getenv("REDIS_HOST"), 
                port=int(os.getenv("REDIS_PORT", 10000)), 
                password=os.getenv("REDIS_PASSWORD"), 
                ssl=str(os.getenv("REDIS_SSL", "true")).lower() == "true",
                decode_responses=False, socket_connect_timeout=0.5, socket_timeout=0.5,
                retry_on_timeout=False, health_check_interval=30,
            )
            await client.ping()
            self.redis_client = client
            schema = (
                TextField("query_text"), TextField("category"), TextField("response_json"),
                VectorField("query_vector", "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
            )
            await self._setup_redis_index(schema)
            logger.info("✅ Azure Redis Semantic Cache connected")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed (disabling cache retries): {e}")
            self.redis_client = None
            self.redis_disabled = True
            return False

    async def _redis_reconnect_loop(self):
        if self.redis_disabled:
            return
        was_down = self.redis_client is None
        while True:
            await asyncio.sleep(REDIS_RECONNECT_INTERVAL_SECONDS)
            if self.redis_disabled:
                break
            try:
                if self.redis_client is None:
                    success = await self._connect_redis()
                    if success and was_down: logger.info("✅ Redis recovered")
                    was_down = not success
                else:
                    await self.redis_client.ping()
            except Exception:
                self.redis_client = None
                was_down = True

    async def _setup_redis_index(self, schema):
        try:
            await self.redis_client.ft("idx:policy_cache_v2").info()
        except ResponseError:
            try:
                await self.redis_client.ft("idx:policy_cache_v2").create_index(
                    fields=schema, definition=IndexDefinition(prefix=["cache:policy:"], index_type=IndexType.HASH))
            except Exception: pass

    async def is_redis_healthy(self) -> bool:
        if self.redis_disabled or not self.redis_client: return False
        now = asyncio.get_event_loop().time()
        if now - self._last_redis_ping < 5.0: return self._last_redis_status
        try:
            await self.redis_client.ping()
            self._last_redis_status = True
        except Exception:
            self._last_redis_status = False
        finally:
            self._last_redis_ping = now
        return self._last_redis_status

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> bool:
        if self.redis_disabled or not self.redis_client: return True
        try:
            pipe = self.redis_client.pipeline()
            pipe.incr(f"ratelimit:{key}")
            pipe.expire(f"ratelimit:{key}", window_seconds, nx=True)
            count, _ = await pipe.execute()
            return int(count) <= limit
        except Exception: return True

    async def search_policy(self, query: str, category: Optional[str] = None, limit: int = 3) -> Dict[str, Any]:
        fallback = {"results": [], "query": query, "total": 0, "low_confidence": True, "error": "Unavailable."}
        if not self.openai_client or not self.search_client: return fallback
        limit = max(1, min(int(limit or 3), 10))
        cache_cat = category or "none"

        try:
            vec = await self.get_embedding(query)
            vec_bytes = np.array(vec, dtype=np.float32).tobytes()
        except Exception: return fallback

        if not self.redis_disabled and self.redis_client:
            try:
                q = Query("(*)=>[KNN 1 @query_vector $vec AS score]").sort_by("score").return_fields("response_json", "category", "score").dialect(2)
                res = await self.redis_client.ft("idx:policy_cache_v2").search(q, query_params={"vec": vec_bytes})
                if res.docs and float(res.docs[0].score) <= POLICY_CACHE_MAX_DISTANCE:
                    cat = getattr(res.docs[0], "category", b"none")
                    if (cat.decode("utf-8") if isinstance(cat, bytes) else str(cat)) == cache_cat:
                        return json.loads(res.docs[0].response_json)
            except Exception as e:
                logger.warning(f"⚠️ Redis cache miss: {e}")

        try:
            v_q = VectorizedQuery(vector=vec, k_nearest_neighbors=limit, fields="embedding")
            raw_res = await self.search_client.search(search_text=query, vector_queries=[v_q], select=["id", "source", "content"], top=limit)
            fmt_res = [{"id": d.get("id"), "source": d.get("source"), "content": d.get("content"), "score": d.get("@search.score", 0.0)} async for d in raw_res]
            low_conf = not fmt_res or fmt_res[0]["score"] < POLICY_LOW_CONFIDENCE_SCORE
            out = {"results": fmt_res, "query": query, "total": len(fmt_res), "low_confidence": low_conf}
            
            if not self.redis_disabled and self.redis_client and not low_conf:
                try:
                    cid = f"cache:policy:{uuid.uuid4().hex}"
                    await self.redis_client.hset(cid, mapping={"query_text": query, "category": cache_cat, "response_json": json.dumps(out, default=str), "query_vector": vec_bytes})
                    await self.redis_client.expire(cid, POLICY_CACHE_TTL_SECONDS)
                except Exception: pass
            return out
        except Exception as e:
            logger.error(f"❌ AI Search failed: {e}")
            return fallback

    async def close(self):
        if self._redis_reconnect_task: self._redis_reconnect_task.cancel()
        if self.redis_client:
            closer = getattr(self.redis_client, "aclose", None) or self.redis_client.close
            await closer()
        if self.search_client: await self.search_client.close()
        if self.openai_client: await self.openai_client.close()