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

## Endpoints

### Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"Sentrix API","version":"0.1.0"}
```

### Conversation (AI Copilot)

`POST /api/v1/conversations/message` — send a message to the AI conversation engine.

Request:

```json
{
  "conversation_id": "conv-1f3a9c2b",
  "message": "Investigate the beacon pattern on LAB-07"
}
```

Response:

```json
{
  "conversation_id": "conv-1f3a9c2b",
  "response": "I've triaged the telemetry referenced in your request…",
  "timestamp": "2026-08-01T14:36:36.393114Z",
  "metadata": {
    "model": "sentrix-mock-0.1",
    "reasoning": null,
    "evidence": null,
    "sources": null,
    "tools_used": null,
    "execution_time_ms": 12
  }
}
```

The `metadata` block is the reserved contract for the future AI engine — fields for
reasoning, evidence, sources, and tools are populated once the AI router and RAG layers
are integrated. The engine is currently mock-backed and stateless (`conversation_id` is
client-generated).

## Test Suite

```bash
# Run all tests (auth, conversations, health)
pytest tests/ -v
```


