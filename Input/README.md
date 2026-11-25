# Project Input Inventory

This inventory records local files that could be inputs, examples, or reference material. Large or secret-bearing files are listed only; nothing is copied here. The running app does not load sample audio or flight rows from a local dataset.

| File name | Location in repository | Purpose / use |
|---|---|---|
| `backend\.env` | `backend\.env` | Local service configuration. This file is ignored by Git and may contain secrets. It was not opened or copied. |
| `backend\.env.example` | `backend\.env.example` | Placeholder configuration template. The backend does not read this template; copy it to `backend\.env` for setup. |
| `frontend\.env.local` | `frontend\.env.local` | Local Vite configuration. This file is ignored by Git and was not opened. The source reads `VITE_BACKEND_URL`. |
| `frontend\src\constants.js` | `frontend\src\constants.js` | Active UI suggestion strings shown by the React app. Selecting one fills the text field; current text submission is a no-op. |
| `backend\loadtest.js` | `backend\loadtest.js` | Standalone k6 WebSocket load test. It sends a sample text request after a session is established. It is not started by the app. |
| `backend\SELECT TOP 100.sql` | `backend\SELECT TOP 100.sql` | Manual Azure SQL inspection examples. The live code does not execute this file. |
| `AICOE_POC_Package\airline-voice-agent\Input\azure_sql_schema_probe.sql` | `AICOE_POC_Package\airline-voice-agent\Input\azure_sql_schema_probe.sql` | SQL schema/data probe kept in the POC package. No active application code references it. |
| `AICOE_POC_Package\airline-voice-agent\Input\sample_voice_queries_constants.js` | `AICOE_POC_Package\airline-voice-agent\Input\sample_voice_queries_constants.js` | Older sample query constants. The app has its active sample queries in `frontend\src\constants.js`; no active import of this POC copy was found. |
| `AICOE_POC_Package\airline-voice-agent\Airline_Voice_Agent_POC.pdf` | `AICOE_POC_Package\airline-voice-agent\Airline_Voice_Agent_POC.pdf` | POC reference document. The application does not load it. |
| `backend\info.db` | `backend\info.db` | Local SQLite file present in the backend folder. No active backend source reference was found. Flight queries use Azure SQL instead. |
| Azure AI Search index documents | External Azure AI Search resource; not present as local files in this repository | Policy retrieval reads the configured index. No local policy-document set or indexing/ingestion script was found. |
| Flight/booking sample dataset | Not found | The application queries Azure SQL table `dbo.voice_agent_data`. No local flight/booking dataset file is loaded by the app. |
| Sample audio / uploaded audio | Not found | The browser captures microphone audio at runtime. No sample audio file or file-upload UI was found. |
| Standalone prompt files | Not found | Voice instructions and SQL-generation prompts are embedded in `backend\src\main.py` and `backend\autogen_flow\airline_autogen_flow.py`. |

No files were copied from their existing locations.
