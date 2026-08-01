# Sentrix API

FastAPI-based API gateway for the Sentrix AI Cybersecurity Platform.

## Stack

- **Python** 3.10+
- **FastAPI** — API framework
- **Uvicorn** — ASGI server
- **Pydantic Settings** — configuration
- **Ruff** — linter / formatter
- **Pytest** — test runner

## Project Structure

```
apps/api/
├── app/
│   ├── api/v1/          # Versioned API routes
│   ├── core/            # Cross-cutting concerns
│   ├── db/              # Database connections
│   ├── models/          # ORM models
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   ├── repositories/    # Data access layer
│   ├── agents/          # AI agents
│   ├── rag/             # RAG knowledge layer
│   ├── tools/           # Cybersecurity tool execution
│   ├── middleware/      # ASGI middleware
│   ├── utils/           # Helpers
│   ├── config/          # Pydantic settings
│   └── main.py          # FastAPI entry point
├── tests/               # Pytest suite
├── pyproject.toml       # Project config + deps
├── .env.example         # Env template
└── README.md
```

## Development

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies (with dev extras)
pip install -e ".[dev]"

# Run the server
uvicorn app.main:app --reload

# Run tests
pytest

# Lint & format
ruff check .
ruff format .
```

## Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"Sentrix API","version":"0.1.0"}
```

