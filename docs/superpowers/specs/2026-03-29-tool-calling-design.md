# Tool Calling Compatibility Design

## Context

This project adapts OpenAI Codex clients that speak the Responses API to Alibaba Cloud Coding Plan, which currently accepts Chat Completions style requests. Basic conversation support is already implemented. The remaining gap is tool-calling compatibility so newer Codex versions can complete multi-step function execution loops through this proxy.

The design in this document focuses on the minimum high-value feature set needed for Codex tool use:

- Responses request input support for `function_call_output`
- Responses request parameter support for `tool_choice` and `parallel_tool_calls`
- Non-streaming conversion of Chat Completions `tool_calls` into Responses `function_call` output items
- Streaming conversion of tool call deltas into Responses semantic events

This design explicitly does not include `text.format` structured output conversion or standalone `reasoning` output items. Those can be added in a follow-up change after tool-calling compatibility is stable.

## Goals

- Preserve the existing text-only conversation path.
- Allow Codex to receive function call requests from upstream Chat Completions responses.
- Allow Codex to send function results back using Responses `function_call_output` items.
- Support both streaming and non-streaming tool-call flows.
- Keep compatibility behavior explicit when Coding Plan cannot represent a Responses feature exactly.

## Non-Goals

- Full parity for every OpenAI Responses built-in tool type.
- Adding synthetic support for unsupported upstream tools.
- Reworking conversation state around `previous_response_id`.
- Implementing structured output conversion.
- Emitting standalone reasoning items beyond current text aggregation behavior.

## Upstream Compatibility Assumptions

The proxy targets Coding Plan endpoints that are Chat Completions compatible and can accept OpenAI-style function calling payloads:

- request `tools`
- request `tool_choice` in supported modes
- request `parallel_tool_calls` when accepted by the upstream model
- response `message.tool_calls`
- streaming `delta.tool_calls`
- tool result messages with role `tool` and `tool_call_id`

If the upstream rejects a tool-related field, the proxy should return a clear API error rather than silently dropping behavior.

## Data Model Changes

`codex_proxy.models` will be extended to represent the Responses items Codex uses for tool loops.

Add request-side item models:

- `FunctionCallItem`
  - `type = "function_call"`
  - `call_id`
  - `name`
  - `arguments`
- `FunctionCallOutputItem`
  - `type = "function_call_output"`
  - `call_id`
  - `output`

Update request model fields:

- add `tool_choice: str | dict[str, Any] | None`
- add `parallel_tool_calls: bool | None`

The request `input` union should accept mixed lists that may contain:

- conversation messages
- assistant tool-call history items
- function call outputs

Response-side output should support mixed output items:

- `message`
- `function_call`

The existing `output_text` field remains a plain text aggregation of assistant message text only.

## Request Conversion Design

### Input normalization

The converter will normalize the Responses input into a Chat Completions `messages` array.

Rules:

1. `instructions` remains the leading `system` message.
2. Plain string input becomes a single `user` message.
3. Standard Responses `message` items map to Chat messages as they do today.
4. Assistant-side `function_call` items become a Chat `assistant` message with a `tool_calls` array entry.
5. `function_call_output` items become Chat `tool` messages with:
   - `role = "tool"`
   - `tool_call_id = call_id`
   - `content = output` converted to string

### Tool request fields

The following request fields are forwarded to Chat Completions when present:

- `tools`
- `tool_choice`
- `parallel_tool_calls`

Tool normalization rules:

- Preserve valid OpenAI Chat-style function tools unchanged.
- Continue supporting the current simplified function tool shorthand by expanding it into full Chat `tools` entries.
- Ignore malformed tool objects only when they are clearly unusable and there are still valid tools remaining.
- If all provided tools are malformed, omit `tools` and let upstream behave as a normal text request.

### Mixed assistant history

When the request input contains both assistant text and function calls in sequence, the converter should preserve the order. The generated Chat history should reflect the actual interaction:

- assistant text as `assistant.content`
- assistant function calls as `assistant.tool_calls`
- tool results as `tool` messages

If a single Responses assistant history message contains text and tool calls in a shape the current proxy cannot represent directly, the converter should split it into multiple Chat messages to preserve semantics rather than merge unrelated content.

## Non-Streaming Response Conversion

The converter will inspect the first choice message and produce Responses output items in order.

Rules:

1. If the assistant message has non-empty text content, emit one `message` output item.
2. If the assistant message has `tool_calls`, emit one `function_call` output item per tool call.
3. Preserve call order from upstream.
4. `output_text` is the concatenation of emitted assistant text only.
5. Usage continues to map from Chat token fields into Responses usage fields.

Output item mapping for a tool call:

- `type = "function_call"`
- `id =` generated proxy item id
- `call_id = upstream tool call id`
- `name = tool_calls[n].function.name`
- `arguments = tool_calls[n].function.arguments`

If both text content and tool calls are present in the same upstream message, emit both item types in order: message first, then function calls. This preserves readable assistant text while still exposing the actionable function requests to Codex.

## Streaming Conversion Design

Streaming support will move from a single text accumulator to a small response state machine.

### State tracked per stream

- response id
- sequence number
- text message item state
- accumulated assistant text
- usage
- tool call states keyed by upstream `tool_call.index`

Each tool call state stores:

- generated Responses output item id
- upstream `call_id` or fallback generated id
- function name
- accumulated arguments string
- whether `response.output_item.added` has been sent
- whether `response.function_call_arguments.done` has been sent

### Text event flow

The current text event sequence is preserved for assistant text:

- `response.created`
- `response.output_item.added`
- `response.content_part.added`
- repeated `response.output_text.delta`
- `response.output_text.done`
- `response.content_part.done`
- `response.output_item.done`

These events are only emitted if text content actually appears.

### Tool event flow

For each tool call index:

1. On first delta for that tool call, emit `response.output_item.added` with:
   - `item.type = "function_call"`
   - `item.call_id`
   - `item.name`
   - `item.arguments = ""`
2. On every arguments delta, emit `response.function_call_arguments.delta`.
3. When the tool call finishes or the stream ends, emit:
   - `response.function_call_arguments.done`
   - `response.output_item.done`

If the upstream includes the function name before arguments, store it immediately so the added item is complete enough for clients. If the name arrives late, the proxy updates internal state and uses the final value in the done event.

### Stream completion

At stream end:

- finalize any open text item
- finalize any open tool call items in index order
- emit `response.completed`
- emit `[DONE]`

The final `response.completed.response.output` should contain the completed text message item if present and all completed function call items in stable order.

## Error Handling

- Upstream HTTP errors remain mapped into Responses-style error responses.
- Tool-related upstream validation failures should surface as-is through the existing API error handling path.
- If the proxy receives a request shape it does not yet support, return a 400-style validation error rather than silently corrupting the interaction.
- Streaming errors continue to produce an `error` event followed by `[DONE]`.

## Testing Plan

Add coverage in `tests/test_models.py`, `tests/test_converter.py`, and `tests/test_router.py`.

### Model tests

- request accepts `function_call_output`
- request accepts `tool_choice`
- request accepts `parallel_tool_calls`

### Converter request tests

- `function_call_output` becomes Chat `tool` message
- assistant `function_call` history becomes Chat `assistant.tool_calls`
- `tool_choice` and `parallel_tool_calls` are forwarded
- mixed text plus tool history preserves order

### Converter response tests

- Chat tool call response becomes Responses `function_call`
- response with text plus tool calls emits both item types
- `output_text` excludes function argument payloads

### Router streaming tests

- text-only stream remains unchanged
- single tool call stream emits added, argument deltas, done, completed
- multiple tool calls with different indexes remain ordered
- mixed text plus tool stream finalizes both item categories correctly

## Implementation Notes

- Most logic should stay in `converter.py` and a small helper module for tool-call state if needed.
- `tools.py` can become the home for request/stream helper functions if that keeps `converter.py` readable.
- The implementation should favor explicit helper methods over large nested conditionals because stream event handling is stateful and easy to regress.

## Risks

- Chat streaming payloads from Coding Plan may differ slightly from OpenAI's exact `delta.tool_calls` shape. The implementation should be defensive and tested against the observed payloads available to the project.
- Some upstream models may accept `tools` but reject specific `tool_choice` values. The proxy should not guess; it should pass the field through and let the upstream reject unsupported combinations.
- The Responses event schema is stricter than Chat streaming. Missing or misordered events can break Codex tool execution, so router tests are essential.

## Rollout

Ship this as a focused tool-calling compatibility change. Once stable, a second pass can add:

- `text.format` to upstream structured output conversion
- explicit `reasoning` output items
- broader built-in tool compatibility decisions beyond custom function tools
