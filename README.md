# Cabbo FastAPI Project

This project is the backend for the Cabbo cab booking platform, built with FastAPI and managed with uv.

## Setup

### 1. Create and activate the virtual environment

#### Windows (PowerShell):
```powershell
uv venv
.\.venv\Scripts\activate
```

#### Linux/macOS (bash):
```bash
uv venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
uv pip install -r pyproject.toml
```

Or, for manual install:
```bash
uv pip install fastapi uvicorn[standard]
```

## Running the Server

### Windows or Linux/macOS

#### Option 1: Using Uvicorn (recommended for development)
```bash
uvicorn main:app --reload
```

#### Option 2: Directly with Python (auto-reload enabled)
```bash
python main.py
```

## Project Structure
- `main.py`: FastAPI entrypoint
- `pyproject.toml`: Project dependencies and metadata

---

