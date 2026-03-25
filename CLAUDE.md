# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Codex Proxy is a FastAPI service that translates OpenAI Codex Responses API requests to Alibaba Cloud Coding Plan Chat Completions API format. It acts as an adapter layer, allowing Codex CLI to work with Coding Plan's backend.

## Commands

```bash
# Install (development mode with test dependencies)
pip install -e ".[dev]"

# Run the server
python -m codex_proxy.main
# Or: uvicorn codex_proxy.main:app --host 127.0.0.1 --port 8080
# Or: codex-proxy (after install)

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_converter.py -v

# Run with coverage
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

## Architecture

```
Request Flow:
OpenAI Responses API request → /v1/responses endpoint
    → Converter.to_chat_completions_request() (format translation)
    → CodingPlanClient.chat() (HTTP request to Coding Plan)
    → Converter.to_responses_response() (format translation back)
    → OpenAI Responses API response
```

### Core Components

| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app creation, lifespan management, logging middleware |
| `router.py` | API endpoints (`/health`, `/v1/responses`), streaming response generator |
| `converter.py` | Bidirectional format conversion between Responses API and Chat Completions |
| `client.py` | Async HTTP client for Coding Plan API, handles streaming SSE parsing |
| `models.py` | Pydantic models for Responses API request/response types |
| `config.py` | YAML configuration loading with `${ENV_VAR}` substitution |
| `config.yaml` | Runtime configuration (model mapping, API key, server settings) |

### Key Format Conversions

- **Input → Messages**: `input` string/list becomes `messages` array; `instructions` becomes system message
- **Role Mapping**: `developer` role maps to `system`
- **Model Resolution**: Request model names (e.g., `gpt-5.4`) are mapped via `model_mapping` in config
- **Response ID**: `chatcmpl-xxx` becomes `resp_xxx`
- **Streaming Events**: Chat Completions SSE → `response.output_text.delta`/`response.completed` events

## Configuration

Copy `config.example.yaml` to `config.yaml`. The API key uses environment variable substitution:

```yaml
coding_plan:
  api_key: "${CODING_PLAN_API_KEY}"
  model_mapping:
    "gpt-5.4": "qwen3.5-plus"
```

Set `CODING_PLAN_API_KEY` environment variable before running.

## Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. The `respx` library mocks HTTP requests to Coding Plan API. Test files mirror the module structure: `test_converter.py` tests `converter.py`, etc.