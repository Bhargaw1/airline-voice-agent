"""
Airline Voice Agent Backend
FastAPI server for real-time voice assistant
"""
import os
import json
import asyncio
import logging
import re
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import websockets
from datetime import datetime, timedelta
import pytz

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_file_handler = logging.FileHandler(os.getenv("LOG_FILE", "backend.log"), encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(_file_handler)

logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-live-preview")
GEMINI_VOICE_NAME = os.getenv("GEMINI_VOICE_NAME", "Puck")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")

_base_endpoint = os.getenv("GEMINI_ENDPOINT", "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
GEMINI_WS_URL = f"{_base_endpoint}?key={GEMINI_API_KEY}" if "?" not in _base_endpoint else _base_endpoint
GEMINI_WS_MAX_SIZE = int(os.getenv("GEMINI_WS_MAX_SIZE_BYTES", str(2 * 1024 * 1024)))

REST_RATE_LIMIT = int(os.getenv("REST_RATE_LIMIT_PER_MINUTE", "60"))
WS_RATE_LIMIT = int(os.getenv("WS_CONNECT_RATE_LIMIT_PER_MINUTE", "10"))

GEMINI_CONNECT_TIMEOUT_SECONDS = int(os.getenv("GEMINI_CONNECT_TIMEOUT_SECONDS", "8"))

def build_setup_message(resume_handle: Optional[str] = None) -> dict:
    ist_time = datetime.now(pytz.timezone('Asia/Kolkata'))
    time_context = ist_time.strftime("%I:%M %p")
    hour = ist_time.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    return {
        "setup": {
            "model": f"models/{GEMINI_MODEL_NAME}",
            "systemInstruction": {
                "parts": [{
                    "text": (
                        f"You are Sky, a premium, human airline concierge. Current local time is {time_context}.\n\n"
                        "CORE BEHAVIOR:\n"
                        f"1. First Turn: When the conversation starts, you MUST greet the user exactly with: "
                        f"'{greeting}! How may I help you today?' Do not say anything else on the first turn.\n"
                        "2. Language Mirroring: You must strictly match the user's language, dialect, and script "
                        "dynamically. If the user speaks Hindi, reply in Hindi. If the user speaks Hinglish "
                        "(e.g., 'mujhe Delhi ka ticket chahiye'), reply in warm, natural Hinglish. Never force "
                        "English if the user switches languages.\n"
                        "3. Spoken Tone: Sound like a real human agent. Be warm, direct, and conversational.\n"
                        "4. Formatting: NEVER use markdown, asterisks, or bullet points. Spell out flight numbers "
                        "naturally (e.g., 'A I two zero four' instead of 'AI204').\n"
                        "5. Pacing: Answer with only one short idea or question at a time.\n\n"
                        "RULES OF ENGAGEMENT:\n"
                        "- If a query is ambiguous, ask one short clarifying question.\n"
                        "- Rely entirely on your tools for flight statuses, schedules, and policies. "
                        "Do not invent data.\n"
                        "- Acknowledge Before Searching: Right before you call a tool to look something up, say a "
                        "brief acknowledgment first, in the exact same language and register the user is currently "
                        "speaking in, so the user isn't left in silence while the lookup runs.\n"
                        "- Connections: If a flight result has one or more stops, always mention the connecting "
                        "city and layover duration if given, instead of only saying it has a stop.\n"
                        "- Date Ranges: If the user asks for flights across a range of dates (e.g. 'from 24 "
                        "September to 31 March'), call search_flights with date_from and date_to instead of a "
                        "single date, so every matching flight in that window is returned, not just one day.\n"
                        "- If a tool response includes a 'note' field, treat it as the authoritative explanation "
                        "for why the result looks the way it does. Always relay its meaning in natural spoken "
                        "words, converting any raw date into relative terms (today, tomorrow, or weekday/date).\n"
                    )
                }]
            },
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE_NAME}}},
            },
            "tools": [{
                "functionDeclarations": [
                    {
                        "name": "get_flight_status",
                        "description": "Check real-time status of a specific flight number.",
                        "parameters": {"type": "OBJECT", "properties": {"flight_no": {"type": "STRING"}, "date": {"type": "STRING"}}, "required": ["flight_no"]},
                    },
                    {
                        "name": "search_flights",
                        # CHANGED: description now explains the range option
                        "description": (
                            "Search available flights between origin and destination cities. Use 'date' for a "
                            "single specific day, OR use 'date_from' and 'date_to' together to find every flight "
                            "across a range of dates (e.g. the user asks for flights across several weeks or months)."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "origin": {"type": "STRING", "description": "Departure city or airport code (e.g., Bangalore, BLR)"},
                                "destination": {"type": "STRING", "description": "Arrival city or airport code (e.g., Delhi, DEL)"},
                                # CHANGED: date is now optional, used only for a single-day search
                                "date": {"type": "STRING", "description": "A single specific flight date in YYYY-MM-DD format. Omit this if using date_from/date_to instead."},
                                # NEW: range parameters
                                "date_from": {"type": "STRING", "description": "Start of a date range in YYYY-MM-DD format, for multi-day searches."},
                                "date_to": {"type": "STRING", "description": "End of a date range in YYYY-MM-DD format, for multi-day searches."},
                            },
                            # CHANGED: date removed from required — only origin/destination are mandatory now
                            "required": ["origin", "destination"],
                        },
                    },
                    {
                        "name": "search_policy",
                        "description": "Search airline policies for baggage, cancellation, or special items.",
                        "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}, "category": {"type": "STRING"}}, "required": ["query"]},
                    },
                ]
            }],
            "sessionResumption": {"handle": resume_handle} if resume_handle else {},
            "contextWindowCompression": {"slidingWindow": {}}
        }
    }

try:
    from src.middleware import AirlineMiddleware
    MIDDLWARE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Middleware not available: {e}")
    MIDDLWARE_AVAILABLE = False
    AirlineMiddleware = None

def normalize_date(date_str: Optional[str]) -> str:
    today = datetime.now(pytz.timezone("Asia/Kolkata")).date()
    if not date_str: return today.isoformat()
    val = str(date_str).strip().lower()
    if "tomorrow" in val: return (today + timedelta(days=1)).isoformat()
    if "today" in val: return today.isoformat()
    match = re.search(r'\d{4}-\d{2}-\d{2}', val)
    if match: return match.group(0)
    return today.isoformat()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if MIDDLWARE_AVAILABLE:
        try:
            app.state.middleware = AirlineMiddleware()
            await app.state.middleware.initialize()
            logger.info("✅ Middleware initialized")
        except Exception as e:
            logger.error(f"❌ Middleware initialization failed: {e}")
            app.state.middleware = None
    else:
        app.state.middleware = None
    yield
    if getattr(app.state, "middleware", None):
        await app.state.middleware.close()

app = FastAPI(title="Airline Voice Agent Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if BACKEND_API_KEY and x_api_key != BACKEND_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

async def enforce_rest_rate_limit(request: Request):
    if not getattr(app.state, "middleware", None): return
    client_ip = request.client.host if request.client else "unknown"
    allowed = await app.state.middleware.check_rate_limit(key=f"rest:{client_ip}", limit=REST_RATE_LIMIT, window_seconds=60)
    if not allowed: raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")

class HealthResponse(BaseModel):
    status: str; message: str; version: str = "1.0.0"; services: Dict[str, str] = {}

class ToolRequest(BaseModel):
    tool_name: str; arguments: Dict[str, Any] = Field(default_factory=dict)

class ToolResponse(BaseModel):
    success: bool; data: Optional[Any] = None; error: Optional[str] = None

@app.get("/health", response_model=HealthResponse)
async def health_check():
    services = {}
    mw = getattr(app.state, "middleware", None)
    if mw:
        services["azure_search"] = "connected" if mw.search_client else "disconnected"
        services["azure_sql"] = "connected" if mw.sql_pool else "disconnected"
        services["redis"] = "connected" if await mw.is_redis_healthy() else "disconnected"
        services["azure_openai"] = "connected" if mw.openai_healthy else "disconnected"
    services["gemini_live"] = "configured" if GEMINI_API_KEY else "not_configured"
    return HealthResponse(status="healthy", message="Backend is running and ready", services=services)

@app.post("/execute-tool", response_model=ToolResponse, dependencies=[Depends(verify_api_key), Depends(enforce_rest_rate_limit)])
async def execute_tool(request: ToolRequest):
    try:
        if not getattr(app.state, "middleware", None): raise HTTPException(status_code=503, detail="Backend services not initialized")
        if request.tool_name == "get_flight_status": result = await execute_flight_status(request.arguments)
        elif request.tool_name == "search_policy": result = await execute_policy_search(request.arguments)
        elif request.tool_name == "search_flights": result = await execute_flight_search(request.arguments)
        else: raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}")
        return ToolResponse(success=True, data=result)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {str(e)}", exc_info=True)
        return ToolResponse(success=False, error="The service is temporarily unavailable.")

@app.post("/admin/invalidate-policy-cache", dependencies=[Depends(verify_api_key)])
async def invalidate_policy_cache_endpoint():
    mw = getattr(app.state, "middleware", None)
    if not mw: raise HTTPException(status_code=503, detail="Backend services not initialized")
    deleted = await mw.invalidate_policy_cache()
    return {"invalidated": deleted}

async def execute_flight_status(args: Dict[str, Any]) -> Dict[str, Any]:
    flight_no = args.get("flight_no")
    date = normalize_date(args.get("date")) if args.get("date") else None
    if not flight_no: raise HTTPException(status_code=400, detail="flight_no is required")
    return await app.state.middleware.get_flight_status(flight_no, date)

async def execute_policy_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query")
    category = args.get("category")
    if not query: raise HTTPException(status_code=400, detail="query is required")
    return await app.state.middleware.search_policy(query, category, args.get("limit", 5))

async def execute_flight_search(args: Dict[str, Any]) -> Dict[str, Any]:
    origin = args.get("origin")
    destination = args.get("destination")
    if not all([origin, destination]):
        raise HTTPException(status_code=400, detail="origin and destination are required")

    # NEW: date-range branch. If either date_from or date_to is present,
    # treat this as a range search — normalize both ends and pass them
    # through to the middleware's range query instead of the single-date path.
    date_from_raw = args.get("date_from")
    date_to_raw = args.get("date_to")
    if date_from_raw or date_to_raw:
        date_from = normalize_date(date_from_raw) if date_from_raw else normalize_date(None)
        date_to = normalize_date(date_to_raw) if date_to_raw else date_from
        return await app.state.middleware.search_flights(
            origin, destination, date_from=date_from, date_to=date_to
        )

    date = normalize_date(args.get("date"))
    return await app.state.middleware.search_flights(origin, destination, date=date)

async def execute_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "get_flight_status": return await execute_flight_status(args)
        elif name == "search_policy": return await execute_policy_search(args)
        elif name == "search_flights": return await execute_flight_search(args)
        return {"error": f"Unknown tool: {name}"}
    except HTTPException as e:
        logger.warning(f"⚠️ Tool call validation error for '{name}': {e.detail}")
        return {"error": e.detail}
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}", exc_info=True)
        return {"error": "The service is temporarily unavailable."}

async def relay_client_to_gemini(websocket: WebSocket, gemini_ws):
    try:
        while True:
            msg = await websocket.receive_text()
            await gemini_ws.send(msg)
    except WebSocketDisconnect: pass

_gemini_reject_before_setup_count = 0

async def relay_gemini_to_client(websocket: WebSocket, gemini_ws, session_key: Optional[str], skip_greeting: bool = False) -> Dict[str, Any]:
    global _gemini_reject_before_setup_count
    mw = getattr(app.state, "middleware", None)
    outcome: Dict[str, Any] = {
        "received_any_message": False,
        "received_setup_complete": False,
        "gemini_close_code": None,
        "gemini_close_reason": None,
    }
    greeting_triggered = False
    try:
        async for raw in gemini_ws:
            outcome["received_any_message"] = True
            text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            data = json.loads(text)

            if data.get("setupComplete") is not None:
                outcome["received_setup_complete"] = True
                if not greeting_triggered and not skip_greeting:
                    greeting_triggered = True
                    await gemini_ws.send(json.dumps({
                        "clientContent": {
                            "turns": [{"role": "user", "parts": [{"text": "(call connected)"}]}],
                            "turnComplete": True
                        }
                    }))
                    logger.info("👋 Sent kickoff turn so Gemini greets the customer first")

            function_calls = data.get("toolCall", {}).get("functionCalls")
            if function_calls:
                for fc in function_calls:
                    result = await execute_tool_call(fc.get("name"), fc.get("args") or {})
                    await websocket.send_json({"toolResult": {"name": fc.get("name"), "data": result}})
                    await gemini_ws.send(json.dumps({"toolResponse": {"functionResponses": [{"id": fc.get("id"), "name": fc.get("name"), "response": result}]}}))
                continue

            resumption_update = data.get("sessionResumptionUpdate")
            if resumption_update and resumption_update.get("resumable") and mw and mw.redis_client and session_key:
                new_handle = resumption_update.get("newHandle")
                if new_handle:
                    try: await mw.redis_client.set(f"session:resume:{session_key}", new_handle, ex=3600)
                    except Exception as e: logger.warning(f"⚠️ Could not persist resumption handle: {e}")

            if data.get("goAway"): logger.info(f"⚠️ Gemini sent goAway: {data['goAway']}")
            await websocket.send_text(text)
    except websockets.exceptions.ConnectionClosed as e:
        outcome["gemini_close_code"] = e.code
        outcome["gemini_close_reason"] = e.reason
        if not outcome["received_setup_complete"]:
            _gemini_reject_before_setup_count += 1
            n = _gemini_reject_before_setup_count
            if n <= 5 or n % 200 == 0:
                logger.error(
                    f"❌ [#{n}] Gemini closed the connection before setupComplete "
                    f"(received_any_message={outcome['received_any_message']}, "
                    f"close_code={e.code}, close_reason={e.reason!r}). "
                    f"Check GEMINI_API_KEY validity and GEMINI_MODEL_NAME "
                    f"('{GEMINI_MODEL_NAME}') access for this key."
                )
        else:
            logger.info(f"ℹ️ Gemini session ended normally (close_code={e.code}, close_reason={e.reason!r})")
    except WebSocketDisconnect:
        pass
    return outcome

@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    client_ip = websocket.client.host if websocket.client else "unknown"
    api_key = websocket.query_params.get("api_key")
    if BACKEND_API_KEY and api_key != BACKEND_API_KEY:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    mw = getattr(app.state, "middleware", None)
    if mw:
        allowed = await mw.check_rate_limit(key=f"ws:{client_ip}", limit=WS_RATE_LIMIT, window_seconds=60)
        if not allowed:
            await websocket.close(code=4008, reason="Rate limit exceeded")
            return

    if not GEMINI_API_KEY:
        await websocket.close(code=1011, reason="Voice agent not configured")
        return

    semaphore = mw.voice_session_semaphore if mw else None
    acquired = True
    if semaphore:
        try: await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
        except asyncio.TimeoutError: acquired = False

    if not acquired:
        await websocket.accept()
        await websocket.close(code=1013, reason="Server at capacity, please retry shortly")
        return

    await websocket.accept()
    session_key = websocket.query_params.get("session_id")
    resume_handle = websocket.query_params.get("resume")

    if not resume_handle and session_key and mw and mw.redis_client:
        try:
            stored = await mw.redis_client.get(f"session:resume:{session_key}")
            if stored: resume_handle = stored.decode("utf-8") if isinstance(stored, bytes) else stored
        except Exception as e: logger.warning(f"⚠️ Could not read resumption handle from Redis: {e}")

    try:
        gemini_ws = await asyncio.wait_for(
            websockets.connect(GEMINI_WS_URL, max_size=GEMINI_WS_MAX_SIZE),
            timeout=GEMINI_CONNECT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(f"❌ Upstream Gemini connect timed out after {GEMINI_CONNECT_TIMEOUT_SECONDS}s (client={client_ip})")
        if semaphore: semaphore.release()
        await websocket.close(code=1011, reason="Upstream voice service timed out")
        return
    except Exception as e:
        logger.error(f"❌ Upstream Gemini connect failed (client={client_ip}): {e}")
        if semaphore: semaphore.release()
        await websocket.close(code=1011, reason="Upstream voice service unavailable")
        return

    relay_outcome: Optional[Dict[str, Any]] = None
    try:
        async with gemini_ws:
            await gemini_ws.send(json.dumps(build_setup_message(resume_handle=resume_handle)))
            task_up = asyncio.create_task(relay_client_to_gemini(websocket, gemini_ws))
            task_down = asyncio.create_task(
                relay_gemini_to_client(websocket, gemini_ws, session_key, skip_greeting=bool(resume_handle))
            )
            done, pending = await asyncio.wait({task_up, task_down}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending: task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if task_down in done and not task_down.cancelled():
                try:
                    relay_outcome = task_down.result()
                except Exception:
                    relay_outcome = None
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"❌ Voice relay failed mid-session (client={client_ip}): {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Voice session error")
        except Exception:
            pass
    finally:
        if semaphore: semaphore.release()
        try:
            if relay_outcome and not relay_outcome.get("received_setup_complete") and relay_outcome.get("gemini_close_code") is not None:
                reason = f"Upstream rejected session: {relay_outcome.get('gemini_close_reason') or 'no reason given by Gemini'}"
                await websocket.close(code=1011, reason=reason[:120])
            else:
                await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)