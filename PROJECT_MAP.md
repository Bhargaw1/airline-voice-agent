# Airline Voice Agent — Project Map

This describes the repository as it exists now. It does not change or remove any existing project files. The existing `.env` file was not opened or copied into this document; its secret values are intentionally not reproduced.

## 1. Entry points

### Backend

- Framework: **FastAPI**, served by Uvicorn.
- Documented command (run from `backend\`):

  ```powershell
  uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
  ```

- `backend\src\main.py` also has a `__main__` entry that starts Uvicorn on `0.0.0.0:8000` without reload when run as a module from `backend\`:

  ```powershell
  python -m src.main
  ```

- The FastAPI application is `app` in `backend\src\main.py`. Its lifespan initializes `AirlineMiddleware` and warms the SQL schema cache. The main endpoints are `GET /health`, `POST /execute-tool`, and `WS /ws/audio`.
- `backend\src\main.py` contains a large commented-out older implementation before the active module code. The active module starts at approximately line 722; the earlier commented section is not executed.

### Frontend

- Framework/toolchain: **React 18 + Vite**.
- From `frontend\`, run `npm run dev`; `package.json` invokes `vite`. Vite defaults to port `5173`, with `VITE_DEV_PORT` as an override.
- `frontend\vite.config.js` configures React and a development proxy for `/api` to `VITE_BACKEND_URL` (default `http://127.0.0.1:8000`).
- `frontend\src\main.jsx` mounts `App` from `frontend\src\App.jsx` into `#root` and imports `index.css`.
- The current app calls the backend using the absolute `VITE_BACKEND_URL`/default URL, rather than the configured `/api` proxy path.

### `backend\autogen_flow\`

This is **not a separate server or process**. `backend\src\main.py` imports `route_question`, `run_sql_pipeline`, `warm_up`, and `db_healthy` from `autogen_flow.airline_autogen_flow`; its lifespan warms the flow and its tool handlers invoke it. Start only the FastAPI backend.

Despite the directory name, the SQL flow is custom Python code using the Azure OpenAI SDK (`AzureOpenAI`), SQLAlchemy, pandas, and pyodbc. It does not import or instantiate an AutoGen framework/agent.

## 2. End-to-end interaction

The active flight-search path is voice-first:

1. **Mount the application:** `frontend\src\main.jsx` renders `App` from `frontend\src\App.jsx`.
2. **Start the call:** `App` passes its `handleMicClick` callback to `Header` and `SearchCard`. Those components invoke it from the call/microphone buttons. In `frontend\src\hooks\useRealtimeAgent.js`, `handleMicClick` starts `startSession`.
3. **Capture microphone audio:** `startSession` requests microphone permission with `getUserMedia`, creates an `AudioWorkletNode` using the inline `PCMCaptureProcessor`, and receives 20 ms frames. It converts Float32 samples to PCM16 and base64.
4. **Send audio to the backend:** the hook opens a WebSocket at `${VITE_BACKEND_URL}/ws/audio` (default `ws://127.0.0.1:8000/ws/audio`) and sends `realtimeInput.audio` messages. The backend endpoint is `websocket_audio` in `backend\src\main.py`.
5. **Proxy to the real-time model:** `websocket_audio` checks the optional API key and Gemini configuration, connects to the configured Gemini WebSocket endpoint, and sends `build_setup_message`. The setup declares `GEMINI_MODEL_NAME`, audio output/voice settings, and tools (`search_flights`, `get_flight_status`, `search_policy`, and `initiate_booking_handoff`). `relay_client_to_gemini` forwards client messages; `relay_gemini_to_client` handles model messages and tool calls.
6. **Dispatch a tool call:** Gemini Live (not OpenAI Realtime) decides when to call a declared tool. `relay_gemini_to_client` captures Gemini's input transcription into session context, then calls `_run_tool_with_timeout` → `execute_tool_call` in `backend\src\main.py`.
7. **Look up flights:** `execute_tool_call` dispatches to `execute_flight_search` or `execute_flight_status`. `_gateway_router_flow` sends these flight tools directly to `run_sql_pipeline` in `backend\autogen_flow\airline_autogen_flow.py`; it deliberately bypasses the LLM route classifier for those two tool types.
8. **Generate and run SQL:** `run_sql_pipeline` uses the Azure OpenAI chat deployment to generate a T-SQL `SELECT`, `execute_query` applies read-only checks and runs it against Azure SQL through SQLAlchemy/pyodbc, then `generate_answer` uses the same chat deployment to produce a voice-ready answer. The configured table is `dbo.voice_agent_data`; the generated query is limited by `SQL_FLOW_MAX_ROWS` (default 50).
9. **Return results to both consumers:** `_send_client_tool_result` sends non-empty `flight_results` plus a count to the browser. The backend also returns a `toolResponse` to Gemini; Gemini speaks its answer, which the backend relays to the browser.
10. **Play speech and render the table:** `useRealtimeAgent` decodes Gemini's returned audio and plays PCM at 24 kHz. On `toolResult`, it calls `App`'s `handleFlightResults`; `App` stores rows and renders them through `renderFlightSection` → `FlightTable` in `frontend\src\components\FlightTable.jsx`. `ResultsToolbar` filters/sorts those rows.

### Other tool paths

- **Policy question:** `execute_policy_search` → `_gateway_router_flow` → `route_question` (Azure OpenAI chat classifier) and `run_policy_pipeline` → `AirlineMiddleware.search_policy`. Middleware creates an embedding with Azure OpenAI, optionally checks/caches a vector in Redis, then queries Azure AI Search's configured vector index. Policy search is not an SQL-table lookup.
- **Booking request by voice:** Gemini can call `initiate_booking_handoff`; `execute_tool_call` schedules `send_booking_email_async`. SMTP is optional and its recipient is hard-coded in `main.py`. The flight table's **Book** button is a separate UI path and currently does not invoke this backend tool.
- **Text search:** the input and suggestion chips are displayed, but `App.handleTextSubmit` is intentionally a no-op. Typing a query and pressing Search does not send it to the backend.

## 3. Models, services, and data

### AI models

| Purpose | Model/deployment | Configuration |
|---|---|---|
| Live voice conversation, speech understanding and audio reply | Gemini Live; default `gemini-2.0-flash-exp` | `GEMINI_API_KEY`, optional `GEMINI_ENDPOINT`, `GEMINI_MODEL_NAME`, `GEMINI_VOICE_NAME` in `backend\.env.example`; read in `backend\src\main.py` |
| SQL generation, SQL intent routing (where used), and spoken-answer text | Azure OpenAI chat deployment; default deployment name `gpt-5-mini` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `CHAT_DEPLOYMENT`, `CHAT_API_VERSION`; configured in `backend\autogen_flow\config.py` and used in `backend\autogen_flow\airline_autogen_flow.py` |
| Policy-query embeddings | Azure OpenAI embedding deployment; default `text-embedding-3-small` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `EMBEDDING_DEPLOYMENT`, `EMBEDDING_API_VERSION`; configured in `backend\src\middleware.py` |

The frontend package lists `@google/genai` and `@google/generative-ai`, but no active frontend source imports either SDK. The browser sends audio to the backend; the backend calls Gemini.

### Environment variables

Set backend values in `backend\.env` (loaded by the backend/SQL config); `backend\.env.example` documents the expected settings. Required service credentials/configuration for the full experience:

- **Gemini:** `GEMINI_API_KEY`. Optional endpoint/model/voice: `GEMINI_ENDPOINT`, `GEMINI_MODEL_NAME`, `GEMINI_VOICE_NAME`.
- **Azure OpenAI:** `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`; deployment/API versions: `CHAT_DEPLOYMENT`, `CHAT_API_VERSION`, `EMBEDDING_DEPLOYMENT`, `EMBEDDING_API_VERSION`.
- **Azure AI Search:** `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KEY`, and `SEARCH_INDEX_NAME` (default `voice-agent-docs`).
- **Azure SQL:** `SQL_SERVER`, `SQL_DATABASE`, `SQL_USERNAME`, `SQL_PASSWORD`, and `SQL_DRIVER` (default `ODBC Driver 18 for SQL Server`).
- **Optional Redis semantic cache/rate limiting/session resume:** `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_SSL`.
- **Optional backend access control:** `BACKEND_API_KEY`. If set, REST requires `X-API-Key` and WebSocket requires `?api_key=...`.
- **Optional booking email:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_TLS`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
- **Frontend/backend connection:** frontend `VITE_BACKEND_URL` (default `http://127.0.0.1:8000`); Vite's port override is `VITE_DEV_PORT`. Backend also reads `CORS_ORIGINS`.
- **Tuning/diagnostics:** `LOG_FILE`, `GEMINI_WS_MAX_SIZE_BYTES`, `REST_RATE_LIMIT_PER_MINUTE`, `WS_CONNECT_RATE_LIMIT_PER_MINUTE`, `GEMINI_CONNECT_TIMEOUT_SECONDS`, `TOOL_TIMEOUT_SECONDS`, `GEMINI_INPUT_TRANSCRIPTION`, `SEND_TOOL_EVENTS_TO_CLIENT`, `FLIGHT_UI_DEBUG`, `MAX_CONCURRENT_VOICE_SESSIONS`, `POLICY_CACHE_TTL_SECONDS`, `REDIS_RECONNECT_INTERVAL_SECONDS`, `POLICY_CACHE_MAX_DISTANCE`, `POLICY_LOW_CONFIDENCE_SCORE`, `SQL_FLOW_REASONING_EFFORT`, and `SQL_FLOW_MAX_ROWS`.

The root `requirements.txt` / `backend\requirements.txt` do not contain every direct import needed by the backend flow (notably OpenAI, SQLAlchemy, and Azure Search packages). The README's backend setup therefore has a separate `pip install` command for several packages beyond `backend\requirements.txt`.

### Database and SQL

- Flight data is queried from **Azure SQL Server**, configured in `backend\autogen_flow\config.py` using a SQLAlchemy `mssql+pyodbc` engine and the configured ODBC driver.
- The application flow targets **`dbo.voice_agent_data`**. It reads schema metadata from `INFORMATION_SCHEMA.COLUMNS`, inspects distinct values/date bounds for prompt context, and executes generated read-only T-SQL.
- `backend\info.db` is present but no active backend source references SQLite or `info.db`.
- `backend\SELECT TOP 100.sql` is a **manual query/reference file**, not imported or executed by application code. It includes a first example querying `dbo.flights` (not the live flow's `dbo.voice_agent_data`) and additional inspection queries for `voice_agent_data`.
- Policy content is in Azure AI Search, optionally cached in Azure Redis; no SQL policy table is configured in the code.

## 4. Dependency map

Statuses mean: **ACTIVE** = part of the application/runtime or setup; **STANDALONE SCRIPT** = manually run independently; **NOT REFERENCED** = not reached by the active app (or generated/runtime data rather than source). Python bytecode cache files are listed because they exist, but are generated artifacts.

### `backend\`

| File | What it does | Imported/used by | Status |
|---|---|---|---|
| `backend\.env` | Local runtime environment settings; values intentionally not reproduced here. | `backend\src\main.py` (`load_dotenv`); `backend\autogen_flow\config.py` loads this path explicitly. | ACTIVE |
| `backend\.env.example` | Credential/configuration template. | Setup instructions in README; not loaded by the app. | NOT REFERENCED |
| `backend\.gitignore` | Git ignore rules for local/generated files. | Git, not application code. | NOT REFERENCED |
| `backend\backend.log` | Backend log file (runtime output). | File handler configured in `backend\src\main.py` (`LOG_FILE`, default `backend.log`). | ACTIVE |
| `backend\info.db` | SQLite database file. | No active source reference found. | NOT REFERENCED |
| `backend\loadtest.js` | k6 WebSocket load-test scenario. | Run independently with k6; not imported by the backend. | STANDALONE SCRIPT |
| `backend\requirements.txt` | Python dependency pins/ranges. | Used by setup/install commands. | ACTIVE |
| `backend\SELECT TOP 100.sql` | Manual data/schema inspection SQL examples. | No active source reference found; run manually in a SQL client. | STANDALONE SCRIPT |
| `backend\src\__init__.py` | Makes `src` a Python package. | Python package imports/`src.main`. | ACTIVE |
| `backend\src\main.py` | FastAPI app, health/tool APIs, Gemini WebSocket proxy, tool orchestration and booking handoff. | Uvicorn entry point; imports middleware and SQL flow. | ACTIVE |
| `backend\src\middleware.py` | Azure OpenAI embeddings, Azure AI Search policy retrieval, optional Redis cache/rate limiting and voice-session semaphore. | Imported/initialized by `backend\src\main.py`. | ACTIVE |
| `backend\src\__pycache__\__init__.cpython-314.pyc` | Generated package bytecode. | Python interpreter cache; no source-level import. | NOT REFERENCED |
| `backend\src\__pycache__\__init__.cpython-312.pyc` | Generated package bytecode. | Python interpreter cache; no source-level import. | NOT REFERENCED |
| `backend\src\__pycache__\voice_engine.cpython-312.pyc` | Generated bytecode for a `voice_engine` module whose source is absent from the current `backend\src\` inventory. | No current source import found. | NOT REFERENCED |
| `backend\src\__pycache__\sql_agent.cpython-312.pyc` | Generated bytecode for a `sql_agent` module whose source is absent from the current `backend\src\` inventory. | No current source import found. | NOT REFERENCED |
| `backend\src\__pycache__\middleware.cpython-314.pyc` | Generated middleware bytecode. | Python interpreter cache; source module is `middleware.py`. | NOT REFERENCED |
| `backend\src\__pycache__\middleware.cpython-312.pyc` | Generated middleware bytecode. | Python interpreter cache; source module is `middleware.py`. | NOT REFERENCED |
| `backend\src\__pycache__\main.cpython-314.pyc` | Generated backend bytecode. | Python interpreter cache; source module is `main.py`. | NOT REFERENCED |
| `backend\src\__pycache__\main.cpython-312.pyc` | Generated backend bytecode. | Python interpreter cache; source module is `main.py`. | NOT REFERENCED |
| `backend\autogen_flow\config.py` | Loads Azure/OpenAI/SQL settings and creates SQLAlchemy engine. | Imported by `backend\autogen_flow\airline_autogen_flow.py`. | ACTIVE |
| `backend\autogen_flow\airline_autogen_flow.py` | LLM-assisted route/SQL generation, guarded SQL execution, answer generation, SQL health and warm-up helpers. | Imported/called by `backend\src\main.py`. | ACTIVE |
| `backend\autogen_flow\__pycache__\config.cpython-312.pyc` | Generated configuration bytecode. | Python interpreter cache; source module is `config.py`. | NOT REFERENCED |
| `backend\autogen_flow\__pycache__\airline_autogen_flow.cpython-312.pyc` | Generated SQL-flow bytecode. | Python interpreter cache; source module is `airline_autogen_flow.py`. | NOT REFERENCED |

### `frontend\src\`

| File | What it does | Imported/used by | Status |
|---|---|---|---|
| `frontend\src\main.jsx` | React/Vite mount; renders `App` and imports global CSS. | Vite HTML entry. | ACTIVE |
| `frontend\src\App.jsx` | App state, status/health check, realtime hook integration, flight filters/sorting, and result rendering. | `frontend\src\main.jsx`. | ACTIVE |
| `frontend\src\api.js` | REST helper for `POST /execute-tool`. It is not called by current app code. | No current source import found. | NOT REFERENCED |
| `frontend\src\constants.js` | Sample flight-query chips. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\index.css` | Global application styles. | `frontend\src\main.jsx`. | ACTIVE |
| `frontend\src\hooks\useRealtimeAgent.js` | Microphone capture, PCM conversion, WebSocket lifecycle/reconnect, Gemini audio playback and tool-result callbacks. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\utils\flights.js` | Airline-code/status helpers plus a legacy result-shaping helper. | `FlightTable.jsx` and the unreferenced `FlightCard.jsx`. | ACTIVE |
| `frontend\src\components\Header.jsx` | Header, call button and agent status. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\Hero.jsx` | Intro/hero content. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\SearchCard.jsx` | Text input, search button and microphone controls. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\Suggestions.jsx` | Renders sample query chips. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\EmptyState.jsx` | Empty/no-call prompt. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\ResultsToolbar.jsx` | Result count, sort and flight filters. | `frontend\src\App.jsx`. | ACTIVE |
| `frontend\src\components\FlightTable.jsx` | Displays flight rows and Book buttons. | Imported and rendered by `frontend\src\App.jsx` for one or multiple dates. | ACTIVE |
| `frontend\src\components\FlightCard.jsx` | Older individual flight-card presentation. | No current source imports it. | NOT REFERENCED |
| `frontend\src\components\FlightTicketCard.jsx` | Ticket/boarding-pass presentation component. | No current source imports it. | NOT REFERENCED |
| `frontend\src\components\FlightTicketCard.css` | Styles for `FlightTicketCard.jsx`. | Imported only by the unreferenced `FlightTicketCard.jsx`. | NOT REFERENCED |

`frontend\src\components\AiCard.jsx` and `frontend\src\components\Processing.jsx` are deleted in the current worktree and are absent from the source inventory. A source search found no remaining imports or references to either name. `FlightTable.jsx` is present and actively imported/rendered in `App.jsx`.

## 5. Risks and incomplete behavior

1. **Configured backend API key blocks the current frontend.** If `BACKEND_API_KEY` is non-empty, `/ws/audio` requires an `api_key` query parameter and `/execute-tool` requires `X-API-Key`. The active WebSocket hook sends neither; the unused `api.js` helper also sends no API-key header. The voice call will be rejected when this optional protection is enabled.
2. **Text search does not submit.** `App.handleTextSubmit` is a no-op. The text field and suggestion chips only update the `query` state; they do not send text to Gemini or `/execute-tool`.
3. **The flight table's Book button has no visible/actionable handoff.** It only sets `bookingHandoff` state, which is not read or rendered. Voice-based booking uses a different tool path.
4. **Health status checks only Gemini for voice configuration.** `App` marks realtime configured from `services.gemini_live`; this does not establish that Azure SQL, Azure OpenAI, or AI Search are available. The UI can enable the call even when later tool execution cannot work.
5. **Tool-result UI metadata is lost.** `_send_client_tool_result` sends only `flight_results` and `count`; it omits `truncated` and `widened`, although the frontend has UI state for both. Also `ResultsToolbar` says “first 100 shown,” while the SQL pipeline defaults to 50 rows and returns at most 25 rows to its answer/result payload.
6. **The manual SQL file mixes table versions.** Its initial query reads `dbo.flights`; the live application uses `dbo.voice_agent_data`. Treat the file as historical/manual guidance, not a reliable representation of the application schema.
7. **The SQL prompt has a fixed date embedded in it.** `airline_autogen_flow.py` contains a “Today is October 5, 2026” / “before 2026-10-05” instruction in addition to a dynamic SQL date expression. That fixed reference will become stale and may conflict with the actual current date.
8. **Dependency installation is split across commands.** `backend\requirements.txt` alone does not declare several direct imports used by the app/SQL flow; the README's extra pip-install command is needed. A fresh setup that installs only the requirements file can fail imports or leave the SQL flow unavailable.
9. **Several source/artifact files are disconnected.** `frontend\src\api.js`, `FlightCard.jsx`, and `FlightTicketCard.jsx` are not on the active UI path; `backend\info.db` is not the configured database. The source tree also contains stale bytecode for missing `voice_engine.py` and `sql_agent.py`.
10. **The Vite `/api` proxy is not used by current requests.** The app calls the absolute backend URL and the WebSocket URL directly. This works only if the backend is reachable from the browser and its CORS configuration permits the frontend origin; the proxy configuration does not currently route those requests.
11. **Large commented legacy implementation in `backend\src\main.py`.** More than 700 leading lines are commented-out old code, making it easy to mistake inactive behavior for the live implementation.
12. **Local secrets/config need careful handling.** `backend\.env` exists in the working tree; do not commit it. The booking recipient is hard-coded in the active backend source.
