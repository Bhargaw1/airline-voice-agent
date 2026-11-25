import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from azure.core.credentials import AzureKeyCredential

# Prefer backend/.env (works whether cwd is repo root or backend/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")
load_dotenv()  # optional cwd / root override

# ---- Chat LLM (AutoGen agents) ----
GPT4_LLM_MODEL_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT", "gpt-5-mini")
AZURE_OPENAI_API_BASE = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("CHAT_API_VERSION", "2024-12-01-preview")

# ---- Embeddings (policy search) ----
Embedding_Model = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

# ---- Azure AI Search ----
AZURE_SEARCH_SERVICE_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_credential = AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY", ""))

# ---- Azure SQL (SQLAlchemy engine) ----
# Enforce standard timeouts on connection stages
_odbc = (
    f"DRIVER={{{os.getenv('SQL_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
    f"SERVER={os.getenv('SQL_SERVER')};DATABASE={os.getenv('SQL_DATABASE')};"
    f"UID={os.getenv('SQL_USERNAME')};PWD={os.getenv('SQL_PASSWORD')};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=7;Timeout=7;"
)
engine = create_engine("mssql+pyodbc:///?odbc_connect=" + quote_plus(_odbc))

INPUT_DIR = "."