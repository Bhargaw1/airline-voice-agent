# """
# Airline Voice Agent Backend
# FastAPI API Gateway and Real-Time Orchestrator

# Architecture: the LLM router lives HERE, at the gateway. Every tool call Gemini emits
# (get_flight_status, search_flights, search_policy) is classified FIRST as sql / policy / mixed,
# then dispatched: sql -> dynamic SQL pipeline, policy -> RAG pipeline (Redis cache + AI Search),
# mixed -> both in parallel with asyncio.gather. _build_flight_payload merges the results.
# The flow module and the middleware never import main.py, so there are no circular dependencies.
# """
# import os
# import json
# import asyncio
# import logging
# import re
# import secrets
# import time
# import smtplib
# from contextlib import asynccontextmanager
# from dotenv import load_dotenv
# import websockets
# from datetime import datetime
# import pytz
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart

# load_dotenv()
# from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header, Depends
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field
# from typing import Optional, Dict, Any

# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# logger = logging.getLogger(__name__)
# _file_handler = logging.FileHandler(os.getenv("LOG_FILE", "backend.log"), encoding="utf-8")
# _file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
# logging.getLogger().addHandler(_file_handler)
# for _n in ("websockets", "websockets.client", "websockets.server"):
#     logging.getLogger(_n).setLevel(logging.WARNING)

# IST = pytz.timezone("Asia/Kolkata")
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-exp")
# GEMINI_VOICE_NAME = os.getenv("GEMINI_VOICE_NAME", "Puck")
# BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")
# _base_endpoint = os.getenv("GEMINI_ENDPOINT", "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
# GEMINI_WS_URL = f"{_base_endpoint}?key={GEMINI_API_KEY}" if "?" not in _base_endpoint else _base_endpoint
# GEMINI_WS_MAX_SIZE = int(os.getenv("GEMINI_WS_MAX_SIZE_BYTES", str(2 * 1024 * 1024)))
# REST_RATE_LIMIT = int(os.getenv("REST_RATE_LIMIT_PER_MINUTE", "60"))
# WS_RATE_LIMIT = int(os.getenv("WS_CONNECT_RATE_LIMIT_PER_MINUTE", "10"))
# GEMINI_CONNECT_TIMEOUT_SECONDS = int(os.getenv("GEMINI_CONNECT_TIMEOUT_SECONDS", "8"))
# TOOL_TIMEOUT_SECONDS = float(os.getenv("TOOL_TIMEOUT_SECONDS", "20.0"))
# MAX_TOOL_ARG_LENGTH = 300
# GEMINI_INPUT_TRANSCRIPTION = os.getenv("GEMINI_INPUT_TRANSCRIPTION", "true").lower() == "true"
# MAX_UTTERANCE_LENGTH = 500

# _INJECTION_PATTERNS = [
#     re.compile(p, re.IGNORECASE) for p in (
#         r"ignore (all )?(previous|prior|above) instructions",
#         r"disregard (the )?(system|developer) (prompt|message|instructions)",
#         r"you are now (?:in )?(?:dan|developer|admin) mode",
#         r"reveal (the )?(system prompt|hidden instructions|api key|secret)",
#         r"jailbreak",
#     )
# ]


# def tool_args_violation(args: Dict[str, Any]) -> Optional[str]:
#     for key, value in (args or {}).items():
#         if isinstance(value, str):
#             if len(value) > MAX_TOOL_ARG_LENGTH:
#                 return f"Argument '{key}' is too long."
#             if any(p.search(value) for p in _INJECTION_PATTERNS):
#                 return "Request blocked by safety check."
#     return None


# async def send_booking_email_async(booking_data: dict, recent_utterance: str, history: list):
#     """Non-blocking background email dispatch for booking handoffs."""
#     def _send():
#         recipient = "i-shyam.singh@affine.ai"
#         origin = booking_data.get('origin', 'Not specified')
#         destination = booking_data.get('destination', 'Not specified')
#         flight_no = booking_data.get('flight_number', 'Not specified')
        
#         subject = f"✈️ [Booking Referral] {origin} to {destination}"
        
#         body = f"""New Booking Referral:
# --------------------------------------------------
# Customer Request / Utterance: {recent_utterance}
# Route: {origin} to {destination}
# Flight Details: {flight_no}
# Notes: {booking_data.get('customer_note', 'Customer ready for documentation & payment')}

# Recent Conversation History:
# {history[-4:] if history else 'N/A'}
# --------------------------------------------------
# Dispatched automatically by Airline Voice Agent Gateway.
# """
#         logger.info(f"📧 [BOOKING EMAIL LOGGED TO {recipient}]:\n{body}")
        
#         smtp_host = os.getenv("SMTP_HOST")
#         if smtp_host:
#             try:
#                 msg = MIMEMultipart()
#                 msg["From"] = os.getenv("SMTP_FROM", "voice-agent@airline.com")
#                 msg["To"] = recipient
#                 msg["Subject"] = subject
#                 msg.attach(MIMEText(body, "plain"))
#                 with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", 587))) as server:
#                     if os.getenv("SMTP_TLS", "true").lower() == "true":
#                         server.starttls()
#                     if os.getenv("SMTP_USER"):
#                         server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
#                     server.send_message(msg)
#             except Exception as e:
#                 logger.error(f"Failed to dispatch email via SMTP: {e}")

#     await asyncio.to_thread(_send)


# def build_setup_message(resume_handle: Optional[str] = None) -> dict:
#     now_ist = datetime.now(IST)
#     time_context = now_ist.strftime("%I:%M %p")
#     date_context = now_ist.strftime("%A, %d %B %Y")
#     hour = now_ist.hour
#     greeting = "Hi, Good morning! How may I help you today?" if hour < 12 else "Hi, Good afternoon! How may I help you today?" if hour < 17 else "Hi, Good evening! How may I help you today?"

#     return {
#         "setup": {
#             "model": f"models/{GEMINI_MODEL_NAME}",
#             "systemInstruction": {
#                 "parts": [{
#                     "text": (
#                         f"You are Sky, a highly professional airline concierge. Current local time is {time_context} "
#                         f"and today's date is {date_context} (India Standard Time).\n\n"
#                         "CORE SYSTEM BEHAVIOR & PRIORITIES:\n\n"
#                         "1. FLIGHT SEARCH PRIORITY:\n"
#                         "   - When the user asks for flights, schedules, fares, or routes, you MUST ALWAYS call the `search_flights` tool. NEVER answer flight availability or schedules from memory.\n"
#                         "   - For specific flight number inquiry or status, call `get_flight_status`.\n"
#                         "   - For baggage, cancellation, refund, or rules, call `search_policy`.\n\n"
#                         "2. INSTANT BOOKING HANDOFF PROTOCOL:\n"
#                         "   - When the user indicates they want to BOOK or RESERVE a flight (e.g., 'Mujhe flight book karni hai', 'Book this flight', 'Reserve seat'):\n"
#                         "     Do NOT ask multi-step questions for passenger count, meals, or medical conditions.\n"
#                         "     Immediately call the `initiate_booking_handoff` tool.\n"
#                         "     Speak this exact handoff message (mirroring the user's spoken language):\n"
#                         "     - English: 'For further booking process, I am forwarding your request to my team member. They will assist you with documentation and payment shortly.'\n"
#                         "     - Hindi / Hinglish: 'Aage ki booking process ke liye main aapki request hamare team member ko forward kar raha hoon. Wo jald hi documentation aur payment mein aapki madad karenge.'\n\n"
#                         "3. UNIVERSAL LANGUAGE MIRRORING (ZERO DRIFT):\n"
#                         "   - Always respond in the EXACT SAME language that the user is currently speaking.\n"
#                         "   - NEVER switch or drift to an unprompted language.\n"
#                         "   - Keep all voice responses concise, conversational, and direct (2-3 sentences max).\n"
#                     )
#                 }]
#             },
#             "generationConfig": {
#                 "responseModalities": ["AUDIO"],
#                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE_NAME}}},
#             },
#             "tools": [{
#                 "functionDeclarations": [
#                     {
#                         "name": "get_flight_status",
#                         "description": "Check real-time status of a specific flight number. If the user gives no date, omit 'date' and the flight nearest to today is returned.",
#                         "parameters": {
#                             "type": "OBJECT",
#                             "properties": {
#                                 "flight_no": {"type": "STRING", "description": "Flight number, e.g. AI204"},
#                                 "date": {"type": "STRING", "description": "Flight date in YYYY-MM-DD format (optional)."},
#                             },
#                             "required": ["flight_no"],
#                         },
#                     },
#                     {
#                         "name": "search_flights",
#                         "description": "Search available flights between origin and destination cities. Use 'date' for a single day, OR 'date_from' and 'date_to' together for a range of dates.",
#                         "parameters": {
#                             "type": "OBJECT",
#                             "properties": {
#                                 "origin": {"type": "STRING", "description": "Departure city or airport code (e.g., Bangalore, BLR)"},
#                                 "destination": {"type": "STRING", "description": "Arrival city or airport code (e.g., Delhi, DEL)"},
#                                 "date": {"type": "STRING", "description": "A single flight date in YYYY-MM-DD format. Omit if using date_from/date_to."},
#                                 "date_from": {"type": "STRING", "description": "Start of a date range, YYYY-MM-DD."},
#                                 "date_to": {"type": "STRING", "description": "End of a date range, YYYY-MM-DD."},
#                             },
#                             "required": ["origin", "destination"],
#                         },
#                     },
#                     {
#                         "name": "search_policy",
#                         "description": "Search airline policies for baggage, cancellation, refunds, changes, check-in or special items.",
#                         "parameters": {
#                             "type": "OBJECT",
#                             "properties": {
#                                 "query": {"type": "STRING", "description": "The policy question in plain words."},
#                                 "category": {"type": "STRING", "description": "Optional: baggage, cancellation, refund, check-in."},
#                             },
#                             "required": ["query"],
#                         },
#                     },
#                     {
#                         "name": "initiate_booking_handoff",
#                         "description": "Call this tool immediately when the user wants to book or reserve a flight. Do not ask further qualifying questions.",
#                         "parameters": {
#                             "type": "OBJECT",
#                             "properties": {
#                                 "flight_number": {"type": "STRING", "description": "The specific flight number (optional)"},
#                                 "origin": {"type": "STRING", "description": "Departure city if mentioned"},
#                                 "destination": {"type": "STRING", "description": "Arrival city if mentioned"},
#                                 "customer_note": {"type": "STRING", "description": "Any specific notes mentioned by customer"}
#                             },
#                             "required": []
#                         }
#                     },
#                 ]
#             }],
#             "sessionResumption": {"handle": resume_handle} if resume_handle else {},
#             "contextWindowCompression": {"slidingWindow": {}},
#             **({"inputAudioTranscription": {}} if GEMINI_INPUT_TRANSCRIPTION else {}),
#         }
#     }


# try:
#     from src.middleware import AirlineMiddleware
#     MIDDLEWARE_AVAILABLE = True
# except ImportError as e:
#     logger.warning(f"Middleware not available: {e}")
#     MIDDLEWARE_AVAILABLE = False
#     AirlineMiddleware = None

# try:
#     from autogen_flow.airline_autogen_flow import route_question, run_sql_pipeline, warm_up, db_healthy
#     FLOW_AVAILABLE = True
# except Exception as e:
#     logger.error(f"❌ SQL flow import failed (all flight tools will return 503): {e}", exc_info=True)
#     FLOW_AVAILABLE = False
#     route_question = run_sql_pipeline = warm_up = db_healthy = None


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     app.state.middleware = None
#     if MIDDLEWARE_AVAILABLE: # Note: Typo fix from previous MIDDLEWARE_AVAILABLE if any, kept consistent
#         try:
#             app.state.middleware = AirlineMiddleware()
#             await app.state.middleware.initialize()
#             logger.info("✅ Middleware initialized")
#         except Exception as e:
#             logger.error(f"❌ Middleware initialization failed: {e}")
#             app.state.middleware = None
#     if FLOW_AVAILABLE:
#         try:
#             await asyncio.to_thread(warm_up)
#         except Exception as e:
#             logger.warning(f"⚠️ SQL flow warm-up failed: {e}")
#     yield
#     if getattr(app.state, "middleware", None):
#         await app.state.middleware.close()
#         app.state.middleware = None


# app = FastAPI(title="Airline Voice Agent Backend", lifespan=lifespan)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
#     allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
# )


# def _api_key_ok(provided: Optional[str]) -> bool:
#     if not BACKEND_API_KEY:
#         return True
#     return secrets.compare_digest((provided or "").encode(), BACKEND_API_KEY.encode())


# async def verify_api_key(x_api_key: Optional[str] = Header(None)):
#     if not _api_key_ok(x_api_key):
#         raise HTTPException(status_code=401, detail="Invalid API key")


# async def enforce_rest_rate_limit(request: Request):
#     if not getattr(app.state, "middleware", None):
#         return
#     client_ip = request.client.host if request.client else "unknown"
#     allowed = await app.state.middleware.check_rate_limit(key=f"rest:{client_ip}", limit=REST_RATE_LIMIT, window_seconds=60)
#     if not allowed:
#         raise HTTPException(status_code=429, detail="Rate limit exceeded.")


# # ==============================================================================
# # REST API ENDPOINTS (/health, /execute-tool)
# # ==============================================================================
# class HealthResponse(BaseModel):
#     status: str
#     message: str
#     version: str = "1.5.0"
#     services: Dict[str, str] = {}


# class ToolRequest(BaseModel):
#     tool_name: str
#     arguments: Dict[str, Any] = Field(default_factory=dict)
#     utterance: Optional[str] = None


# class ToolResponse(BaseModel):
#     success: bool
#     data: Optional[Any] = None
#     error: Optional[str] = None


# @app.get("/health", response_model=HealthResponse)
# async def health_check():
#     services = {}
#     mw = getattr(app.state, "middleware", None)
#     if mw:
#         services["azure_search"] = "connected" if mw.search_client else "disconnected"
#         services["redis"] = "connected" if await mw.is_redis_healthy() else "disconnected"
#         services["azure_openai"] = "connected" if mw.openai_healthy else "disconnected"
#     if FLOW_AVAILABLE:
#         services["azure_sql"] = "connected" if await asyncio.to_thread(db_healthy) else "disconnected"
#     else:
#         services["azure_sql"] = "disconnected"
#     services["gemini_live"] = "configured" if GEMINI_API_KEY else "not_configured"
#     return HealthResponse(status="healthy", message="Backend is running and ready", services=services)


# @app.post("/execute-tool", response_model=ToolResponse, dependencies=[Depends(verify_api_key), Depends(enforce_rest_rate_limit)])
# async def execute_tool(request: ToolRequest):
#     try:
#         violation = tool_args_violation(request.arguments)
#         if violation:
#             raise HTTPException(status_code=400, detail=violation)
#         utt = _clean_utterance(request.utterance)
#         if request.tool_name == "get_flight_status": result = await execute_flight_status(request.arguments, utt)
#         elif request.tool_name == "search_policy": result = await execute_policy_search(request.arguments, utt)
#         elif request.tool_name == "search_flights": result = await execute_flight_search(request.arguments, utt)
#         else: raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}")
#         return ToolResponse(success=True, data=result)
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"❌ Tool execution failed: {e}", exc_info=True)
#         return ToolResponse(success=False, error="The service is temporarily unavailable.")


# # ==============================================================================
# # ORCHESTRATION LAYER
# # ==============================================================================
# def _clean_utterance(text: Optional[str]) -> str:
#     text = (text or "").strip()[:MAX_UTTERANCE_LENGTH]
#     if text and any(p.search(text) for p in _INJECTION_PATTERNS):
#         return ""
#     return text


# _TOOL_DEFAULT_ROUTE = {"get_flight_status": "sql", "search_flights": "sql", "search_policy": "policy"}


# async def run_policy_pipeline(query: str, category: Optional[str] = None) -> Dict[str, Any]:
#     mw = getattr(app.state, "middleware", None)
#     if not mw or not getattr(mw, "search_client", None):
#         return {"results": [], "total": 0, "low_confidence": True, "error": "Policy services unavailable."}
#     return await mw.search_policy(query=query, category=category)


# def _build_flight_payload(route: str, sql_result: Optional[Dict[str, Any]], policy_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
#     payload = {
#         "route": route,
#         "dynamic_sql_used": sql_result.get("query") if sql_result else None,
#         "flight_results": sql_result.get("rows", []) if sql_result else [],
#         "count": sql_result.get("count", 0) if sql_result else 0,
#         "summary": sql_result.get("answer") if sql_result else "",
#     }
#     if policy_result is not None:
#         payload["policy_information"] = policy_result
#     return payload


# async def _gateway_router_flow(tool: str, args: Dict[str, Any], tool_question: str, utterance: str = "") -> Dict[str, Any]:
#     if not FLOW_AVAILABLE:
#         raise HTTPException(status_code=503, detail="Backend data service unavailable.")

#     # Bypass router LLM for deterministic flight tools to save ~2.5s latency
#     if tool in ("search_flights", "get_flight_status"):
#         logger.info(f"🚦 Direct SQL route for tool={tool} utterance={utterance!r}")
#         sql_result = await asyncio.to_thread(run_sql_pipeline, tool_question)
#         return _build_flight_payload("sql", sql_result, None)

#     category = args.get("category")
#     hint = f"\n(Tool requested: {tool}, args: {json.dumps(args, ensure_ascii=False)[:300]})"
#     try:
#         routing = await asyncio.to_thread(route_question, (utterance or tool_question) + hint)
#     except Exception as e:
#         logger.error(f"❌ Router raised: {e!r}")
#         routing = {"fallback": True}

#     if routing.get("fallback"):
#         route = _TOOL_DEFAULT_ROUTE.get(tool, "sql")
#         sql_q = pol_q = tool_question
#         logger.warning(f"🚦 Router fallback -> default route '{route}' for tool {tool}")
#     else:
#         route = routing["route"]
#         sql_q = routing.get("sql_question") or tool_question
#         pol_q = routing.get("policy_question") or tool_question
#     logger.info(f"🚦 Route={route} tool={tool} utterance={utterance!r}")

#     sql_result = None
#     policy_result = None

#     if route == "sql":
#         sql_result = await asyncio.to_thread(run_sql_pipeline, sql_q)
#     elif route == "policy":
#         policy_result = await run_policy_pipeline(pol_q, category)
#     else:
#         sql_r, pol_r = await asyncio.gather(
#             asyncio.to_thread(run_sql_pipeline, sql_q),
#             run_policy_pipeline(pol_q, category),
#             return_exceptions=True,
#         )
#         if isinstance(sql_r, BaseException):
#             logger.error(f"❌ SQL half of mixed route failed: {sql_r!r}")
#             sql_r = {"query": None, "rows": [], "count": 0, "answer": "I could not fetch the flight data right now."}
#         if isinstance(pol_r, BaseException):
#             logger.error(f"❌ Policy half of mixed route failed: {pol_r!r}")
#             pol_r = {"results": [], "total": 0, "low_confidence": True, "error": "Policy services unavailable."}
#         sql_result, policy_result = sql_r, pol_r

#     return _build_flight_payload(route, sql_result, policy_result)


# async def execute_flight_status(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
#     flight_no = args.get("flight_no")
#     if not flight_no:
#         raise HTTPException(status_code=400, detail="flight_no required")
#     date = args.get("date") or "today"
#     question = f"What is the flight status and details for flight {flight_no} on {date}?"
#     return await _gateway_router_flow("get_flight_status", args, question, utterance)


# async def execute_flight_search(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
#     origin, destination = args.get("origin"), args.get("destination")
#     if not all([origin, destination]):
#         raise HTTPException(status_code=400, detail="origin and destination required")
    
#     # FIX: Prioritize raw utterance to preserve natural language context
#     if utterance:
#         question = utterance
#     else:
#         date_from, date_to, date = args.get("date_from"), args.get("date_to"), args.get("date")
#         if date_from and date_to:
#             question = f"Find all available flights from {origin} to {destination} between {date_from} and {date_to}."
#         elif date:
#             question = f"Find all available flights from {origin} to {destination} on {date}."
#         else:
#             question = f"Find upcoming flights from {origin} to {destination}."
            
#     return await _gateway_router_flow("search_flights", args, question, utterance)


# async def execute_policy_search(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
#     query = args.get("query")
#     if not query:
#         raise HTTPException(status_code=400, detail="query required")
#     return await _gateway_router_flow("search_policy", args, query, utterance)


# async def execute_tool_call(name: str, args: Dict[str, Any], utterance: str = "", history: list = None) -> Dict[str, Any]:
#     started = time.perf_counter()
#     try:
#         violation = tool_args_violation(args)
#         if violation:
#             logger.warning(f"⚠️ Tool call '{name}' rejected by safety check: {violation}")
#             return {"error": violation}
#         if name == "get_flight_status": return await execute_flight_status(args, utterance)
#         elif name == "search_policy": return await execute_policy_search(args, utterance)
#         elif name == "search_flights": return await execute_flight_search(args, utterance)
#         elif name == "initiate_booking_handoff":
#             # Fire-and-forget email dispatch
#             asyncio.create_task(send_booking_email_async(args, utterance, history or []))
            
#             # Language mirroring heuristic for handoff message
#             is_hindi = bool(re.search(r'[\u0900-\u097F]|hai|karna|rahahoon|madad|kripya', utterance, re.IGNORECASE))
#             response_text = (
#                 "Aage ki booking process ke liye main aapki request hamare team member ko forward kar raha hoon. "
#                 "Wo jald hi documentation aur payment mein aapki madad karenge." if is_hindi else
#                 "For further booking process, I am forwarding your request to my team member. "
#                 "They will assist you with documentation and payment shortly."
#             )
            
#             return {
#                 "route": "handoff",
#                 "status": "forwarded",
#                 "message": "Request forwarded to support team (i-shyam.singh@affine.ai)",
#                 "summary": response_text
#             }
#         return {"error": f"Unknown tool: {name}"}
#     except Exception as e:
#         logger.error(f"❌ Tool execution failed: {e}", exc_info=True)
#         return {"error": "Service temporarily unavailable."}
#     finally:
#         logger.info(f"🛠️ Tool '{name}' finished in {(time.perf_counter() - started) * 1000:.0f} ms")


# async def _run_tool_with_timeout(fc: Dict[str, Any], utterance: str = "", history: list = None):
#     name = fc.get("name")
#     try:
#         result = await asyncio.wait_for(execute_tool_call(name, fc.get("args") or {}, utterance, history), timeout=TOOL_TIMEOUT_SECONDS)
#     except asyncio.TimeoutError:
#         logger.error(f"❌ Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s")
#         result = {"error": "The lookup is taking too long. Please try again in a moment."}
#     return fc, result


# # ==============================================================================
# # WEBSOCKET PROXY LOGIC
# # ==============================================================================
# async def relay_client_to_gemini(websocket: WebSocket, gemini_ws, setup_done: asyncio.Event):
#     try:
#         try:
#             await asyncio.wait_for(setup_done.wait(), timeout=5.0)
#         except asyncio.TimeoutError:
#             pass
#         while True:
#             message = await websocket.receive()
#             if message["type"] == "websocket.disconnect":
#                 break
#             if message.get("text") is not None:
#                 text_data = message["text"]
#                 if "setup" in text_data:
#                     try:
#                         if "setup" in json.loads(text_data):
#                             continue
#                     except Exception:
#                         pass
#                 await gemini_ws.send(text_data)
#             elif message.get("bytes") is not None:
#                 await gemini_ws.send(message["bytes"])
#     except WebSocketDisconnect:
#         pass


# async def relay_gemini_to_client(websocket: WebSocket, gemini_ws, session_key: Optional[str], setup_done: asyncio.Event, ctx: Dict[str, Any]) -> Dict[str, Any]:
#     mw = getattr(app.state, "middleware", None)
#     outcome: Dict[str, Any] = {"received_setup_complete": False, "gemini_close_code": None, "gemini_close_reason": None}
#     greeting_triggered = False
#     try:
#         async for raw in gemini_ws:
#             text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
#             data = json.loads(text)

#             server_content = data.get("serverContent") or {}
#             in_tr = server_content.get("inputTranscription")
#             if in_tr and in_tr.get("text"):
#                 ctx["utterance"] = (ctx.get("utterance", "") + in_tr["text"])[-2000:]
#                 ctx.setdefault("history", []).append(in_tr["text"])
#                 if len(ctx["history"]) > 10:
#                     ctx["history"] = ctx["history"][-10:]
            
#             # FIX: Removed premature ctx["utterance"] = "" on turnComplete to prevent race condition with tool calls.
#             # Utterance is safely cleared after tool execution completes (see line ~405).

#             if data.get("setupComplete") is not None:
#                 outcome["received_setup_complete"] = True
#                 if not greeting_triggered:
#                     greeting_triggered = True
#                     await gemini_ws.send(json.dumps({
#                         "clientContent": {"turns": [{"role": "user", "parts": [{"text": "Hi. Greet me politely."}]}], "turnComplete": True}
#                     }))
#                     logger.info("👋 Sent kickoff turn so Gemini greets the customer first")
#                     setup_done.set()

#             function_calls = data.get("toolCall", {}).get("functionCalls")
#             if function_calls:
#                 for fc in function_calls:
#                     await websocket.send_json({"toolStatus": {"name": fc.get("name"), "state": "started"}})
#                 utterance = _clean_utterance(ctx.get("utterance"))
#                 history = ctx.get("history", [])
#                 results = await asyncio.gather(*[_run_tool_with_timeout(fc, utterance, history) for fc in function_calls])
#                 responses = []
#                 for fc, result in results:
#                     await websocket.send_json({"toolResult": {"name": fc.get("name"), "data": result}})
                    
#                     output_parts = []
#                     if isinstance(result, dict):
#                         summary = result.get("summary")
#                         if summary:
#                             output_parts.append(summary)
                        
#                         policy_info = result.get("policy_information")
#                         if policy_info and isinstance(policy_info, dict):
#                             results_list = policy_info.get("results", [])
#                             if policy_info.get("low_confidence") or not results_list:
#                                 output_parts.append("I could not find a reliable answer in our policy documents. Please check with the airline.")
#                             else:
#                                 for r in results_list[:3]:
#                                     src = r.get("source", "Policy document")
#                                     cont = r.get("content", "")
#                                     output_parts.append(f"Source ({src}): {cont}")
                        
#                         output_text = "\n\n".join(output_parts) if output_parts else "No results found."
#                         gemini_response = {"output": output_text}
#                     else:
#                         gemini_response = {"output": str(result)[:1000]}
                        
#                     responses.append({"id": fc.get("id"), "name": fc.get("name"), "response": gemini_response})
#                 await gemini_ws.send(json.dumps({"toolResponse": {"functionResponses": responses}}))
                
#                 # Safely clear utterance ONLY after tool execution is fully complete
#                 ctx["utterance"] = ""
#                 continue

#             res_update = data.get("sessionResumptionUpdate")
#             if res_update and res_update.get("resumable") and mw and getattr(mw, "redis_client", None) and session_key:
#                 if new_handle := res_update.get("newHandle"):
#                     try:
#                         await mw.redis_client.set(f"session:resume:{session_key}", new_handle, ex=3600)
#                     except Exception as e:
#                         logger.warning(f"⚠️ Could not persist resumption handle: {e}")

#             if data.get("goAway"):
#                 logger.info(f"⚠️ Gemini sent goAway: {data['goAway']}")
#             await websocket.send_text(text)
#     except websockets.exceptions.ConnectionClosed as e:
#         outcome["gemini_close_code"], outcome["gemini_close_reason"] = e.code, e.reason
#         if not outcome["received_setup_complete"]:
#             logger.error(f"❌ Gemini closed connection early (code={e.code}, reason={e.reason!r}). Check GEMINI_API_KEY.")
#         else:
#             logger.info(f"ℹ️ Gemini session ended (code={e.code}, reason={e.reason!r})")
#     except WebSocketDisconnect:
#         pass
#     return outcome


# @app.websocket("/ws/audio")
# async def websocket_audio(websocket: WebSocket):
#     client_ip = websocket.client.host if websocket.client else "unknown"
#     if not _api_key_ok(websocket.query_params.get("api_key")):
#         await websocket.close(code=4001, reason="Unauthorized")
#         return

#     mw = getattr(app.state, "middleware", None)
#     if mw and not await mw.check_rate_limit(key=f"ws:{client_ip}", limit=WS_RATE_LIMIT, window_seconds=60):
#         await websocket.close(code=4008, reason="Rate limit exceeded")
#         return

#     if not GEMINI_API_KEY:
#         await websocket.close(code=1011, reason="Voice agent not configured")
#         return

#     semaphore = getattr(mw, "voice_session_semaphore", None) if mw else None
#     if semaphore:
#         try:
#             await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
#         except asyncio.TimeoutError:
#             await websocket.accept()
#             await websocket.close(code=1013, reason="Server at capacity, please retry shortly")
#             return

#     await websocket.accept()
#     session_key = websocket.query_params.get("session_id")
#     resume_handle = websocket.query_params.get("resume")

#     if not resume_handle and session_key and mw and getattr(mw, "redis_client", None):
#         try:
#             stored = await mw.redis_client.get(f"session:resume:{session_key}")
#             if stored:
#                 resume_handle = stored.decode("utf-8") if isinstance(stored, bytes) else stored
#         except Exception as e:
#             logger.warning(f"⚠️ Could not read resumption handle from Redis: {e}")

#     try:
#         gemini_ws = await asyncio.wait_for(
#             websockets.connect(GEMINI_WS_URL, max_size=GEMINI_WS_MAX_SIZE, ping_interval=None),
#             timeout=GEMINI_CONNECT_TIMEOUT_SECONDS,
#         )
#     except Exception as e:
#         logger.error(f"❌ Upstream Gemini connect failed (client={client_ip}): {e!r}")
#         if semaphore:
#             semaphore.release()
#         await websocket.close(code=1011, reason="Upstream voice service unavailable")
#         return

#     relay_outcome = None
#     setup_done = asyncio.Event()
#     ctx: Dict[str, Any] = {"utterance": "", "history": []}
#     try:
#         async with gemini_ws:
#             await gemini_ws.send(json.dumps(build_setup_message(resume_handle=resume_handle)))
#             t_up = asyncio.create_task(relay_client_to_gemini(websocket, gemini_ws, setup_done))
#             t_down = asyncio.create_task(relay_gemini_to_client(websocket, gemini_ws, session_key, setup_done, ctx))
#             done, pending = await asyncio.wait({t_up, t_down}, return_when=asyncio.FIRST_COMPLETED)
#             for t in pending:
#                 t.cancel()
#             await asyncio.gather(*pending, return_exceptions=True)
#             if t_down in done and not t_down.cancelled():
#                 try:
#                     relay_outcome = t_down.result()
#                 except Exception:
#                     relay_outcome = None
#     except WebSocketDisconnect:
#         pass
#     except Exception as e:
#         logger.error(f"❌ Voice relay failed mid-session (client={client_ip}): {e}", exc_info=True)
#     finally:
#         if semaphore:
#             semaphore.release()
#         try:
#             if relay_outcome and not relay_outcome.get("received_setup_complete") and relay_outcome.get("gemini_close_code") is not None:
#                 reason = f"Upstream rejected session: {relay_outcome.get('gemini_close_reason') or 'no reason given'}"
#                 await websocket.close(code=1011, reason=reason[:120])
#             else:
#                 await websocket.close()
#         except Exception:
#             pass


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
"""
Airline Voice Agent Backend
FastAPI API Gateway and Real-Time Orchestrator

Architecture: the LLM router lives HERE, at the gateway. Every tool call Gemini emits
(get_flight_status, search_flights, search_policy) is classified FIRST as sql / policy / mixed,
then dispatched: sql -> dynamic SQL pipeline, policy -> RAG pipeline (Redis cache + AI Search),
mixed -> both in parallel with asyncio.gather. _build_flight_payload merges the results.
The flow module and the middleware never import main.py, so there are no circular dependencies.
"""
import os
import json
import asyncio
import logging
import math
import re
import secrets
import time
import smtplib
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import websockets
from datetime import datetime
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from pathlib import Path as _Path

# Always load backend/.env even when uvicorn is started from the repo root
_BACKEND_DIR = _Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv()  # optional override from process cwd / root .env

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
_file_handler = logging.FileHandler(os.getenv("LOG_FILE", str(_BACKEND_DIR / "backend.log")), encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(_file_handler)
for _n in ("websockets", "websockets.client", "websockets.server"):
    logging.getLogger(_n).setLevel(logging.WARNING)

IST = pytz.timezone("Asia/Kolkata")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-exp")
GEMINI_VOICE_NAME = os.getenv("GEMINI_VOICE_NAME", "Puck")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY")
_base_endpoint = os.getenv("GEMINI_ENDPOINT", "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
GEMINI_WS_URL = f"{_base_endpoint}?key={GEMINI_API_KEY}" if "?" not in _base_endpoint else _base_endpoint
GEMINI_WS_MAX_SIZE = int(os.getenv("GEMINI_WS_MAX_SIZE_BYTES", str(2 * 1024 * 1024)))
REST_RATE_LIMIT = int(os.getenv("REST_RATE_LIMIT_PER_MINUTE", "60"))
WS_RATE_LIMIT = int(os.getenv("WS_CONNECT_RATE_LIMIT_PER_MINUTE", "10"))
GEMINI_CONNECT_TIMEOUT_SECONDS = int(os.getenv("GEMINI_CONNECT_TIMEOUT_SECONDS", "8"))
TOOL_TIMEOUT_SECONDS = float(os.getenv("TOOL_TIMEOUT_SECONDS", "20.0"))
MAX_TOOL_ARG_LENGTH = 300
GEMINI_INPUT_TRANSCRIPTION = os.getenv("GEMINI_INPUT_TRANSCRIPTION", "true").lower() == "true"
SEND_TOOL_EVENTS_TO_CLIENT = os.getenv("SEND_TOOL_EVENTS_TO_CLIENT", "false").lower() == "true"
FLIGHT_UI_DEBUG = os.getenv("FLIGHT_UI_DEBUG", "false").lower() == "true"
MAX_UTTERANCE_LENGTH = 500


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(v) for v in value]
    return value


def _prepare_flight_rows_for_client(rows: list) -> list:
    """Ensure flight rows are JSON-serializable (no NaN/datetime) for WebSocket send."""
    cleaned = [_sanitize_json_value(r) for r in rows if isinstance(r, dict)]
    return json.loads(json.dumps(cleaned, default=str))


async def _send_client_tool_result(websocket: WebSocket, fc: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Send flight table data to the browser; never raise (Gemini toolResponse must still run)."""
    tool_name = fc.get("name")
    try:
        if SEND_TOOL_EVENTS_TO_CLIENT:
            payload = _sanitize_json_value(result) if isinstance(result, dict) else result
            await websocket.send_text(json.dumps({"toolResult": {"name": tool_name, "data": payload}}))
            if FLIGHT_UI_DEBUG:
                fr = result.get("flight_results") if isinstance(result, dict) else None
                logger.info(f"📤 toolResult SENT (debug full) tool={tool_name} flight_rows={len(fr) if isinstance(fr, list) else 'n/a'}")
            return

        if not isinstance(result, dict):
            if FLIGHT_UI_DEBUG:
                logger.info(f"⏭️ toolResult SKIPPED tool={tool_name} reason=result_not_dict")
            return

        flight_rows = result.get("flight_results")
        if not isinstance(flight_rows, list) or len(flight_rows) == 0:
            if FLIGHT_UI_DEBUG:
                logger.info(
                    f"⏭️ toolResult SKIPPED tool={tool_name} reason=empty_or_missing_flight_results "
                    f"type={type(flight_rows).__name__} len={len(flight_rows) if isinstance(flight_rows, list) else 'n/a'}"
                )
            return

        safe_rows = _prepare_flight_rows_for_client(flight_rows)
        count = int(result.get("count") or len(safe_rows))
        await websocket.send_text(json.dumps({
            "toolResult": {
                "name": tool_name,
                "data": {"flight_results": safe_rows, "count": count},
            }
        }))
        if FLIGHT_UI_DEBUG:
            logger.info(f"📤 toolResult SENT tool={tool_name} flight_rows={len(safe_rows)} count={count}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to send toolResult to browser (tool={tool_name}): {e!r}")

# Reminder attached to EVERY tool response so the model keeps speaking in the user's current language
# (tool data / policy text is usually English and used to pull the model into drifting languages).
LANGUAGE_REMINDER = (
    "Speak your reply in the SAME language the user is currently speaking. "
    "Do NOT switch language because this data is in English or another language. "
    "Translate/paraphrase it into the user's current language. Keep it to 2-3 short sentences."
)

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"ignore (all )?(previous|prior|above) instructions",
        r"disregard (the )?(system|developer) (prompt|message|instructions)",
        r"you are now (?:in )?(?:dan|developer|admin) mode",
        r"reveal (the )?(system prompt|hidden instructions|api key|secret)",
        r"jailbreak",
    )
]

# Heuristic for detecting Hindi / Hinglish in the user's utterance (used for the handoff summary text).
# Word-boundary matching avoids false positives like "chair" / "hair" matching "hai".
_HINDI_PATTERN = re.compile(
    r"[\u0900-\u097F]|\b(hai|hain|karna|karni|karo|kijiye|chahiye|mujhe|madad|kripya|aap|mera|meri|"
    r"hamare|kya|kaise|kab|kahan|nahi|haan|batao|dikhao|bukk?ing)\b",
    re.IGNORECASE,
)


def tool_args_violation(args: Dict[str, Any]) -> Optional[str]:
    for key, value in (args or {}).items():
        if isinstance(value, str):
            if len(value) > MAX_TOOL_ARG_LENGTH:
                return f"Argument '{key}' is too long."
            if any(p.search(value) for p in _INJECTION_PATTERNS):
                return "Request blocked by safety check."
    return None


async def send_booking_email_async(booking_data: dict, recent_utterance: str, history: list):
    """Non-blocking background email dispatch for booking handoffs."""
    def _send():
        recipient = "i-shyam.singh@affine.ai"
        origin = booking_data.get('origin', 'Not specified')
        destination = booking_data.get('destination', 'Not specified')
        flight_no = booking_data.get('flight_number', 'Not specified')

        subject = f"✈️ [Booking Referral] {origin} to {destination}"

        body = f"""New Booking Referral:
--------------------------------------------------
Customer Request / Utterance: {recent_utterance}
Route: {origin} to {destination}
Flight Details: {flight_no}
Notes: {booking_data.get('customer_note', 'Customer ready for documentation & payment')}

Recent Conversation History:
{history[-4:] if history else 'N/A'}
--------------------------------------------------
Dispatched automatically by Airline Voice Agent Gateway.
"""
        logger.info(f"📧 [BOOKING EMAIL LOGGED TO {recipient}]:\n{body}")

        smtp_host = os.getenv("SMTP_HOST")
        if smtp_host:
            try:
                msg = MIMEMultipart()
                msg["From"] = os.getenv("SMTP_FROM", "voice-agent@airline.com")
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))
                with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", 587))) as server:
                    if os.getenv("SMTP_TLS", "true").lower() == "true":
                        server.starttls()
                    if os.getenv("SMTP_USER"):
                        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
                    server.send_message(msg)
            except Exception as e:
                logger.error(f"Failed to dispatch email via SMTP: {e}")

    await asyncio.to_thread(_send)


def build_setup_message(resume_handle: Optional[str] = None) -> dict:
    now_ist = datetime.now(IST)
    time_context = now_ist.strftime("%I:%M %p")
    date_context = now_ist.strftime("%A, %d %B %Y")

    return {
        "setup": {
            "model": f"models/{GEMINI_MODEL_NAME}",
            "systemInstruction": {
                "parts": [{
                    "text": (
                        f"You are Sky, a highly professional airline concierge. Current local time is {time_context} "
                        f"and today's date is {date_context} (India Standard Time).\n\n"
                        "CORE SYSTEM BEHAVIOR & PRIORITIES:\n\n"
                        "1. LANGUAGE LOCK (HIGHEST PRIORITY - OVERRIDES EVERYTHING ELSE):\n"
                        "   - Your conversation language starts as ENGLISH.\n"
                        "   - Detect the language of the user's LATEST spoken message and reply ONLY in that language.\n"
                        "   - STAY in the current language for every following turn. Do NOT switch languages on your own, "
                        "even if tool results, flight data, policy text, or earlier messages contain another language, "
                        "and even if the user's message contains a few words of another language "
                        "(e.g. one Hindi word or a name inside an English sentence).\n"
                        "   - Switch ONLY when the user clearly speaks a full sentence or request in a different language, "
                        "or explicitly asks you to change language. Once they switch, stay in the new language until they switch again.\n"
                        "   - English sentence = English reply. Hindi sentence = Hindi reply. "
                        "Hinglish (Hindi in Roman script) sentence = Hinglish reply.\n"
                        "   - Tool outputs are usually in English; always paraphrase them into the user's CURRENT language when speaking.\n"
                        "   - Keep all voice responses concise, conversational, and direct (2-3 sentences max).\n\n"
                        "2. FLIGHT SEARCH PRIORITY:\n"
                        "   - When the user asks for flights, schedules, fares, or routes, you MUST ALWAYS call the `search_flights` tool. NEVER answer flight availability or schedules from memory.\n"
                        "   - For specific flight number inquiry or status, call `get_flight_status`.\n"
                        "   - For baggage, cancellation, refund, or rules, call `search_policy`.\n"
                        "   - When search_flights returns MANY flights: say the total number of flights, then mention at least 5 of them as examples spread across different dates (for example: 'on 13th there is ..., on 15th ..., on 18th ...'), including airline and flight number, and optionally the departure time or fare. NEVER read out the whole list. After that, ask which date or time the user prefers so you can narrow it down.\n"
                        "   - When there are 5 or fewer flights, read them all briefly.\n"
                        "   - Speak dates naturally (for example '13th October'), not in numeric form like 2026-10-13. Say fares as '1200 rupees'. Do not read long flight numbers digit by digit more than once.\n"
                        "   - For this flight-list case you may use up to 4-5 short sentences (this overrides the general 2-3 sentence limit). Everything else stays at 2-3 sentences.\n\n"
                        "3. INSTANT BOOKING HANDOFF PROTOCOL:\n"
                        "   - When the user indicates they want to BOOK or RESERVE a flight (e.g., 'Mujhe flight book karni hai', 'Book this flight', 'Reserve seat'):\n"
                        "     Do NOT ask multi-step questions for passenger count, meals, or medical conditions.\n"
                        "     Immediately call the `initiate_booking_handoff` tool.\n"
                        "     Then speak the handoff message in the user's CURRENT conversation language (per the Language Lock above), meaning exactly this:\n"
                        "     - English: 'For further booking process, I am forwarding your request to my team member. They will assist you with documentation and payment shortly.'\n"
                        "     - Hindi / Hinglish: 'Aage ki booking process ke liye main aapki request hamare team member ko forward kar raha hoon. Wo jald hi documentation aur payment mein aapki madad karenge.'\n"
                        "     Use the Hindi/Hinglish version ONLY if the user is currently speaking Hindi/Hinglish. Otherwise use the English version.\n"
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
                        "description": "Check real-time status of a specific flight number. If the user gives no date, omit 'date' and the flight nearest to today is returned.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "flight_no": {"type": "STRING", "description": "Flight number, e.g. AI204"},
                                "date": {"type": "STRING", "description": "Flight date in YYYY-MM-DD format (optional)."},
                            },
                            "required": ["flight_no"],
                        },
                    },
                    {
                        "name": "search_flights",
                        "description": "Search available flights between origin and destination cities. Use 'date' for a single day, OR 'date_from' and 'date_to' together for a range of dates.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "origin": {"type": "STRING", "description": "Departure city or airport code (e.g., Bangalore, BLR)"},
                                "destination": {"type": "STRING", "description": "Arrival city or airport code (e.g., Delhi, DEL)"},
                                "date": {"type": "STRING", "description": "A single flight date in YYYY-MM-DD format. Omit if using date_from/date_to."},
                                "date_from": {"type": "STRING", "description": "Start of a date range, YYYY-MM-DD."},
                                "date_to": {"type": "STRING", "description": "End of a date range, YYYY-MM-DD."},
                            },
                            "required": ["origin", "destination"],
                        },
                    },
                    {
                        "name": "search_policy",
                        "description": "Search airline policies for baggage, cancellation, refunds, changes, check-in or special items.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "The policy question in plain words."},
                                "category": {"type": "STRING", "description": "Optional: baggage, cancellation, refund, check-in."},
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "initiate_booking_handoff",
                        "description": "Call this tool immediately when the user wants to book or reserve a flight. Do not ask further qualifying questions.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "flight_number": {"type": "STRING", "description": "The specific flight number (optional)"},
                                "origin": {"type": "STRING", "description": "Departure city if mentioned"},
                                "destination": {"type": "STRING", "description": "Arrival city if mentioned"},
                                "customer_note": {"type": "STRING", "description": "Any specific notes mentioned by customer"}
                            },
                            "required": []
                        }
                    },
                ]
            }],
            "sessionResumption": {"handle": resume_handle} if resume_handle else {},
            "contextWindowCompression": {"slidingWindow": {}},
            **({"inputAudioTranscription": {}} if GEMINI_INPUT_TRANSCRIPTION else {}),
        }
    }


try:
    from src.middleware import AirlineMiddleware
    MIDDLEWARE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Middleware not available: {e}")
    MIDDLEWARE_AVAILABLE = False
    AirlineMiddleware = None

try:
    from autogen_flow.airline_autogen_flow import route_question, run_sql_pipeline, warm_up, db_healthy
    FLOW_AVAILABLE = True
except Exception as e:
    logger.error(f"❌ SQL flow import failed (all flight tools will return 503): {e}", exc_info=True)
    FLOW_AVAILABLE = False
    route_question = run_sql_pipeline = warm_up = db_healthy = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.middleware = None
    if MIDDLEWARE_AVAILABLE:
        try:
            app.state.middleware = AirlineMiddleware()
            await app.state.middleware.initialize()
            logger.info("✅ Middleware initialized")
        except Exception as e:
            logger.error(f"❌ Middleware initialization failed: {e}")
            app.state.middleware = None
    if FLOW_AVAILABLE:
        try:
            await asyncio.to_thread(warm_up)
        except Exception as e:
            logger.warning(f"⚠️ SQL flow warm-up failed: {e}")
    yield
    if getattr(app.state, "middleware", None):
        await app.state.middleware.close()
        app.state.middleware = None


app = FastAPI(title="Airline Voice Agent Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


def _api_key_ok(provided: Optional[str]) -> bool:
    if not BACKEND_API_KEY:
        return True
    return secrets.compare_digest((provided or "").encode(), BACKEND_API_KEY.encode())


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not _api_key_ok(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


async def enforce_rest_rate_limit(request: Request):
    if not getattr(app.state, "middleware", None):
        return
    client_ip = request.client.host if request.client else "unknown"
    allowed = await app.state.middleware.check_rate_limit(key=f"rest:{client_ip}", limit=REST_RATE_LIMIT, window_seconds=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")


# ==============================================================================
# REST API ENDPOINTS (/health, /execute-tool)
# ==============================================================================
class HealthResponse(BaseModel):
    status: str
    message: str
    version: str = "1.5.0"
    services: Dict[str, str] = {}


class ToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    utterance: Optional[str] = None


class ToolResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


@app.get("/health", response_model=HealthResponse)
async def health_check():
    services = {}
    mw = getattr(app.state, "middleware", None)
    if mw:
        services["azure_search"] = "connected" if mw.search_client else "disconnected"
        services["redis"] = "connected" if await mw.is_redis_healthy() else "disconnected"
        services["azure_openai"] = "connected" if mw.openai_healthy else "disconnected"
    if FLOW_AVAILABLE:
        services["azure_sql"] = "connected" if await asyncio.to_thread(db_healthy) else "disconnected"
    else:
        services["azure_sql"] = "disconnected"
    services["gemini_live"] = "configured" if GEMINI_API_KEY else "not_configured"
    return HealthResponse(status="healthy", message="Backend is running and ready", services=services)


@app.post("/execute-tool", response_model=ToolResponse, dependencies=[Depends(verify_api_key), Depends(enforce_rest_rate_limit)])
async def execute_tool(request: ToolRequest):
    try:
        violation = tool_args_violation(request.arguments)
        if violation:
            raise HTTPException(status_code=400, detail=violation)
        utt = _clean_utterance(request.utterance)
        if request.tool_name == "get_flight_status": result = await execute_flight_status(request.arguments, utt)
        elif request.tool_name == "search_policy": result = await execute_policy_search(request.arguments, utt)
        elif request.tool_name == "search_flights": result = await execute_flight_search(request.arguments, utt)
        else: raise HTTPException(status_code=400, detail=f"Unknown tool: {request.tool_name}")
        return ToolResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}", exc_info=True)
        return ToolResponse(success=False, error="The service is temporarily unavailable.")


# ==============================================================================
# ORCHESTRATION LAYER
# ==============================================================================
def _clean_utterance(text: Optional[str]) -> str:
    text = (text or "").strip()[:MAX_UTTERANCE_LENGTH]
    if text and any(p.search(text) for p in _INJECTION_PATTERNS):
        return ""
    return text


_TOOL_DEFAULT_ROUTE = {"get_flight_status": "sql", "search_flights": "sql", "search_policy": "policy"}


async def run_policy_pipeline(query: str, category: Optional[str] = None) -> Dict[str, Any]:
    mw = getattr(app.state, "middleware", None)
    if not mw or not getattr(mw, "search_client", None):
        return {"results": [], "total": 0, "low_confidence": True, "error": "Policy services unavailable."}
    return await mw.search_policy(query=query, category=category)


def _row_flight_number(row: Dict[str, Any]) -> str:
    return str(row.get("flight_number") or row.get("flight_no") or row.get("flightNumber") or "").strip()


def _row_fare(row: Dict[str, Any]) -> Optional[float]:
    for key in ("total_fare_inr", "price_inr", "fare"):
        val = row.get(key)
        if val is None:
            continue
        try:
            amount = float(val)
            if amount > 0:
                return amount
        except (TypeError, ValueError):
            continue
    return None


def _row_date_sort_key(row: Dict[str, Any]) -> tuple:
    raw = row.get("flight_date") or ""
    date_part = str(raw).split("T")[0] if raw else ""
    time_part = str(row.get("departure_time") or "")
    return (date_part, time_part)


def _format_digest_date(date_val: Any) -> str:
    if not date_val:
        return "Unknown date"
    date_str = str(date_val).split("T")[0]
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return date_str


def _format_digest_time(time_val: Any) -> str:
    if not time_val:
        return ""
    text = str(time_val)
    return text[:5] if len(text) >= 5 else text


def _pick_example_flights(rows: list, max_examples: int = 5) -> list:
    if not rows:
        return []
    sorted_rows = sorted(rows, key=_row_date_sort_key)
    total = len(rows)
    if total <= max_examples:
        return sorted_rows

    target = max(max_examples, 5)
    picked: list = []
    seen: set = set()

    def identity(row: Dict[str, Any]) -> tuple:
        return (_row_date_sort_key(row), _row_flight_number(row))

    earliest_by_date: Dict[str, Dict[str, Any]] = {}
    for row in sorted_rows:
        date_key = _row_date_sort_key(row)[0]
        if date_key and date_key not in earliest_by_date:
            earliest_by_date[date_key] = row

    for date_key in sorted(earliest_by_date.keys()):
        if len(picked) >= target:
            break
        row = earliest_by_date[date_key]
        picked.append(row)
        seen.add(identity(row))

    for row in sorted_rows:
        if len(picked) >= target:
            break
        key = identity(row)
        if key not in seen:
            picked.append(row)
            seen.add(key)

    return picked[:target]


def build_flight_digest(rows: list, max_examples: int = 5) -> str:
    if not rows:
        return "TOTAL FLIGHTS: 0. NO FLIGHTS FOUND."

    total = len(rows)
    sorted_rows = sorted(rows, key=_row_date_sort_key)
    date_keys = sorted({k[0] for k in (_row_date_sort_key(r) for r in sorted_rows) if k[0]})
    date_labels = [_format_digest_date(d) for d in date_keys]

    fares = [f for f in (_row_fare(r) for r in rows) if f is not None]
    cheapest = min(fares) if fares else None

    examples = _pick_example_flights(rows, max_examples)
    example_chunks = []
    for idx, row in enumerate(examples, 1):
        chunk = f"{idx}) {_format_digest_date(row.get('flight_date'))} - {row.get('airline') or 'Airline'} {_row_flight_number(row) or '—'}"
        dep = _format_digest_time(row.get("departure_time"))
        if dep:
            chunk += f", departs {dep}"
        fare = _row_fare(row)
        if fare is not None:
            chunk += f", Rs {int(round(fare))}"
        example_chunks.append(chunk)

    dates_line = ", ".join(date_labels[:12])
    if len(date_labels) > 12:
        dates_line += ", ..."

    parts = [f"TOTAL FLIGHTS: {total}."]
    if date_labels:
        parts.append(f"DATES AVAILABLE: {dates_line}.")
    if cheapest is not None:
        parts.append(f"CHEAPEST: Rs {int(round(cheapest))}.")
    parts.append("EXAMPLES: " + " | ".join(example_chunks) + ".")
    return " ".join(parts)


def _flight_search_gemini_lines(result: Dict[str, Any]) -> list:
    """Plain-text flight digest + speak guidance for Gemini toolResponse (voice summarization)."""
    if "flight_results" not in result:
        return []
    rows = result.get("flight_results")
    if not isinstance(rows, list):
        return []

    if len(rows) == 0:
        return [
            "NO FLIGHTS FOUND for this search. Tell the user no flights were found for that route or dates, "
            "and ask if they want to try another date or route."
        ]

    lines = [build_flight_digest(rows)]
    count = len(rows)
    if count > 5:
        lines.append(
            "Tell the user the total count, mention the dates, name at least 5 example flights briefly "
            "(date + airline + flight number, and time or fare if short), then ask which date or flight they prefer. "
            "Do NOT read every flight."
        )
    else:
        lines.append("Read out these flights briefly, then ask which one they want.")
    return lines


def _build_flight_payload(route: str, sql_result: Optional[Dict[str, Any]], policy_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {
        "route": route,
        "dynamic_sql_used": sql_result.get("query") if sql_result else None,
        "flight_results": sql_result.get("rows", []) if sql_result else [],
        "count": sql_result.get("count", 0) if sql_result else 0,
        "summary": sql_result.get("answer") if sql_result else "",
    }
    if policy_result is not None:
        payload["policy_information"] = policy_result
    return payload


async def _gateway_router_flow(tool: str, args: Dict[str, Any], tool_question: str, utterance: str = "") -> Dict[str, Any]:
    if not FLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="Backend data service unavailable.")

    # Bypass router LLM for deterministic flight tools to save ~2.5s latency
    if tool in ("search_flights", "get_flight_status"):
        logger.info(f"🚦 Direct SQL route for tool={tool} utterance={utterance!r}")
        sql_result = await asyncio.to_thread(run_sql_pipeline, tool_question)
        return _build_flight_payload("sql", sql_result, None)

    category = args.get("category")
    hint = f"\n(Tool requested: {tool}, args: {json.dumps(args, ensure_ascii=False)[:300]})"
    try:
        routing = await asyncio.to_thread(route_question, (utterance or tool_question) + hint)
    except Exception as e:
        logger.error(f"❌ Router raised: {e!r}")
        routing = {"fallback": True}

    if routing.get("fallback"):
        route = _TOOL_DEFAULT_ROUTE.get(tool, "sql")
        sql_q = pol_q = tool_question
        logger.warning(f"🚦 Router fallback -> default route '{route}' for tool {tool}")
    else:
        route = routing["route"]
        sql_q = routing.get("sql_question") or tool_question
        pol_q = routing.get("policy_question") or tool_question
    logger.info(f"🚦 Route={route} tool={tool} utterance={utterance!r}")

    sql_result = None
    policy_result = None

    if route == "sql":
        sql_result = await asyncio.to_thread(run_sql_pipeline, sql_q)
    elif route == "policy":
        policy_result = await run_policy_pipeline(pol_q, category)
    else:
        sql_r, pol_r = await asyncio.gather(
            asyncio.to_thread(run_sql_pipeline, sql_q),
            run_policy_pipeline(pol_q, category),
            return_exceptions=True,
        )
        if isinstance(sql_r, BaseException):
            logger.error(f"❌ SQL half of mixed route failed: {sql_r!r}")
            sql_r = {"query": None, "rows": [], "count": 0, "answer": "I could not fetch the flight data right now."}
        if isinstance(pol_r, BaseException):
            logger.error(f"❌ Policy half of mixed route failed: {pol_r!r}")
            pol_r = {"results": [], "total": 0, "low_confidence": True, "error": "Policy services unavailable."}
        sql_result, policy_result = sql_r, pol_r

    return _build_flight_payload(route, sql_result, policy_result)


async def execute_flight_status(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
    flight_no = args.get("flight_no")
    if not flight_no:
        raise HTTPException(status_code=400, detail="flight_no required")
    date = args.get("date") or "today"
    question = f"What is the flight status and details for flight {flight_no} on {date}?"
    return await _gateway_router_flow("get_flight_status", args, question, utterance)


async def execute_flight_search(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
    origin, destination = args.get("origin"), args.get("destination")
    if not all([origin, destination]):
        raise HTTPException(status_code=400, detail="origin and destination required")

    # Prioritize raw utterance to preserve natural language context
    if utterance:
        question = utterance
    else:
        date_from, date_to, date = args.get("date_from"), args.get("date_to"), args.get("date")
        if date_from and date_to:
            question = f"Find all available flights from {origin} to {destination} between {date_from} and {date_to}."
        elif date:
            question = f"Find all available flights from {origin} to {destination} on {date}."
        else:
            question = f"Find upcoming flights from {origin} to {destination}."

    return await _gateway_router_flow("search_flights", args, question, utterance)


async def execute_policy_search(args: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
    query = args.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    return await _gateway_router_flow("search_policy", args, query, utterance)


async def execute_tool_call(name: str, args: Dict[str, Any], utterance: str = "", history: list = None) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        violation = tool_args_violation(args)
        if violation:
            logger.warning(f"⚠️ Tool call '{name}' rejected by safety check: {violation}")
            return {"error": violation}
        if name == "get_flight_status": return await execute_flight_status(args, utterance)
        elif name == "search_policy": return await execute_policy_search(args, utterance)
        elif name == "search_flights": return await execute_flight_search(args, utterance)
        elif name == "initiate_booking_handoff":
            # Fire-and-forget email dispatch
            asyncio.create_task(send_booking_email_async(args, utterance, history or []))

            # Language heuristic for the handoff message (word-boundary match, no substring false positives)
            is_hindi = bool(_HINDI_PATTERN.search(utterance or ""))
            response_text = (
                "Aage ki booking process ke liye main aapki request hamare team member ko forward kar raha hoon. "
                "Wo jald hi documentation aur payment mein aapki madad karenge." if is_hindi else
                "For further booking process, I am forwarding your request to my team member. "
                "They will assist you with documentation and payment shortly."
            )

            return {
                "route": "handoff",
                "status": "forwarded",
                "message": "Request forwarded to support team (i-shyam.singh@affine.ai)",
                "summary": response_text
            }
        return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}", exc_info=True)
        return {"error": "Service temporarily unavailable."}
    finally:
        logger.info(f"🛠️ Tool '{name}' finished in {(time.perf_counter() - started) * 1000:.0f} ms")


async def _run_tool_with_timeout(fc: Dict[str, Any], utterance: str = "", history: list = None):
    name = fc.get("name")
    try:
        result = await asyncio.wait_for(execute_tool_call(name, fc.get("args") or {}, utterance, history), timeout=TOOL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(f"❌ Tool '{name}' timed out after {TOOL_TIMEOUT_SECONDS}s")
        result = {"error": "The lookup is taking too long. Please try again in a moment."}
    return fc, result


# ==============================================================================
# WEBSOCKET PROXY LOGIC
# ==============================================================================
async def relay_client_to_gemini(websocket: WebSocket, gemini_ws, setup_done: asyncio.Event):
    try:
        try:
            await asyncio.wait_for(setup_done.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                text_data = message["text"]
                if "setup" in text_data:
                    try:
                        if "setup" in json.loads(text_data):
                            continue
                    except Exception:
                        pass
                await gemini_ws.send(text_data)
            elif message.get("bytes") is not None:
                await gemini_ws.send(message["bytes"])
    except WebSocketDisconnect:
        pass


async def relay_gemini_to_client(websocket: WebSocket, gemini_ws, session_key: Optional[str], setup_done: asyncio.Event, ctx: Dict[str, Any]) -> Dict[str, Any]:
    mw = getattr(app.state, "middleware", None)
    outcome: Dict[str, Any] = {"received_setup_complete": False, "gemini_close_code": None, "gemini_close_reason": None}
    greeting_triggered = False
    try:
        async for raw in gemini_ws:
            text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            data = json.loads(text)

            server_content = data.get("serverContent") or {}
            in_tr = server_content.get("inputTranscription")
            if in_tr and in_tr.get("text"):
                ctx["utterance"] = (ctx.get("utterance", "") + in_tr["text"])[-2000:]
                ctx.setdefault("history", []).append(in_tr["text"])
                if len(ctx["history"]) > 10:
                    ctx["history"] = ctx["history"][-10:]

            # NOTE: ctx["utterance"] is NOT cleared on turnComplete (race condition with tool calls).
            # It is cleared safely after tool execution completes (see below).

            if data.get("setupComplete") is not None:
                outcome["received_setup_complete"] = True
                if not greeting_triggered:
                    greeting_triggered = True
                    await gemini_ws.send(json.dumps({
                        "clientContent": {"turns": [{"role": "user", "parts": [{"text": "Hi. Greet me politely in English."}]}], "turnComplete": True}
                    }))
                    logger.info("👋 Sent kickoff turn so Gemini greets the customer first")
                    setup_done.set()

            function_calls = data.get("toolCall", {}).get("functionCalls")
            if function_calls:
                if SEND_TOOL_EVENTS_TO_CLIENT:
                    for fc in function_calls:
                        await websocket.send_json({"toolStatus": {"name": fc.get("name"), "state": "started"}})
                utterance = _clean_utterance(ctx.get("utterance"))
                history = ctx.get("history", [])
                results = await asyncio.gather(*[_run_tool_with_timeout(fc, utterance, history) for fc in function_calls])
                responses = []
                for fc, result in results:
                    if isinstance(result, dict):
                        await _send_client_tool_result(websocket, fc, result)

                    output_parts = []
                    if isinstance(result, dict):
                        flight_lines = _flight_search_gemini_lines(result)
                        if flight_lines:
                            output_parts.extend(flight_lines)
                        else:
                            summary = result.get("summary")
                            if summary:
                                output_parts.append(summary)

                        policy_info = result.get("policy_information")
                        if policy_info and isinstance(policy_info, dict):
                            results_list = policy_info.get("results", [])
                            if policy_info.get("low_confidence") or not results_list:
                                output_parts.append("I could not find a reliable answer in our policy documents. Please check with the airline.")
                            else:
                                for r in results_list[:3]:
                                    src = r.get("source", "Policy document")
                                    cont = r.get("content", "")
                                    output_parts.append(f"Source ({src}): {cont}")

                        output_text = "\n\n".join(output_parts) if output_parts else "No results found."
                        gemini_response = {"output": output_text, "instruction": LANGUAGE_REMINDER}
                    else:
                        gemini_response = {"output": str(result)[:1000], "instruction": LANGUAGE_REMINDER}

                    responses.append({"id": fc.get("id"), "name": fc.get("name"), "response": gemini_response})
                await gemini_ws.send(json.dumps({"toolResponse": {"functionResponses": responses}}))

                # Safely clear utterance ONLY after tool execution is fully complete
                ctx["utterance"] = ""
                continue

            res_update = data.get("sessionResumptionUpdate")
            if res_update and res_update.get("resumable") and mw and getattr(mw, "redis_client", None) and session_key:
                if new_handle := res_update.get("newHandle"):
                    try:
                        await mw.redis_client.set(f"session:resume:{session_key}", new_handle, ex=3600)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not persist resumption handle: {e}")

            if data.get("goAway"):
                logger.info(f"⚠️ Gemini sent goAway: {data['goAway']}")
            await websocket.send_text(text)
    except websockets.exceptions.ConnectionClosed as e:
        outcome["gemini_close_code"], outcome["gemini_close_reason"] = e.code, e.reason
        if not outcome["received_setup_complete"]:
            logger.error(f"❌ Gemini closed connection early (code={e.code}, reason={e.reason!r}). Check GEMINI_API_KEY.")
        else:
            logger.info(f"ℹ️ Gemini session ended (code={e.code}, reason={e.reason!r})")
    except WebSocketDisconnect:
        pass
    return outcome


@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not _api_key_ok(websocket.query_params.get("api_key")):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    mw = getattr(app.state, "middleware", None)
    if mw and not await mw.check_rate_limit(key=f"ws:{client_ip}", limit=WS_RATE_LIMIT, window_seconds=60):
        await websocket.close(code=4008, reason="Rate limit exceeded")
        return

    if not GEMINI_API_KEY:
        await websocket.close(code=1011, reason="Voice agent not configured")
        return

    semaphore = getattr(mw, "voice_session_semaphore", None) if mw else None
    if semaphore:
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            await websocket.accept()
            await websocket.close(code=1013, reason="Server at capacity, please retry shortly")
            return

    await websocket.accept()
    session_key = websocket.query_params.get("session_id")
    resume_handle = websocket.query_params.get("resume")

    if not resume_handle and session_key and mw and getattr(mw, "redis_client", None):
        try:
            stored = await mw.redis_client.get(f"session:resume:{session_key}")
            if stored:
                resume_handle = stored.decode("utf-8") if isinstance(stored, bytes) else stored
        except Exception as e:
            logger.warning(f"⚠️ Could not read resumption handle from Redis: {e}")

    try:
        gemini_ws = await asyncio.wait_for(
            websockets.connect(GEMINI_WS_URL, max_size=GEMINI_WS_MAX_SIZE, ping_interval=None),
            timeout=GEMINI_CONNECT_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.error(f"❌ Upstream Gemini connect failed (client={client_ip}): {e!r}")
        if semaphore:
            semaphore.release()
        await websocket.close(code=1011, reason="Upstream voice service unavailable")
        return

    relay_outcome = None
    setup_done = asyncio.Event()
    ctx: Dict[str, Any] = {"utterance": "", "history": []}
    try:
        async with gemini_ws:
            await gemini_ws.send(json.dumps(build_setup_message(resume_handle=resume_handle)))
            t_up = asyncio.create_task(relay_client_to_gemini(websocket, gemini_ws, setup_done))
            t_down = asyncio.create_task(relay_gemini_to_client(websocket, gemini_ws, session_key, setup_done, ctx))
            done, pending = await asyncio.wait({t_up, t_down}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if t_down in done and not t_down.cancelled():
                try:
                    relay_outcome = t_down.result()
                except Exception:
                    relay_outcome = None
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"❌ Voice relay failed mid-session (client={client_ip}): {e}", exc_info=True)
    finally:
        if semaphore:
            semaphore.release()
        try:
            if relay_outcome and not relay_outcome.get("received_setup_complete") and relay_outcome.get("gemini_close_code") is not None:
                reason = f"Upstream rejected session: {relay_outcome.get('gemini_close_reason') or 'no reason given'}"
                await websocket.close(code=1011, reason=reason[:120])
            else:
                await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)