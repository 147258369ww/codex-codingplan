# Codex Proxy

Proxy service that adapts OpenAI Codex (Responses API) to Alibaba Cloud Coding Plan (Chat Completions API).

## Features

- Translates OpenAI Responses API requests to Chat Completions API format
- Supports both streaming and non-streaming responses
- Handles function/tool calls with proper format conversion
- Environment variable substitution in configuration
- Health check endpoint for monitoring

## Requirements

- Python >=3.10

## Installation

```bash
cd codex-proxy
pip install -e .
```

Or with development dependencies:

```bash
pip install -e ".[dev]"
```

## Configuration

1. Copy the example configuration:
```bash
cp config.example.yaml config.yaml
```

2. Set your API key as an environment variable:
```bash
export CODING_PLAN_API_KEY="your-api-key-here"
```

3. Edit `config.yaml` to customize model and other settings.

### Configuration Options

| Section | Option | Description | Default |
|---------|--------|-------------|---------|
| `server` | `host` | Server bind address | `127.0.0.1` |
| `server` | `port` | Server port | `8080` |
| `coding_plan` | `base_url` | Coding Plan API base URL | `https://coding.dashscope.aliyuncs.com/v1` |
| `coding_plan` | `api_key` | API key (supports `${ENV_VAR}` syntax) | Required |
| `coding_plan` | `model` | Model name to use | `qwen-coder-plus` |
| `coding_plan` | `timeout` | Request timeout in seconds | `300` |
| `logging` | `level` | Log level | `INFO` |
| `logging` | `format` | Log format string | Standard format |

## Running

```bash
# Direct run
python -m codex_proxy.main

# Or using uvicorn
uvicorn codex_proxy.main:app --host 127.0.0.1 --port 8080

# Or using the installed script
codex-proxy
```

## Codex Configuration

Modify `~/.codex/config.toml` to use this proxy:

```toml
base_url = "http://127.0.0.1:8080/v1"
model = "qwen-coder-plus"

[model_providers.coding_plan_proxy]
name = "coding_plan_proxy"
base_url = "http://127.0.0.1:8080/v1"
env_key = "CODING_PLAN_API_KEY"
wire_api = "responses"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check - returns `{"status": "ok"}` |
| `/v1/responses` | POST | Responses API entry point |

## Testing

Run all tests:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

## API Format Conversion

### Request Conversion

The proxy converts OpenAI Responses API requests to Chat Completions format:

- `input` messages are converted to `messages` array
- `instructions` becomes the system message
- `function_call` input history becomes assistant `tool_calls`
- `function_call_output` inputs become Chat `tool` messages
- `tools` are converted to Chat `tools` definitions
- `tool_choice` and `parallel_tool_calls` are forwarded when present
- `stream` flag is preserved

### Response Conversion

- Non-streaming: assistant `tool_calls` are converted back into Responses `function_call` items
- Non-streaming: mixed text and tool-call responses preserve both message text and tool items
- Streaming: text deltas and tool-call argument deltas are emitted as Responses SSE events
- Streaming: tool-call completion emits `response.function_call_arguments.done` and `response.output_item.done`

## Error Handling

The proxy handles errors gracefully:

- API errors from Coding Plan are converted to Responses API error format
- Streaming errors are sent as error events before `[DONE]`
- Internal errors return 500 with descriptive error messages

## License

MIT License
