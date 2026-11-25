# D:\airline-voice-agent\docs\build_docs.py
from pathlib import Path
import re


import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
DOCS = Path(__file__).resolve().parent


ENV_ROWS = [
    ("Azure OpenAI / LLM", "AZURE_OPENAI_ENDPOINT", "backend\\autogen_flow\\config.py; backend\\src\\middleware.py", "Azure OpenAI resource endpoint for chat and embeddings.", "Required for SQL/LLM and policy embedding features.", "No code fallback; unset if missing."),
    ("Azure OpenAI / LLM", "AZURE_OPENAI_KEY", "backend\\autogen_flow\\config.py; backend\\src\\middleware.py", "Azure OpenAI credential. Document with `<placeholder>` only.", "Required for SQL/LLM and policy embedding features.", "No code fallback; unset if missing."),
    ("Azure OpenAI / LLM", "CHAT_DEPLOYMENT", "backend\\autogen_flow\\config.py", "Azure OpenAI chat deployment for SQL generation and answer text.", "Required for SQL/LLM features.", "`gpt-5-mini`"),
    ("Azure OpenAI / LLM", "CHAT_API_VERSION", "backend\\autogen_flow\\config.py", "Chat API version.", "Optional override; required deployment compatibility.", "`2024-12-01-preview`"),
    ("Azure OpenAI / LLM", "EMBEDDING_DEPLOYMENT", "backend\\autogen_flow\\config.py; backend\\src\\middleware.py", "Embedding deployment for policy retrieval.", "Required for policy search.", "`text-embedding-3-small`"),
    ("Azure OpenAI / LLM", "EMBEDDING_API_VERSION", "backend\\src\\middleware.py", "Embedding API version.", "Optional override; required for embedding initialization.", "`2024-02-01`"),
    ("Azure AI Search / RAG", "AZURE_SEARCH_ENDPOINT", "backend\\autogen_flow\\config.py; backend\\src\\middleware.py", "Search service endpoint for policy retrieval.", "Required for policy search.", "No code fallback; search client is not initialized if missing."),
    ("Azure AI Search / RAG", "AZURE_SEARCH_KEY", "backend\\autogen_flow\\config.py; backend\\src\\middleware.py", "Search credential. Document with `<placeholder>` only.", "Required for policy search.", "No code fallback; search client is not initialized if missing."),
    ("Azure AI Search / RAG", "SEARCH_INDEX_NAME", "backend\\src\\middleware.py", "Name of the policy vector-search index.", "Optional override; required index must exist.", "`voice-agent-docs`"),
    ("Azure SQL / database", "SQL_SERVER", "backend\\autogen_flow\\config.py", "SQL Server host.", "Required for flight data.", "No code fallback; unset if missing."),
    ("Azure SQL / database", "SQL_DATABASE", "backend\\autogen_flow\\config.py", "Database name.", "Required for flight data.", "No code fallback; unset if missing."),
    ("Azure SQL / database", "SQL_USERNAME", "backend\\autogen_flow\\config.py", "SQL login name.", "Required by the configured SQL connection string.", "No code fallback; unset if missing."),
    ("Azure SQL / database", "SQL_PASSWORD", "backend\\autogen_flow\\config.py", "SQL login password. Document with `<placeholder>` only.", "Required by the configured SQL connection string.", "No code fallback; unset if missing."),
    ("Azure SQL / database", "SQL_DRIVER", "backend\\autogen_flow\\config.py", "ODBC driver name.", "Optional override; installed ODBC driver is required.", "`ODBC Driver 18 for SQL Server`"),
    ("Gemini Live / voice", "GEMINI_ENDPOINT", "backend\\src\\main.py", "Gemini Live WebSocket endpoint.", "Optional override; a reachable Gemini Live endpoint is required.", "`wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent`"),
    ("Gemini Live / voice", "GEMINI_MODEL_NAME", "backend\\src\\main.py", "Gemini Live model name.", "Optional override; Gemini Live access is required.", "`gemini-2.0-flash-exp`"),
    ("Gemini Live / voice", "GEMINI_API_KEY", "backend\\src\\main.py", "Gemini API credential. Document with `<placeholder>` only.", "Required for the voice WebSocket; without it the server rejects the session.", "No code fallback; unset means not configured."),
    ("Gemini Live / voice", "GEMINI_VOICE_NAME", "backend\\src\\main.py", "Gemini generated-audio voice.", "Optional override.", "`Puck`"),
    ("Redis / cache", "REDIS_HOST", "backend\\src\\middleware.py", "Redis host for policy cache, rate limit, and optional resume storage.", "Optional service; policy search can call AI Search without a cache.", "No code fallback; unset disables Redis connection."),
    ("Redis / cache", "REDIS_PORT", "backend\\src\\middleware.py", "Redis port.", "Optional override.", "`10000`"),
    ("Redis / cache", "REDIS_PASSWORD", "backend\\src\\middleware.py", "Redis credential. Document with `<placeholder>` only.", "Required if the configured Redis service requires a password.", "No code fallback."),
    ("Redis / cache", "REDIS_SSL", "backend\\src\\middleware.py", "Enable TLS for Redis.", "Optional override.", "`true`"),
    ("Backend security", "BACKEND_API_KEY", "backend\\src\\main.py", "Optional shared key for REST and WebSocket requests.", "Optional; if set, clients must send the key.", "Unset or empty disables API-key checking."),
    ("Email / handoff", "SMTP_HOST", "backend\\src\\main.py", "SMTP server; its presence enables email dispatch.", "Optional; booking handoff only logs if absent.", "Unset means no SMTP send."),
    ("Email / handoff", "SMTP_PORT", "backend\\src\\main.py", "SMTP server port.", "Optional override.", "`587`"),
    ("Email / handoff", "SMTP_TLS", "backend\\src\\main.py", "Enable STARTTLS.", "Optional override.", "`true`"),
    ("Email / handoff", "SMTP_USER", "backend\\src\\main.py", "SMTP username.", "Optional; used when provided.", "Unset means no SMTP login."),
    ("Email / handoff", "SMTP_PASS", "backend\\src\\main.py", "SMTP password. Document with `<placeholder>` only.", "Required only when SMTP login is enabled by `SMTP_USER`.", "No code fallback."),
    ("Email / handoff", "SMTP_FROM", "backend\\src\\main.py", "Sender address.", "Optional override.", "`voice-agent@airline.com` in code; example file uses a placeholder."),
    ("Backend runtime / network", "CORS_ORIGINS", "backend\\src\\main.py", "Comma-separated allowed browser origins.", "Optional override.", "`http://localhost:5173,http://localhost:3000`"),
    ("Backend runtime / logging", "LOG_FILE", "backend\\src\\main.py", "File path for the backend log handler.", "Optional override.", "`backend.log`"),
    ("Backend runtime / limits", "GEMINI_WS_MAX_SIZE_BYTES", "backend\\src\\main.py", "Maximum upstream WebSocket message size.", "Optional override.", "`2097152` (2 MiB)"),
    ("Backend runtime / limits", "REST_RATE_LIMIT_PER_MINUTE", "backend\\src\\main.py", "REST requests allowed per client IP in a 60-second window when Redis rate limiting is available.", "Optional override.", "`60`"),
    ("Backend runtime / limits", "WS_CONNECT_RATE_LIMIT_PER_MINUTE", "backend\\src\\main.py", "WebSocket connects allowed per client IP in a 60-second window when Redis rate limiting is available.", "Optional override.", "`10`"),
    ("Backend runtime / timeouts", "GEMINI_CONNECT_TIMEOUT_SECONDS", "backend\\src\\main.py", "Timeout for opening the upstream Gemini connection.", "Optional override.", "`8`"),
    ("Backend runtime / timeouts", "TOOL_TIMEOUT_SECONDS", "backend\\src\\main.py", "Timeout applied to one Gemini tool call.", "Optional override.", "`20.0`"),
    ("Backend runtime / voice", "GEMINI_INPUT_TRANSCRIPTION", "backend\\src\\main.py", "Enable Gemini input-audio transcription events.", "Optional override.", "`true`"),
    ("Backend runtime / voice", "SEND_TOOL_EVENTS_TO_CLIENT", "backend\\src\\main.py", "Send full tool result objects to the browser instead of only non-empty flight rows.", "Optional override.", "`false`"),
    ("Backend runtime / diagnostics", "FLIGHT_UI_DEBUG", "backend\\src\\main.py", "Log whether flight table tool results are sent or skipped.", "Optional override.", "`false`"),
    ("Backend runtime / capacity", "MAX_CONCURRENT_VOICE_SESSIONS", "backend\\src\\middleware.py", "Semaphore capacity for concurrent voice sessions.", "Optional override.", "`200`"),
    ("Policy cache / Redis", "POLICY_CACHE_TTL_SECONDS", "backend\\src\\middleware.py", "Lifetime for cached policy responses.", "Optional override.", "`600`"),
    ("Policy cache / Redis", "REDIS_RECONNECT_INTERVAL_SECONDS", "backend\\src\\middleware.py", "Delay between Redis reconnect checks.", "Optional override.", "`30`"),
    ("Policy cache / Redis", "POLICY_CACHE_MAX_DISTANCE", "backend\\src\\middleware.py", "Maximum Redis vector distance accepted as a semantic-cache hit.", "Optional override.", "`0.15`"),
    ("Policy cache / search", "POLICY_LOW_CONFIDENCE_SCORE", "backend\\src\\middleware.py", "AI Search score below which a policy response is marked low-confidence.", "Optional override.", "`0.015`"),
    ("SQL flow / LLM", "SQL_FLOW_REASONING_EFFORT", "backend\\autogen_flow\\airline_autogen_flow.py", "Reasoning-effort option sent with chat completion; retried without it after `BadRequestError`.", "Optional override.", "`minimal`"),
    ("SQL flow / database", "SQL_FLOW_MAX_ROWS", "backend\\autogen_flow\\airline_autogen_flow.py", "TOP limit requested in generated SQL.", "Optional override.", "`50`"),
    ("Frontend / Vite", "VITE_BACKEND_URL", "frontend\\src\\App.jsx; frontend\\src\\api.js; frontend\\src\\hooks\\useRealtimeAgent.js; frontend\\vite.config.js", "Backend HTTP/WebSocket base URL and Vite proxy target.", "Optional override.", "`http://127.0.0.1:8000`"),
    ("Frontend / Vite", "VITE_DEV_PORT", "frontend\\vite.config.js", "Vite development server port.", "Optional override.", "`5173`"),
]


def rich_text(paragraph, text, base_size=9):
    for token in re.split(r"(`[^`]+`)", str(text)):
        if not token:
            continue
        is_code = token.startswith("`") and token.endswith("`")
        value = token[1:-1] if is_code else token
        run = paragraph.add_run(value)
        run.font.name = "Consolas" if is_code else "Calibri"
        run.font.size = Pt(base_size if not is_code else base_size - 0.2)
        if is_code:
            run.font.color.rgb = RGBColor(35, 75, 110)
    return paragraph


def add_para(doc, text="", style=None):
    para = doc.add_paragraph(style=style)
    rich_text(para, text)
    return para


def add_code(doc, text):
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Inches(0.18)
    para.paragraph_format.space_before = Pt(2)
    para.paragraph_format.space_after = Pt(5)
    para.paragraph_format.keep_together = True
    run = para.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(35, 75, 110)
    return para


def add_bullets(doc, items):
    for item in items:
        add_para(doc, item, "List Bullet")


def add_numbered(doc, items):
    for index, item in enumerate(items, 1):
        add_para(doc, f"{index}. {item}")


def set_cell_text(cell, text, header=False):
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    para = cell.paragraphs[0]
    para.paragraph_format.space_after = Pt(0)
    rich_text(para, text, 7.4 if not header else 7.7)
    if header:
        for run in para.runs:
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for i, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[i], header, True)
        shading = table.rows[0].cells[i]._tc.get_or_add_tcPr()
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        fill = OxmlElement("w:shd")
        fill.set(qn("w:fill"), "24476A")
        shading.append(fill)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            set_cell_text(cells[i], value)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def setup_doc(doc, title):
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11)
    section.page_height = Inches(8.5)
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(9)
    normal.paragraph_format.space_after = Pt(5)
    for style_name, size, color in [
        ("Title", 24, "17365D"),
        ("Heading 1", 16, "17365D"),
        ("Heading 2", 12, "24476A"),
        ("Heading 3", 10, "24476A"),
    ]:
        style = doc.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
    doc.core_properties.title = title
    doc.core_properties.subject = "Repository-grounded project documentation"


def add_heading(doc, text, level):
    doc.add_heading(text, level=level)


def env_table(doc):
    add_table(
        doc,
        ["Service group", "Variable", "File(s) reading it", "Purpose", "Required / optional", "Code default"],
        ENV_ROWS,
    )
    add_para(
        doc,
        "Secret values are not copied from local environment files. Use `<placeholder>` in templates. "
        "Required means required for that feature, not necessarily for starting the FastAPI process. "
        "The table includes variables read by source and variables documented in `backend\\.env.example`; "
        "`VITE_DEV_PORT` is read by Vite but is not in the example file. The local `.env` also has "
        "`CHAT_MODEL_NAME` and `EMBEDDING_MODEL_NAME` entries, but active code reads `CHAT_DEPLOYMENT` "
        "and `EMBEDDING_DEPLOYMENT` instead.",
    )


def make_architecture(path):
    fig, ax = plt.subplots(figsize=(12, 4.1))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4.4)
    ax.axis("off")
    boxes = [
        (0.25, 1.55, 1.35, 1.15, "Caller\nmic / speaker"),
        (2.0, 1.55, 1.45, 1.15, "React web client\nPCM capture / play"),
        (3.9, 1.55, 1.55, 1.15, "FastAPI\nWebSocket proxy"),
        (6.0, 1.55, 1.75, 1.15, "Gemini Live\nSTT + LLM"),
        (8.35, 1.55, 1.65, 1.15, "Backend tools\nSQL / policy RAG"),
        (10.45, 1.55, 1.3, 1.15, "Gemini Live\nTTS audio"),
    ]
    for x, y, w, h, label in boxes:
        ax.text(
            x + w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#EAF1F8", edgecolor="#24476A", linewidth=1.5),
        )
    arrows = [
        (1.62, 2.12, 1.98, 2.12, "audio"),
        (3.48, 2.12, 3.88, 2.12, "WebSocket"),
        (5.48, 2.12, 5.98, 2.12, "audio / tool calls"),
        (7.78, 2.12, 8.33, 2.12, "function call"),
        (10.05, 2.12, 10.43, 2.12, "tool result"),
    ]
    for x1, y1, x2, y2, label in arrows:
        ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="->", color="#24476A", lw=1.5))
        ax.text((x1 + x2) / 2, y1 + 0.22, label, ha="center", va="bottom", fontsize=7)
    ax.annotate(
        "generated audio returns through FastAPI and the web client to the caller",
        xy=(2.7, 1.46),
        xytext=(10.9, 1.46),
        ha="center",
        va="top",
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="#9B5B20", lw=1.4, connectionstyle="arc3,rad=-0.16"),
        color="#744315",
    )
    ax.text(
        6,
        0.35,
        "No telephony service is implemented in this repository. Gemini Live performs the speech and language-model steps.",
        ha="center",
        va="center",
        fontsize=8,
        color="#444444",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def details_document():
    doc = Document()
    setup_doc(doc, "Airline Voice Agent - Project Details")
    doc.add_heading("Airline Voice Agent - Project Details", 0)
    add_para(doc, "Repository-grounded summary. Local secret values are intentionally excluded.")

    add_heading(doc, "1. Project Details", 1)
    add_heading(doc, "1.1 Project Name", 2)
    add_para(doc, "Airline Voice Agent (Flight AI), as named in `README.md`.")
    add_heading(doc, "1.2 Project Owner / Team", 2)
    add_para(doc, "To be filled. The repository does not identify a project owner or team.")
    add_heading(doc, "1.3 Problem Statement", 2)
    add_para(doc, "Passengers may need flight schedules, fares, status, or airline-policy answers while interacting with a travel service. This repository does not include user research or measured evidence about the size of that problem.")
    add_para(doc, "A text-only search can require the user to type a structured query. This project instead provides a browser microphone flow that sends audio to a real-time voice model and declares tools for flight and policy lookups.")
    add_para(doc, "The current code returns flight rows from Azure SQL and policy passages from Azure AI Search. It can speak a response and display flight rows. It does not complete a booking; voice booking requests are handed to an email routine when SMTP is configured.")
    add_heading(doc, "1.4 Project Status", 2)
    add_para(doc, "Implementation is present in the repository. The active UI, FastAPI app, Gemini Live WebSocket proxy, Azure SQL flow, and policy retrieval code can be identified in source. The repository does not prove that the configured cloud services are connected, that a demo has passed, or that anything is deployed. No test suite or deployment scripts were found. Text submission and the UI Book button are incomplete.")

    add_heading(doc, "2. Code Repository", 1)
    add_heading(doc, "2.1 GitHub Repository Link", 2)
    add_para(doc, "Git remote `origin` reports:")
    add_code(doc, "https://github.com/Bhargaw1/airline-voice-agent")
    add_heading(doc, "2.2 Main Code Locations", 2)
    add_table(doc, ["Area", "File / folder", "Role"], [
        ("Backend API and voice proxy", "`backend\\src\\main.py`", "FastAPI endpoints, Gemini WebSocket relay, tool dispatch, audio setup and booking handoff."),
        ("Policy retrieval", "`backend\\src\\middleware.py`", "Azure OpenAI embeddings, Azure AI Search, optional Redis cache and rate limiter."),
        ("Flight SQL flow", "`backend\\autogen_flow\\`", "SQLAlchemy connection config and LLM-assisted T-SQL generation/execution."),
        ("Frontend", "`frontend\\src\\`", "React UI, microphone audio capture/playback, flight result table and filters."),
        ("Frontend toolchain", "`frontend\\package.json`, `frontend\\vite.config.js`", "Vite scripts, dependencies, dev port and proxy."),
        ("Configuration template", "`backend\\.env.example`", "Placeholder values and service/runtime settings."),
        ("Load test", "`backend\\loadtest.js`", "Standalone k6 WebSocket load test, not part of app startup."),
        ("Manual SQL examples", "`backend\\SELECT TOP 100.sql`", "Manual SQL queries; app code does not read this file."),
    ])
    add_heading(doc, "2.3 Environment Variables", 2)
    env_table(doc)
    add_heading(doc, "2.4 Run Commands for Each Service", 2)
    add_para(doc, "Run from the repository root in Windows PowerShell. The backend and frontend should run in separate terminals. The repository README lists Python 3.10+ and Node.js 18+, but the locked Vite version requires a newer Node version; see known issues.")
    add_para(doc, "Backend setup and start:")
    add_code(doc, "py -3.12 -m venv .\\venv")
    add_code(doc, ".\\venv\\Scripts\\Activate.ps1")
    add_code(doc, "python -m pip install -r .\\backend\\requirements.txt")
    add_code(doc, "python -m pip install sqlalchemy openai azure-search-documents azure-core")
    add_code(doc, "Copy-Item .\\backend\\.env.example .\\backend\\.env")
    add_code(doc, "Set-Location .\\backend")
    add_code(doc, "python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload")
    add_para(doc, "Fill in required values in `backend\\.env` before expecting cloud-backed features to work. Use the actual installed ODBC Driver 18 for SQL Server.")
    add_para(doc, "Frontend setup and start, in a second PowerShell terminal from the repository root:")
    add_code(doc, "Set-Location .\\frontend")
    add_code(doc, "npm install")
    add_code(doc, "npm run dev")
    add_para(doc, "Open the Vite URL, normally `http://localhost:5173`. Vite 8's locked engine range is Node `^20.19.0 || >=22.12.0`.")
    add_heading(doc, "2.5 Ports and CORS", 2)
    add_table(doc, ["Service", "Port / address", "Source and behavior"], [
        ("FastAPI / Uvicorn", "`8000`, host `0.0.0.0`", "README command and `backend\\src\\main.py` module entry point. Frontend default backend base is `http://127.0.0.1:8000`."),
        ("Vite dev server", "`5173` by default", "`frontend\\vite.config.js`; override with `VITE_DEV_PORT`."),
        ("Additional CORS origin", "`http://localhost:3000`", "Default included with port 5173 from `CORS_ORIGINS` in `backend\\src\\main.py`."),
        ("Redis", "`10000` by default", "`REDIS_PORT` in `backend\\src\\middleware.py`; actual service configuration may differ."),
        ("SMTP", "`587` by default", "`SMTP_PORT` in `backend\\src\\main.py`; only used for handoff email."),
        ("Vite proxy", "`/api` to backend target", "Configured in `frontend\\vite.config.js`; current frontend calls absolute backend URLs and does not use this proxy path."),
    ])
    add_para(doc, "The repository uses loopback addresses for local defaults. No VM-specific IP address was found. `0.0.0.0` is a bind address, not the browser-facing application URL.")

    add_heading(doc, "3. VM Deployment", 1)
    add_heading(doc, "3.1 VM Deployment Link", 2)
    add_para(doc, "To be filled. No VM URL, deployment manifest, or VM deployment script was found.")
    add_heading(doc, "3.2 Credentials", 2)
    add_table(doc, ["Credential", "Value"], [
        ("Username", "To be filled"),
        ("Password", "To be filled"),
    ])
    add_para(doc, "No credential values from local `.env` files are included in this document.")
    add_heading(doc, "3.3 Application URL / Port", 2)
    add_para(doc, "Deployed application URL: To be filled. Local defaults are frontend `http://localhost:5173` and backend `http://127.0.0.1:8000`; the backend WebSocket route is `ws://127.0.0.1:8000/ws/audio`.")

    add_heading(doc, "4. Demo Readiness", 1)
    add_heading(doc, "4.1 Application Working Status", 2)
    add_para(doc, "The code contains a browser voice path and cloud service integrations. Actual operation depends on valid Gemini, Azure OpenAI, Azure SQL, and AI Search configuration. This review did not make live service calls or establish a running demo, so connected status is not verified.")
    add_heading(doc, "4.2 Major Features Working", 2)
    add_para(doc, "A user starts a session from the React page, grants microphone permission, and speaks. `useRealtimeAgent` encodes microphone frames and sends them over `WS /ws/audio`. FastAPI forwards audio to Gemini Live. Gemini can call flight-search/status tools, which execute generated read-only SQL against `dbo.voice_agent_data`; policy questions use embeddings and Azure AI Search. Gemini returns audio for playback. Non-empty flight results are also sent to the UI table. This describes the implemented code path, not a verified live demo.")
    add_heading(doc, "4.3 Required Services Connected", 2)
    add_table(doc, ["Service", "Role", "Code dependency", "Connection verified here?"], [
        ("Google Gemini Live", "Speech input, tool selection and generated audio.", "`backend\\src\\main.py`", "No; credentials and network were not tested."),
        ("Azure OpenAI", "SQL generation/answer text and policy query embeddings.", "`backend\\autogen_flow\\airline_autogen_flow.py`; `backend\\src\\middleware.py`", "No; credentials and deployments were not tested."),
        ("Azure SQL", "Flight schedule/status data in `dbo.voice_agent_data`.", "`backend\\autogen_flow\\config.py`", "No; host, database and ODBC connectivity were not tested."),
        ("Azure AI Search", "Policy vector retrieval.", "`backend\\src\\middleware.py`", "No; endpoint/index were not tested."),
        ("Azure Redis", "Optional semantic cache, rate limiting, and resume-handle storage.", "`backend\\src\\middleware.py`; `backend\\src\\main.py`", "No; optional and not tested."),
        ("SMTP", "Optional email on voice booking handoff.", "`backend\\src\\main.py`", "No; optional and not tested."),
        ("Telephony / phone provider", "Not implemented in repository.", "No telephony SDK or endpoint found.", "Not applicable."),
    ])
    add_heading(doc, "4.4 Demo Data / Sample Inputs", 2)
    add_table(doc, ["Input", "Location", "Use"], [
        ("Sample suggestion text", "`frontend\\src\\constants.js`", "Six example flight prompts in the UI; typed submission currently does not dispatch them."),
        ("Load-test text request", "`backend\\loadtest.js`", "A standalone k6 scenario sends a sample flight query after WebSocket setup."),
        ("Manual SQL queries", "`backend\\SELECT TOP 100.sql`", "Reference queries for manual execution; not used by the app."),
        ("POC SQL/query examples", "`AICOE_POC_Package\\airline-voice-agent\\Input\\`", "Older schema-probe SQL and sample query constants; not imported by the active app."),
        ("Flight dataset", "Azure SQL table `dbo.voice_agent_data`", "External data source, not a local sample file. Dataset source is To be filled."),
        ("Policy documents", "Configured external Azure AI Search index", "No local indexed documents or ingestion pipeline found. Source is To be filled."),
    ])
    add_heading(doc, "4.5 Any known issues or dependencies", 2)
    add_table(doc, ["Issue / dependency", "Evidence and effect"], [
        ("No login page", "`README.md` says there is no login page. API-key checking is optional backend protection, not an interactive login."),
        ("Typed query does not submit", "`frontend\\src\\App.jsx`, `handleTextSubmit`: no-op; suggestions only populate state."),
        ("Book button has no completed action", "`App.handleSelectFlight` only stores `bookingHandoff`; that state is not rendered or sent to the backend."),
        ("API key mismatch", "`BACKEND_API_KEY` requires a query key for WebSocket and header for REST, but current frontend hook/helper sends neither."),
        ("Data result metadata", "The WebSocket result helper sends `flight_results` and `count`, not `truncated`/`widened`; toolbar says first 100 while SQL pipeline caps at 50 and returns at most 25 rows."),
        ("Node version guidance", "`README.md` says Node 18+, while locked Vite 8 declares Node `^20.19.0 || >=22.12.0` in `frontend\\package-lock.json`."),
        ("Undeclared Python imports", "`backend\\requirements.txt` omits SQLAlchemy, OpenAI, Azure Search Documents and Azure Core used in source. README has a separate install command for some dependencies."),
        ("Stale SQL prompt date", "`backend\\autogen_flow\\airline_autogen_flow.py`, `generate_sql`: prompt has a fixed October 5, 2026 date alongside a dynamic date expression."),
        ("Redis is optional and fail-open for rate limiting", "`AirlineMiddleware.check_rate_limit` returns allowed when Redis is disabled or an exception occurs."),
        ("Booking email destination is fixed", "`backend\\src\\main.py`, `send_booking_email_async`: the recipient is embedded in the function and has no environment-variable override."),
        ("No deployment or automated test suite", "No Dockerfile, deployment script, VM address, or test files were found in the repository inventory."),
        ("Unused/legacy UI code", "`frontend\\src\\api.js`, `FlightCard.jsx`, and `FlightTicketCard.jsx` are not imported by active app code. `backend\\src\\main.py` also has a large commented legacy implementation."),
    ])
    path = DOCS / "Details_Document.docx"
    doc.save(path)
    return path


def technical_document():
    doc = Document()
    setup_doc(doc, "Airline Voice Agent – Technical Documentation")
    doc.add_heading("Airline Voice Agent – Technical Documentation", 0)

    add_heading(doc, "1. Project Documentation", 1)
    add_heading(doc, "1.a Problem Statement", 2)
    add_para(doc, "This code is intended for airline passengers who want flight schedules, fares, flight status, or policy information through a spoken interface. The repository does not contain user research or data measuring this need.")
    add_para(doc, "The UI provides a microphone-driven conversation instead of requiring a fully structured text query. The current text field is not connected to a submission flow, so voice is the only implemented way to ask a new question from the web UI.")
    add_para(doc, "For flight questions, the app queries an external SQL table. For policy questions, it retrieves passages from an external search index. The app can speak a response and render flight rows; it does not issue a ticket or process a booking.")

    add_heading(doc, "1.b Architecture", 2)
    add_para(doc, "Layer overview:")
    add_table(doc, ["Layer", "Responsibility"], [
        ("Browser UI", "React page, microphone permissions, PCM audio framing, audio playback, flight table and client-side filtering."),
        ("Web API / proxy", "FastAPI HTTP health/tool routes and WebSocket relay between browser and Gemini Live."),
        ("Voice model", "Gemini Live handles incoming audio understanding, tool selection and generated audio."),
        ("Tool orchestration", "Backend validates tool arguments, applies timeouts and dispatches flight/status/policy/booking tools."),
        ("Structured data", "Azure SQL lookup through SQLAlchemy and ODBC."),
        ("Policy retrieval", "Azure OpenAI embeddings, Azure AI Search vector retrieval, optional Redis semantic cache."),
        ("Optional notification", "SMTP email on a voice booking-handoff tool call."),
    ])
    add_para(doc, "Components:")
    add_table(doc, ["Component", "Role"], [
        ("`frontend\\src\\App.jsx`", "Owns UI state and displays result table/filter controls."),
        ("`frontend\\src\\hooks\\useRealtimeAgent.js`", "Captures microphone audio, manages WebSocket, decodes and plays audio."),
        ("`backend\\src\\main.py`", "FastAPI app, Gemini proxy, tool definitions and dispatch."),
        ("`backend\\autogen_flow\\airline_autogen_flow.py`", "Azure OpenAI-driven SQL generation, guarded database query and spoken text answer."),
        ("`backend\\src\\middleware.py`", "Embedding, policy search, Redis and rate limit operations."),
        ("`backend\\autogen_flow\\config.py`", "SQLAlchemy engine and Azure service configuration."),
    ])
    diagram = DOCS / "architecture.png"
    make_architecture(diagram)
    doc.add_picture(str(diagram), width=Inches(9.4))
    add_para(doc, "Architecture diagram source: `docs\\build_docs.py`. Telephony is not present in the code; the session starts in a browser.")

    add_heading(doc, "1.c End-to-End Flow", 2)
    add_numbered(doc, [
        "The React page mounts in `frontend\\src\\main.jsx`. `App` calls `GET /health` and enables voice only when the response says `services.gemini_live` is configured.",
        "The user starts a call using `Header` or the microphone button in `SearchCard`. `App` delegates to `useRealtimeAgent.handleMicClick`.",
        "`startSession` requests microphone permission, creates an AudioWorklet processor, and buffers approximately 20 ms frames. Float samples become signed 16-bit PCM and base64.",
        "The browser opens `WS /ws/audio`. The FastAPI route checks optional key/rate/capacity settings and connects to Gemini Live.",
        "FastAPI sends `build_setup_message`, containing the model, system instructions, audio output configuration and function declarations. Gemini sends setup completion; the backend triggers an initial greeting.",
        "Client audio messages are relayed to Gemini. Gemini may return transcription events, audio chunks, session updates or function calls.",
        "For a tool call, `relay_gemini_to_client` calls `_run_tool_with_timeout` and `execute_tool_call`. Flight search/status uses `run_sql_pipeline`; policy search uses the Azure OpenAI embedding, optional Redis lookup and Azure AI Search.",
        "The backend returns tool results to Gemini and sends non-empty flight rows to the browser. Gemini generates speech and the browser plays returned audio.",
        "`useRealtimeAgent` invokes `App.handleFlightResults` when flight rows arrive. `App` applies client-side filters and renders `FlightTable` and `ResultsToolbar`.",
        "The user stops the call or the socket closes. The hook closes audio resources; backend relay tasks end and release the voice-session semaphore. Resume behavior is described in section 2.d.",
    ])

    add_heading(doc, "1.d UI Features / Tabs", 2)
    add_table(doc, ["Area", "Purpose"], [
        ("Single React page", "One screen; no routing or tab system was found."),
        ("Header / call control", "Displays status and starts or stops the agent call."),
        ("Hero", "Static title and short prompt."),
        ("Search card", "Text field, search button, microphone button, listening panel and Stop button. Text submit is currently a no-op."),
        ("Suggestion chips", "Fill the query text field with a sample phrase."),
        ("Empty state", "Prompt shown when there is no active call and no flight data."),
        ("Results toolbar", "Displays counts and offers sort, price, time, airline and status filters."),
        ("Flight table", "Shows rows, route/timing/fare/status and Book buttons. The Book button does not complete a handoff."),
        ("Login page", "Not present. README states the POC has no login page."),
    ])

    add_heading(doc, "1.e KPIs, Metrics and Detailed Analysis", 2)
    add_para(doc, "The application is not an analytics system. It does not calculate intent accuracy, total call duration, completed-turn counts, user satisfaction, or production success rates. It does expose health status, query/result information, timing logs, and a standalone k6 test. Each formula and threshold below is taken from source.")
    add_table(doc, ["Metric / rule", "Definition / calculation", "Source file and function", "How to interpret"], [
        ("`sql_pipeline` duration", "Elapsed `perf_counter()` time from pipeline entry to completion, rounded to 2 decimal seconds. Returned in `timings.sql_pipeline` on success and error paths.", "`backend\\autogen_flow\\airline_autogen_flow.py`, `run_sql_pipeline`.", "A per-query diagnostic; not an aggregate dashboard metric."),
        ("Tool execution duration", "Elapsed `perf_counter()` time from `execute_tool_call` entry to exit, multiplied by 1000 and rounded to whole ms.", "`backend\\src\\main.py`, `execute_tool_call`.", "Logged per tool call."),
        ("SQL query duration limit", "Database future wait is capped at 7 seconds; timeout returns an error.", "`backend\\autogen_flow\\airline_autogen_flow.py`, `execute_query`.", "A query over the limit is treated as timed out."),
        ("SQL row cap", "Generated SQL prompt requests `TOP SQL_FLOW_MAX_ROWS`, default 50. Pipeline returns `rows[:25]` to its response.", "`airline_autogen_flow.py`, `MAX_ROWS`, `generate_sql`, `run_sql_pipeline`.", "A row limit, not a latency or quality score."),
        ("Schema context cache TTL", "Reuse cached schema text while `time.time() - cached_at < 600` seconds.", "`airline_autogen_flow.py`, `SCHEMA_TTL`, `get_schema_context`.", "Reduces repeated schema inspection; process-local."),
        ("Health status values", "Health response lists service values such as connected/disconnected or configured/not_configured. Overall `status` is returned as `healthy` by the endpoint.", "`backend\\src\\main.py`, `health_check`; middleware health methods.", "A point-in-time check; `healthy` does not mean every service is connected."),
        ("REST rate limit", "At most 60 requests per client IP per 60-second window by default, using Redis counter/expiry.", "`backend\\src\\main.py`, `enforce_rest_rate_limit`; `backend\\src\\middleware.py`, `check_rate_limit`.", "Not enforced when middleware/Redis is unavailable; Redis errors fail open."),
        ("WebSocket connect rate limit", "At most 10 connects per client IP per 60-second window by default, using the same Redis counter mechanism.", "`backend\\src\\main.py`, `websocket_audio`; `middleware.py`, `check_rate_limit`.", "Close code 4008 when enforced and exceeded."),
        ("Concurrent voice-session cap", "An `asyncio.Semaphore` is initialized with `MAX_CONCURRENT_VOICE_SESSIONS` (default 200). Acquire waits up to 0.1 seconds; no permit returns close 1013.", "`backend\\src\\middleware.py`, `AirlineMiddleware.__init__`; `backend\\src\\main.py`, `websocket_audio`.", "Admission cap, not observed concurrency telemetry."),
        ("Redis cached ping age", "Reuse previous Redis health result for up to 5 seconds before issuing another ping.", "`backend\\src\\middleware.py`, `is_redis_healthy`.", "Health-check throttling."),
        ("Redis connection socket timeouts", "Redis connection and socket timeouts are each configured as 0.5 seconds.", "`backend\\src\\middleware.py`, `_connect_redis`.", "Connection configuration, not measured performance."),
        ("Policy cache TTL", "A successful high-confidence response stored in Redis expires after 600 seconds by default.", "`backend\\src\\middleware.py`, `search_policy`.", "Limits age of semantic cache entries."),
        ("Policy cache hit cutoff", "Use nearest Redis vector result only when its distance is `<= 0.15` and category matches.", "`backend\\src\\middleware.py`, `search_policy`.", "Lower distance is treated as a close semantic match."),
        ("Policy low-confidence cutoff", "Mark result low-confidence when no search results exist or top AI Search score is `< 0.015`.", "`backend\\src\\middleware.py`, `search_policy`.", "Low confidence triggers a cautious voice answer."),
        ("Policy result limit", "Requested number is clamped between 1 and 10; default limit is 3.", "`backend\\src\\middleware.py`, `search_policy`.", "Caps passages returned to the tool."),
        ("Input transcription history cap", "The per-session history list retains the latest 10 transcription entries; current utterance string retains the last 2,000 characters.", "`backend\\src\\main.py`, `relay_gemini_to_client`.", "Bounds in-memory conversation context; not an analytics turn count."),
        ("Tool argument limits", "String arguments longer than 300 characters are rejected; matches against listed injection patterns are also rejected.", "`backend\\src\\main.py`, `tool_args_violation`.", "Input guard; it does not measure model intent accuracy."),
        ("SQL date rules", "The SQL prompt asks for dates on or after the current India date, but also contains the fixed reference date October 5, 2026.", "`backend\\autogen_flow\\airline_autogen_flow.py`, `generate_sql`.", "The fixed date can conflict with the dynamic SQL expression."),
        ("Voice response length", "The system instruction requests 2-3 sentences generally; flight-list answers may use 4-5 short sentences. For more than 5 rows, it asks for at least 5 examples rather than the full list.", "`backend\\src\\main.py`, `build_setup_message`; `build_flight_digest`; `_flight_search_gemini_lines`.", "Prompt-level response rules, not a measured speech quality metric."),
        ("Capture frame duration", "Frame size is `round(captureSampleRate * 20 / 1000)` samples.", "`frontend\\src\\hooks\\useRealtimeAgent.js`, `CAPTURE_FRAME_MS`, `startSession`.", "Audio input batching target is 20 ms."),
        ("Output playback sample rate", "Playback `AudioContext` and buffers are configured at 24,000 samples/second.", "`frontend\\src\\hooks\\useRealtimeAgent.js`, `PLAYBACK_SAMPLE_RATE`, `playNextChunk`.", "Audio playback setting."),
        ("Barge-in RMS values", "The hook increments an accumulator by 20 ms while frame RMS is greater than 0.12, then discards it with `void`. The declared 180 ms constant is not used in that check, and no interruption action uses the accumulator.", "`frontend\\src\\hooks\\useRealtimeAgent.js`, `BARGE_IN_RMS_THRESHOLD`, `BARGE_IN_SUSTAIN_MS`, `startSession`.", "The constants currently do not implement barge-in behavior."),
        ("k6 connection time", "Elapsed milliseconds from just before `ws.connect` to socket `open`, stored as a Trend.", "`backend\\loadtest.js`, `connectionTime`.", "Recorded by k6; no threshold is defined for this Trend."),
        ("k6 tool response time", "Elapsed milliseconds from sending the sample query after `setupComplete` to the first `toolResult`.", "`backend\\loadtest.js`, `toolResponseTime`.", "P95 threshold is under 3,500 ms."),
        ("k6 `ws_backpressure_drops_1013`", "Counter increments when socket close code equals 1013.", "`backend\\loadtest.js`, close handler.", "Expected at capacity; no maximum threshold."),
        ("k6 `ws_ratelimit_drops_4008`", "Counter increments on close code 4008.", "`backend\\loadtest.js`, close handler.", "Threshold: fewer than 5 during the test."),
        ("k6 `ws_other_drops`", "Counter increments for unexpected close codes (not 1000 or 1005) and qualifying socket errors.", "`backend\\loadtest.js`, close/error handlers.", "Threshold: fewer than 20."),
        ("k6 `ws_setup_never_completed`", "Counter increments on each closed connection that never received `setupComplete`.", "`backend\\loadtest.js`, close handler.", "Diagnostic counter; no threshold is set."),
        ("k6 `ws_setup_completed_rate`", "Rate of closed connections whose `setupComplete` flag became true.", "`backend\\loadtest.js`, close handler.", "Threshold: rate greater than 0.90."),
        ("k6 `ws_tool_result_received_rate`", "For connections with setup complete, rate whose socket received a tool result.", "`backend\\loadtest.js`, close handler.", "Threshold: rate greater than 0.85."),
        ("k6 connection check", "`check` succeeds when `ws.connect` response exists and status is 101.", "`backend\\loadtest.js`, `check(res, ...)`.", "Basic WebSocket handshake assertion."),
        ("UI flight counts", "Toolbar displays backend `count` and `processedFlights.length`; latter is count after client-side filters.", "`frontend\\src\\App.jsx`, `handleFlightResults` and filtering; `ResultsToolbar.jsx`.", "A view count, not booking success. Backend result helper currently omits truncated/widened metadata."),
        ("UI price filter ranges", "Positive fares are selected from `total_fare_inr || price_inr || fare`. If max-min is under 500, one ceiling(max) range is shown; otherwise, three ceilings at min + 1/3 range, min + 2/3 range, and max are shown.", "`frontend\\src\\App.jsx`, `generatePriceRanges`.", "This is derived from the currently received rows; it does not calculate market price statistics."),
        ("k6 load stages", "0 to 100 VUs over 15 s, then 250 over 15 s, hold 250 for 30 s, then ramp to 0 over 10 s.", "`backend\\loadtest.js`, `options.scenarios.voice_agent_spike`.", "Scenario configuration; not a production capacity result."),
    ])
    add_para(doc, "The SQL flow performs one repair generation after a query error. If a valid query returns no rows, it makes one widened-date attempt. These are control-flow retry rules, not a measured success rate; source is `run_sql_pipeline`.")

    add_heading(doc, "1.f Services Used", 2)
    add_table(doc, ["Service", "Use"], [
        ("Google Gemini Live", "Upstream real-time voice WebSocket: audio understanding, tool calls and audio response."),
        ("Azure OpenAI", "Chat completions for generated SQL and spoken-answer text; embeddings for policy search."),
        ("Azure SQL", "Flight data queries to `dbo.voice_agent_data`."),
        ("Azure AI Search", "Policy vector search against the configured index."),
        ("Azure Redis", "Optional semantic cache; rate limiting and resumption storage are also attempted through Redis."),
        ("SMTP server", "Optional booking-handoff email when `SMTP_HOST` is configured."),
        ("Telephony provider / Azure Speech / Blob Storage", "Not found in active code; browser microphone and Gemini Live are used instead."),
    ])

    add_heading(doc, "1.g Setup and Run Instructions", 2)
    add_table(doc, ["Prerequisite", "Repository evidence"], [
        ("Python", "README says Python 3.10+; local checked venv is Python 3.12.10. No declared `requires-python` metadata was found."),
        ("Node.js", "`frontend\\package-lock.json` engine declarations for locked Vite require `^20.19.0 || >=22.12.0`; README's Node 18+ statement is lower than Vite's engine."),
        ("npm", "Needed for `frontend\\package.json` scripts."),
        ("ODBC", "README specifies ODBC Driver 18 for SQL Server."),
        ("Cloud configuration", "Gemini Live, Azure OpenAI, Azure SQL and Azure AI Search config; Redis/SMTP are optional."),
    ])
    add_para(doc, "Create and activate the venv from the repository root:")
    add_code(doc, "py -3.12 -m venv .\\venv")
    add_code(doc, ".\\venv\\Scripts\\Activate.ps1")
    add_para(doc, "Install backend packages. The second install follows the additional direct imports called out by the README; `backend\\requirements.txt` does not include all of them.")
    add_code(doc, "python -m pip install -r .\\backend\\requirements.txt")
    add_code(doc, "python -m pip install sqlalchemy openai azure-search-documents azure-core")
    add_code(doc, "Copy-Item .\\backend\\.env.example .\\backend\\.env")
    add_para(doc, "Fill required cloud and database values in `backend\\.env`; start the backend from its folder:")
    add_code(doc, "Set-Location .\\backend")
    add_code(doc, "python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload")
    add_para(doc, "In another terminal, run the frontend:")
    add_code(doc, "Set-Location D:\\airline-voice-agent\\frontend")
    add_code(doc, "npm install")
    add_code(doc, "npm run dev")
    add_para(doc, "Then open Vite's local URL. No deployment run sequence or separately started `autogen_flow` service is present.")
    add_para(doc, "To regenerate the documents, install the document-tooling libraries in the active venv if needed and run:")
    add_code(doc, "python -m pip install python-docx matplotlib")
    add_code(doc, "python .\\docs\\build_docs.py")

    add_heading(doc, "1.h Configuration / Environment Variables", 2)
    env_table(doc)

    add_heading(doc, "2. Technical Details", 1)
    add_heading(doc, "2.a Backend and Frontend Flow", 2)
    add_para(doc, "Frontend flow:")
    add_numbered(doc, [
        "`main.jsx` mounts `App.jsx`.",
        "`App` calls `/health`, wires the controls to `useRealtimeAgent`, and renders UI sections.",
        "`handleMicClick` calls `startSession`; the hook creates audio contexts and the microphone worklet.",
        "The worklet emits approximately 20 ms Float32 frames; the hook converts them to PCM16/base64 and sends JSON audio over `/ws/audio`.",
        "The hook receives JSON messages, queues and plays Gemini audio, and passes non-empty tool rows to `App.handleFlightResults`.",
        "`App` filters/sorts rows and renders `FlightTable` and `ResultsToolbar`. Text submission is currently a no-op.",
    ])
    add_para(doc, "Backend flow:")
    add_numbered(doc, [
        "`main.py` loads environment values and builds a FastAPI app.",
        "The lifespan initializes policy middleware and calls the SQL flow warm-up.",
        "`websocket_audio` applies optional API-key, rate and capacity checks, then opens Gemini's upstream WebSocket.",
        "`build_setup_message` sends model instructions and tool declarations.",
        "`relay_client_to_gemini` forwards client messages; `relay_gemini_to_client` relays output and handles tool calls.",
        "`execute_tool_call` dispatches flight/status to SQL, policy to the router/RAG path, and booking to email handoff.",
        "Tool data is returned to Gemini and, for flight rows, the browser. On disconnect, tasks end and the semaphore is released.",
    ])
    add_para(doc, "Per-turn pipeline:")
    add_para(doc, "Input audio -> Gemini transcription and model turn -> optional function call -> argument checks -> SQL or policy pipeline -> tool response back to Gemini -> generated audio -> browser playback. Flight rows travel as an additional `toolResult` message to the UI.")
    add_para(doc, "Text interaction diagram:")
    add_code(doc, "Caller microphone -> React AudioWorklet -> WS /ws/audio -> Gemini Live")
    add_code(doc, "Gemini function call -> FastAPI execute_tool_call -> Azure SQL or Azure AI Search")
    add_code(doc, "Azure result -> Gemini toolResponse -> Gemini audio -> FastAPI WS -> React playback -> caller")
    add_code(doc, "Azure SQL flight rows -> FastAPI toolResult -> App state -> FlightTable")

    add_heading(doc, "2.b APIs and Major Functions", 2)
    add_para(doc, "API endpoints:")
    add_table(doc, ["Method", "Endpoint", "Purpose / body / response"], [
        ("GET", "`/health`", "Unauthenticated health object: `status`, `message`, version and service states. Does not require request body."),
        ("POST", "`/execute-tool`", "Optional API-key and rate-limit dependencies. JSON body: `{tool_name, arguments, utterance?}`. Accepted names: `get_flight_status`, `search_flights`, `search_policy`. Response model: `{success, data?, error?}`."),
        ("WebSocket", "`/ws/audio`", "Optional `api_key`, `session_id`, and `resume` query parameters. Browser sends JSON `realtimeInput.audio` frames. Backend relays Gemini messages and emits `toolResult` for non-empty flight results."),
    ])
    add_para(doc, "Major backend functions:")
    add_table(doc, ["Function area", "Responsibility / file"], [
        ("`websocket_audio`, `build_setup_message`", "Open browser and Gemini sessions, configure model/tools, manage capacity. `backend\\src\\main.py`."),
        ("`relay_client_to_gemini`, `relay_gemini_to_client`", "Forward WebSocket messages, collect transcription text, relay tool calls/results and audio. `backend\\src\\main.py`."),
        ("`execute_tool_call`, `_run_tool_with_timeout`", "Validate/dispatch function calls and apply timeout. `backend\\src\\main.py`."),
        ("`execute_flight_search`, `execute_flight_status`, `execute_policy_search`", "Build questions and route tool requests. `backend\\src\\main.py`."),
        ("`_gateway_router_flow`, `run_policy_pipeline`", "Route SQL/policy/mixed; combine SQL and policy results. `backend\\src\\main.py`."),
        ("`run_sql_pipeline`, `generate_sql`, `execute_query`, `generate_answer`", "Generate and validate T-SQL, query Azure SQL, form voice-ready answer. `backend\\autogen_flow\\airline_autogen_flow.py`."),
        ("`AirlineMiddleware.initialize`, `search_policy`, `check_rate_limit`", "Initialize Azure/Redis integrations, retrieve policy passages and apply Redis rate checks. `backend\\src\\middleware.py`."),
        ("`health_check`, `execute_tool`", "HTTP health and REST tool endpoints. `backend\\src\\main.py`."),
    ])
    add_para(doc, "Major frontend functions:")
    add_table(doc, ["Function area", "Responsibility / file"], [
        ("`App`, `handleFlightResults`, `renderFlightSection`", "Own results/status state, sorting/filtering and table rendering. `frontend\\src\\App.jsx`."),
        ("`useRealtimeAgent`, `startSession`, `handleMicClick`, `stopSession`", "Capture/play audio and manage the WebSocket lifecycle. `frontend\\src\\hooks\\useRealtimeAgent.js`."),
        ("`SearchCard`, `Header`", "Render microphone/call controls and status. `frontend\\src\\components\\SearchCard.jsx`, `Header.jsx`."),
        ("`FlightTable`", "Render each result row and Book callback. `frontend\\src\\components\\FlightTable.jsx`."),
        ("`ResultsToolbar`", "Render client-side sort and filter controls. `frontend\\src\\components\\ResultsToolbar.jsx`."),
        ("`executeTool`", "Unused REST helper for `/execute-tool`; no active app import found. `frontend\\src\\api.js`."),
    ])

    add_heading(doc, "2.c Data Flow", 2)
    add_para(doc, "Inputs:")
    add_table(doc, ["Data", "Format", "Role"], [
        ("Microphone signal", "Browser MediaStream samples; converted Float32 to signed PCM16, base64-encoded in JSON.", "Voice input to Gemini Live through FastAPI."),
        ("Gemini tool arguments", "JSON object with route/date/flight number or policy query/category.", "Select lookup and build natural-language SQL/policy query."),
        ("Transcription", "Gemini server-content text.", "Per-session utterance context and history for tool calls."),
        ("SQL rows", "Azure SQL rows converted to JSON records.", "Structured flight data for audio and table."),
        ("Policy text", "Azure AI Search result fields `id`, `source`, `content`, `@search.score`.", "Source material for policy answer."),
        ("Generated speech", "Gemini inline audio data, PCM playback context at 24 kHz.", "Audible response in the browser."),
    ])
    add_para(doc, "Processing and response objects:")
    add_bullets(doc, [
        "`POST /execute-tool` accepts `{tool_name, arguments, utterance?}` and returns a `ToolResponse` with `success`, optional `data`, or optional `error`.",
        "Flight tool data contains `route`, `dynamic_sql_used`, `flight_results`, `count`, and `summary`; policy data can add `policy_information`.",
        "The WebSocket tool result to the UI normally contains `flight_results` and `count` only. `SEND_TOOL_EVENTS_TO_CLIENT=true` changes this to send the full result object.",
        "The browser stores result rows in React state and applies local filters; no client database is used.",
    ])
    add_para(doc, "Storage and lifetime:")
    add_table(doc, ["Store", "Content", "Lifetime"], [
        ("Azure SQL", "Flight schedule/status rows in `dbo.voice_agent_data`.", "External database; retention controlled outside this repository."),
        ("Azure AI Search", "Policy documents and vector field used by configured index.", "External service; no ingestion job or local document set found."),
        ("Redis policy cache", "Query text, category, response JSON and 1536-dimension query vector.", "`POLICY_CACHE_TTL_SECONDS` default 600 seconds."),
        ("Redis resume key", "Gemini resume handle under `session:resume:<session_id>`.", "One hour (`ex=3600`) when stored by backend and a session id is provided."),
        ("Redis rate-limit keys", "Counter per route/client-IP key.", "Expiry window passed by caller: 60 seconds."),
        ("Python process memory", "Schema cache and per-WebSocket transcription context.", "Schema cache 600 seconds; session context until socket ends; history capped at 10 entries and utterance at 2,000 characters."),
        ("Browser React state", "Current flight rows, sort/filter settings and UI status.", "Page/session memory; no durable client persistence found."),
        ("Backend log file", "Application log records.", "File path is `LOG_FILE` (default `backend.log`); rotation/retention is not configured in source."),
    ])

    add_heading(doc, "2.d LLM / RAG / Agent Flow", 2)
    add_para(doc, "Gemini Live model and audio voice are configured by `GEMINI_MODEL_NAME` and `GEMINI_VOICE_NAME` in `backend\\src\\main.py`. Azure OpenAI chat uses `CHAT_DEPLOYMENT` for SQL generation and answer text. Azure OpenAI embeddings use `EMBEDDING_DEPLOYMENT` in policy retrieval.")
    add_para(doc, "The system instruction in `build_setup_message` calls the assistant Sky. It sets language mirroring rules, asks the model to call tools rather than invent flight/policy facts, summarizes flights rather than reading a large list, and defines a booking-handoff response. The full prompt is embedded in source; no separate prompt file exists.")
    add_table(doc, ["Agent tool", "Arguments", "Backend action"], [
        ("`search_flights`", "Origin, destination, optional date or date range.", "`execute_flight_search` -> `run_sql_pipeline` -> Azure SQL."),
        ("`get_flight_status`", "Required flight number, optional date.", "`execute_flight_status` -> `run_sql_pipeline` -> Azure SQL."),
        ("`search_policy`", "Required query, optional category.", "Router may choose policy, SQL or mixed; policy path embeds and searches Azure AI Search."),
        ("`initiate_booking_handoff`", "Optional flight number, route, customer note.", "Schedules email routine; returns handoff message. It does not book/ticket a flight."),
    ])
    add_para(doc, "Conversation context is held in the backend WebSocket context, not persisted as a transcript database. The latest transcription entries are capped at 10; the accumulated current utterance is capped at 2,000 characters. Gemini session-resumption handles are stored in Redis for one hour only when the backend receives a session id. The current browser hook opens `/ws/audio` without `session_id` or `resume`, and its setup message is discarded by the backend relay. Therefore cross-reconnect restoration is not established by the current browser path.")
    add_para(doc, "Fallback behavior: SQL imports can fail and mark the flow unavailable; flight tools then return an unavailable error. Policy middleware initialization failures leave policy service unavailable. The SQL route classifier falls back to SQL on invalid/failed classification. Chat completion retries without `reasoning_effort` after `BadRequestError`. Redis is optional; cache failures can fall through to AI Search, and rate-limit checks allow requests when Redis is disabled or errors. Gemini connection failures close the WebSocket with an error code.")

    add_heading(doc, "2.e Important Implementation Details", 2)
    add_table(doc, ["Topic", "Implementation"], [
        ("Naming / locations", "FastAPI application is `app` in `backend\\src\\main.py`. React entry is `frontend\\src\\main.jsx`; app component is `App.jsx`. SQL module is named `autogen_flow`, but no AutoGen library/agent is imported."),
        ("Concurrency", "FastAPI uses async endpoints and WebSocket relay tasks. SQL work is run with `asyncio.to_thread`; SQL execution itself uses a one-worker `ThreadPoolExecutor`. Multiple Gemini tool calls are gathered concurrently."),
        ("Audio buffering", "`useRealtimeAgent.js` uses an AudioWorklet buffer sized from sample rate * 20 ms. Input PCM is base64 in `realtimeInput.audio`; output PCM is queued and played at 24 kHz."),
        ("Error format / HTTP", "`/execute-tool` model has `{success,data,error}`. Validation errors use HTTP 400; bad API key 401; Redis-backed rate limiting 429; unavailable SQL flow 503. Unexpected endpoint exceptions are logged and returned as `success:false` (unless raised as HTTP exception)."),
        ("WebSocket close codes", "4001 unauthorized; 4008 rate limit; 1011 voice/upstream unavailable; 1013 capacity; normal client stop uses 1000."),
        ("Timeouts / retries", "Upstream Gemini connect default 8 seconds; tool default 20 seconds; SQL execution 7 seconds and at most one repair attempt; Redis connect/read 0.5 seconds. SQL zero rows trigger one widened-date attempt. Reconnect in browser uses exponential delay with up to 5 attempts."),
        ("CORS / access", "CORS defaults to localhost ports 5173 and 3000. Optional `BACKEND_API_KEY` protects REST and WebSocket, but active UI does not send it. No user login/session authorization system was found."),
        ("SQL safeguards", "`execute_query` requires SELECT/CTE start, rejects semicolon and listed forbidden keywords, and requires the configured table name in SQL. The SQL is model-generated."),
        ("Key dependencies", "`fastapi`, `uvicorn`, `websockets`, `python-dotenv`, `pandas`, `pyodbc`, `redis`, `numpy`, SQLAlchemy, OpenAI SDK and Azure Search SDK. `frontend\\package.json` uses React, React DOM, Vite and React plugin. Google client packages are present but not imported by active frontend source."),
        ("Tests / load hooks", "No automated unit/integration test files were found. `backend\\loadtest.js` is a k6 load-test script and placeholder key is not a real credential. `GET /health` is the available service health check."),
        ("Documentation generator", "`docs\\build_docs.py` uses `python-docx` and `matplotlib`; it is documentation tooling, not an application runtime dependency."),
    ])
    add_table(doc, ["Limit / threshold", "Calculation / behavior", "Source"], [
        ("Upstream Gemini connection", "`asyncio.wait_for` wraps `websockets.connect`; default timeout is 8 seconds.", "`backend\\src\\main.py`, `websocket_audio`; `GEMINI_CONNECT_TIMEOUT_SECONDS`."),
        ("One tool call", "`asyncio.wait_for` wraps `execute_tool_call`; default limit 20 seconds.", "`backend\\src\\main.py`, `_run_tool_with_timeout`; `TOOL_TIMEOUT_SECONDS`."),
        ("SQL execution", "`future.result(timeout=7.0)` limits one query attempt to 7 seconds.", "`backend\\autogen_flow\\airline_autogen_flow.py`, `execute_query`."),
        ("Voice capacity acquire", "Semaphore acquire is awaited for 0.1 seconds; timeout closes with 1013.", "`backend\\src\\main.py`, `websocket_audio`; semaphore capacity from `AirlineMiddleware.__init__`."),
        ("REST / WebSocket rate", "Redis count must be no greater than the configured limit in a 60-second expiry window; defaults are 60 REST and 10 WS connections per client IP.", "`backend\\src\\main.py`, `enforce_rest_rate_limit`, `websocket_audio`; `backend\\src\\middleware.py`, `check_rate_limit`."),
        ("Incoming upstream message size", "Default maximum is 2 * 1024 * 1024 bytes.", "`backend\\src\\main.py`, `GEMINI_WS_MAX_SIZE_BYTES` and `websockets.connect`."),
        ("Browser reconnect", "At most 5 retries. Delay is `min(1000 * 2^attempt, 15000) + random(0, 400)` milliseconds.", "`frontend\\src\\hooks\\useRealtimeAgent.js`, `scheduleReconnect`."),
        ("Backend setup relay wait", "Client-to-Gemini relay waits up to 5 seconds for setup completion before proceeding.", "`backend\\src\\main.py`, `relay_client_to_gemini`."),
        ("User utterance for tool handling", "Cleaning strips whitespace, limits input to 500 characters, then drops it if a listed pattern matches.", "`backend\\src\\main.py`, `_clean_utterance`; `MAX_UTTERANCE_LENGTH`."),
    ])

    path = DOCS / "Project_Documentation.docx"
    doc.save(path)
    return path


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    first = details_document()
    second = technical_document()
    print(f"Generated: {first}")
    print(f"Generated: {second}")
    print(f"Generated: {DOCS / 'architecture.png'}")


if __name__ == "__main__":
    main()
