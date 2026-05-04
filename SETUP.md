# Setup Guide

Practical Windows PowerShell setup for the PropScore hackathon demo.

## Prerequisites

- Python 3.11+
- Node.js and npm
- Git
- Ollama, if you want local AI underwriter summaries

## 1. Backend Setup

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt
```

## 2. Seed SQLite

```powershell
New-Item -ItemType Directory -Force D:\PropScore\data
$env:SQLITE_DB_PATH="D:/PropScore/data/propscore.sqlite"
python backend/db/seed_sqlite.py
```

Expected result: a local SQLite database at `D:/PropScore/data/propscore.sqlite`.

## 3. Start Backend

```powershell
$env:SQLITE_DB_PATH="D:/PropScore/data/propscore.sqlite"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="qwen2.5:7b"
$env:OLLAMA_FALLBACK_MODEL="llama3.2:3b"
$env:OLLAMA_FAST_MODEL="llama3.2:3b"
$env:OLLAMA_TIMEOUT_SECONDS="150"
$env:OLLAMA_FAST_TIMEOUT_SECONDS="300"
$env:LLM_DEBUG="false"
python -m uvicorn backend.main:app --reload --port 8000
```

Health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

## 4. Frontend Setup

Open a second PowerShell window:

```powershell
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

Open the Vite URL shown in the terminal, usually:

```text
http://127.0.0.1:5173
```

## 5. Ollama Setup

Optional: place Ollama model files on the D drive.

```powershell
setx OLLAMA_MODELS "D:\PropScore\models\ollama"
```

Restart PowerShell after running `setx`, then pull models:

```powershell
ollama pull qwen2.5:7b
ollama pull llama3.2:3b
ollama list
```

Notes:

- `qwen2.5:7b` is the primary enhanced explanation model.
- `llama3.2:3b` is the fast/fallback explanation model.
- Deterministic valuation and scoring do not require Ollama.

## 6. Troubleshooting

### Backend package missing

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements-dev.txt
```

### Backend import issues

- Make sure you are in the repository root containing `backend/main.py`.
- Start with `python -m uvicorn backend.main:app --reload --port 8000`.

### Frontend cannot reach backend

- Confirm backend is running at `http://127.0.0.1:8000`.
- Set frontend API URL:

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
```

Use `127.0.0.1` instead of `localhost` if the browser or Ollama behaves inconsistently.

### SQLite DB path missing

```powershell
New-Item -ItemType Directory -Force D:\PropScore\data
$env:SQLITE_DB_PATH="D:/PropScore/data/propscore.sqlite"
python backend/db/seed_sqlite.py
```

### Ollama timeout

- Keep `OLLAMA_TIMEOUT_SECONDS=150`.
- Keep `OLLAMA_FAST_TIMEOUT_SECONDS=300`.
- `qwen2.5:7b` can be slow on low-RAM machines.
- The backend supports `llama3.2:3b` fast/fallback mode and a rule-based fallback.

### qwen too slow

Use the dashboard normally. The frontend asks for the fast `llama3.2:3b` summary first and only attempts the enhanced `qwen2.5:7b` summary afterward.

### Docker

Docker is optional for this submission. Local Windows setup is the recommended demo path. If using Docker, mount the SQLite path and keep Ollama running on the host machine.
