# Logging Display Design

## Summary

Improve the proxy's logging so day-to-day terminal output is concise and easy to scan, while file logs remain detailed enough for debugging request conversion, streaming behavior, tool calls, and upstream failures.

The preferred approach is a two-layer logging model:

- Console logs: compact request summaries for humans
- File logs: detailed diagnostic events for troubleshooting

This preserves the current rotating file log behavior while making local development and manual verification much less noisy.

## Goals

- Make terminal logs easy to read during interactive development
- Preserve enough detail to debug request conversion and streaming issues
- Correlate summary and detailed logs using a shared `request_id`
- Keep the implementation lightweight and compatible with the current app structure
- Avoid mixing verbose JSON payloads into the console by default

## Non-Goals

- Full structured JSON logging for all sinks
- External log aggregation or telemetry integration
- Reworking the current rotation policy
- Logging every streaming delta to the console

## Current Problems

The current implementation logs useful information, but it is hard to scan because:

- Console and file handlers use the same formatter
- Request payloads are printed inline as formatted JSON
- Streaming event processing can emit noisy debug output
- Request lifecycle information is spread across several ad hoc log lines
- There is no shared request identifier to connect related events quickly

## Recommended Approach

Adopt a split logging strategy:

- Keep console logs focused on request lifecycle summaries and important state changes
- Keep file logs focused on full diagnostic detail, including payloads and upstream error context
- Attach a generated short `request_id` to all request-scoped logs
- Emit semantic log events from the router and middleware instead of hand-written free-form strings

This gives the best balance between usability and diagnostic power without adding heavy dependencies or changing the service architecture.

## User Experience

### Console Log Style

Console output should be a single-line summary format with optional light color when attached to a TTY. It should stay readable even without color.

Example request start:

```text
15:08:41  INFO   req_a13f  POST /v1/responses  model=gpt-5.4 -> qwen3.5-plus  stream=true  input=6msg  tools=2
```

Example tool call summary:

```text
15:08:42  INFO   req_a13f  tool_call  name=search_docs  call_id=call_x9  args=214B
```

Example request completion:

```text
15:08:44  INFO   req_a13f  done  status=200  latency=2.31s  text=684B  tools=1  finish=stop
```

Example upstream error:

```text
15:09:12  WARN   req_b721  upstream_error  status=429  type=rate_limit_error  message="Too many requests"
```

### File Log Style

File logs should keep the existing rotating log file and use a more detailed formatter. They should include enough metadata to reconstruct what happened for a given `request_id`.

Example detailed events:

```text
2026-03-29 15:08:41,224 INFO  codex_proxy.request request.started request_id=req_a13f method=POST path=/v1/responses client=127.0.0.1
2026-03-29 15:08:41,225 INFO  codex_proxy.request request.resolved request_id=req_a13f model_requested=gpt-5.4 model_resolved=qwen3.5-plus stream=true
2026-03-29 15:08:41,226 DEBUG codex_proxy.request request.payload request_id=req_a13f payload={...}
2026-03-29 15:08:42,118 DEBUG codex_proxy.stream tool.delta request_id=req_a13f index=0 call_id=call_x9 name=search_docs delta_bytes=73
2026-03-29 15:08:44,009 INFO  codex_proxy.request request.completed request_id=req_a13f status=200 latency_ms=2310 output_text_chars=684 tool_calls=1
```

## Architecture

### Handler Separation

The application should configure two handlers:

- Console handler
  - Level defaults to `INFO`
  - Uses a compact, human-oriented formatter
  - Emits request summaries, completions, important warnings, and errors
- File handler
  - Level defaults to `DEBUG`
  - Uses a verbose formatter
  - Emits detailed diagnostic events, payloads, streaming deltas, and error context

Both handlers remain attached to the root logger so existing module loggers continue to work.

### Request Context

Each incoming request should receive a short generated `request_id`, for example `req_a13f`.

This identifier should be attached to:

- Middleware request start and completion logs
- Router logs for request conversion and response handling
- Streaming logs
- Validation errors
- Upstream API errors
- Unexpected internal exceptions

The `request_id` should be available on the request object or via a lightweight context mechanism used consistently by middleware and route handlers.

### Logging Utilities Module

Add a small helper module, likely `codex_proxy/logging_utils.py`, to keep formatting and event-building out of business logic.

Responsibilities:

- Generate short request identifiers
- Detect whether color should be enabled
- Provide compact console formatting helpers
- Provide payload truncation helpers
- Format byte and duration summaries
- Build semantic event messages consistently

This avoids scattering formatting logic across `main.py`, `router.py`, and `client.py`.

## Event Model

### Console Events

Console output should be limited to the following event types:

- Request started
- Tool call observed
- Request completed
- Upstream API error
- Validation failure
- Internal error

These events should avoid raw JSON bodies unless an error is small and directly useful.

### File Events

File output may include all console events plus:

- Model resolution
- Request conversion summary
- Truncated converted payload
- Text streaming deltas
- Tool-call argument deltas
- Upstream error payloads
- Exception stack traces
- Usage metadata when available

## Field Conventions

### Required Shared Fields

All request-scoped events should include:

- `request_id`
- event name
- log level

### Console Summary Fields

Depending on event type, console logs should use a fixed order that favors scanning:

- `request_id`
- event or request line
- requested model and resolved model
- `stream`
- `status`
- `latency`
- text size
- tool-call count
- short error type or message

### File Detail Fields

Detailed file logs may additionally include:

- method and path
- client address when available
- message count
- tool count
- usage counters
- finish reason
- payload excerpts
- serialized upstream error payloads

## Boundaries and Safety Rules

- Console logs must not print full converted payload JSON by default
- Console logs must not print every streaming delta event
- Console tool-call logs should show tool name, call identifier, and argument size, not full argument content
- File payload logging should be truncated to a bounded size and marked when truncation occurs
- File logs should preserve exception details for diagnosis

These limits reduce noise and lower the chance of excessive log growth while still preserving enough information for debugging.

## Dependency Strategy

Prefer a lightweight implementation:

- Keep the existing standard-library logging foundation
- Add only minimal color support
- If color is implemented without extra dependencies, that is preferred
- If a small dependency is used, it should be justified by significantly simpler or more reliable terminal behavior

The design should continue to work in non-TTY and plain text environments.

## Configuration Defaults

Defaults should be:

- Console color enabled only when appropriate for the terminal
- Console level `INFO`
- File level `DEBUG`
- Existing timed rotation retained
- Current log file path retained at `logs/codex-proxy.log`

Future extensions may add explicit settings such as:

- `NO_COLOR`
- `LOG_CONSOLE_LEVEL`
- structured JSON mode

These are not required for the initial implementation but the design should not block them.

## Implementation Plan Shape

The implementation should touch these areas:

- `codex_proxy/main.py`
  - split console and file handler configuration
  - wire formatter and filter behavior
- `codex_proxy/router.py`
  - replace current ad hoc info logs with semantic summary and diagnostic events
  - carry `request_id` into streaming and error paths
- `codex_proxy/client.py`
  - keep verbose upstream request and error logs in a file-friendly form
- `codex_proxy/logging_utils.py`
  - new helper module for ids, formatting, truncation, and sink-specific behavior
- tests
  - add coverage for formatting helpers and request lifecycle logging behavior

## Testing Strategy

### Unit Tests

Add tests for the logging utility module:

- request ID generation format
- payload truncation behavior
- byte and duration formatting
- color enable or disable rules
- summary line construction

### Integration-Oriented App Tests

Update or add tests to verify:

- console and file handlers are configured with different responsibilities
- request lifecycle logs include `request_id`
- router emits expected semantic events for success and error paths
- logging changes do not alter response behavior

Tests should validate important fields rather than exact terminal color sequences.

### Manual Verification

Before considering implementation complete:

- run the app locally
- send a normal non-streaming request
- send a streaming request with tool calls
- confirm console output stays compact
- confirm file logs retain useful details for the same `request_id`

## Risks and Mitigations

Risk: Too much logging logic leaks into business code.
Mitigation: centralize formatting and helper logic in `logging_utils.py`.

Risk: Console and file behavior drift over time.
Mitigation: define a small set of semantic events and test them.

Risk: Payload logging becomes too large.
Mitigation: truncate payloads and log summary sizes.

Risk: Color output behaves poorly in non-interactive environments.
Mitigation: enable color only when appropriate and preserve clean plain-text fallback.

## Open Decisions Resolved

The following decisions are fixed for implementation:

- Use the split strategy of concise console logs plus detailed file logs
- Use light color and one-line summaries for the console
- Preserve daily rotating file logs
- Avoid heavy logging dependencies
- Use a shared short `request_id` across request-scoped events

## Success Criteria

The change is successful when:

- terminal output is easy to scan during normal development
- the terminal is no longer flooded with full payload JSON
- a developer can use `request_id` to find detailed logs for one request quickly
- detailed file logs still provide enough information to debug tool-calling and streaming behavior
- existing request handling behavior remains unchanged
