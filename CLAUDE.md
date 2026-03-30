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

# Run a single test file
pytest tests/test_converter.py -v

# Run a specific test
pytest tests/test_converter.py::TestConverterRequestConversion::test_convert_simple_string_input -v

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
| `main.py` | FastAPI app creation, lifespan management, logging setup with daily rotation |
| `router.py` | API endpoints (`/health`, `/v1/responses`), streaming response with full event sequence |
| `converter.py` | Bidirectional format conversion between Responses API and Chat Completions |
| `client.py` | Async HTTP client for Coding Plan API, SSE streaming parsing |
| `models.py` | Pydantic models for Responses API request/response types |
| `config.py` | YAML configuration with `${ENV_VAR}` substitution, model mapping |
| `tools.py` | Tool-calling streaming state helpers and Responses function-call item builders |
| `logging_utils.py` | Request ID generation, payload truncation, console formatter with ANSI color support |

### Key Format Conversions

- **Input → Messages**: `input` string/list becomes `messages` array; `instructions` becomes system message
- **Role Mapping**: `developer` role maps to `system`
- **Model Resolution**: Request model names (e.g., `gpt-5.4`) are mapped via `model_mapping` in config
- **Response ID**: `chatcmpl-xxx` becomes `resp_xxx`
- **Reasoning Content**: `reasoning_content` from upstream (qwen3.5-plus) is merged into output text
- **Tool Calls**: `function_call` / `function_call_output` items are converted to and from Chat tool-call messages
- **Tool Parameters**: `tool_choice` and `parallel_tool_calls` are forwarded when present
- **Streaming Events**: Full event sequence including text deltas and tool-call argument events such as `response.function_call_arguments.delta` / `done`

## Configuration

Copy `config.example.yaml` to `config.yaml`. Key settings:

```yaml
coding_plan:
  api_key: "${CODING_PLAN_API_KEY}"  # Required, from env var
  model_mapping:
    "gpt-5.4": "qwen3.5-plus"        # Map Codex model names to upstream
```

Set `CODING_PLAN_API_KEY` environment variable before running. Empty API key raises `ConfigurationError`.

## Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. The `respx` library mocks HTTP requests. Test files mirror module structure: `test_converter.py` tests `converter.py`.

## Feature Status

Current status:

- **Tool calling**: implemented for `function_call` output and `function_call_output` input handling
- **`tool_choice` / `parallel_tool_calls`**: implemented
- **Structured output**: `text.format` → `response_format` conversion (P2)
- **Reasoning output**: `reasoning` type items in response output (P2)
