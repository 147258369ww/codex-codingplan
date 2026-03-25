"""API format converter between Responses API and Chat Completions API."""

import time
import uuid
from typing import Any

from codex_proxy.models import ResponsesRequest


class Converter:
    """Converts between Responses API and Chat Completions API formats."""

    def to_chat_completions_request(
        self,
        responses_request: ResponsesRequest,
        resolved_model: str,
    ) -> dict[str, Any]:
        """Convert Responses API request to Chat Completions request.

        Args:
            responses_request: The Responses API request.
            resolved_model: The resolved model name to use (after model mapping).

        Returns:
            Chat Completions compatible request dict.
        """
        messages = self._convert_input(
            responses_request.input,
            responses_request.instructions,
        )

        # Build request - use resolved_model directly (already mapped via config)
        request: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": responses_request.stream,
        }

        # Add optional fields
        if responses_request.max_output_tokens is not None:
            request["max_tokens"] = responses_request.max_output_tokens

        if responses_request.temperature is not None:
            request["temperature"] = responses_request.temperature

        if responses_request.top_p is not None:
            request["top_p"] = responses_request.top_p

        if responses_request.tools is not None:
            # Filter tools to only include valid function tools
            # Chat Completions API requires type="function" with a "function" object
            valid_tools = []
            for tool in responses_request.tools:
                if isinstance(tool, dict):
                    if tool.get("type") == "function" and "function" in tool:
                        valid_tools.append(tool)
                    elif tool.get("type") == "function" and "name" in tool:
                        # Convert simplified format to full format
                        valid_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool.get("description", ""),
                                "parameters": tool.get("parameters", {}),
                            }
                        })
            if valid_tools:
                request["tools"] = valid_tools

        return request

    def _convert_input(
        self,
        input_value: str | list,
        instructions: str | None,
    ) -> list[dict[str, str]]:
        """Convert input field to messages array.

        Args:
            input_value: String or message list.
            instructions: Optional system instructions.

        Returns:
            List of message dicts.
        """
        messages = []

        # Add instructions as system message first
        if instructions:
            messages.append({"role": "system", "content": instructions})

        # Handle input
        if isinstance(input_value, str):
            messages.append({"role": "user", "content": input_value})
        else:
            # input_value is a list of messages
            for msg in input_value:
                converted = self._convert_message(msg)
                messages.append(converted)

        return messages

    def _convert_message(self, msg: Any) -> dict[str, Any]:
        """Convert a single message to Chat Completions format.

        Args:
            msg: Message object (InputMessage, Message, or dict).

        Returns:
            Chat Completions message dict.
        """
        if hasattr(msg, "model_dump"):
            data = msg.model_dump()
        elif isinstance(msg, dict):
            data = msg
        else:
            return {"role": "user", "content": str(msg)}

        role = data.get("role", "user")
        content = data.get("content")

        # Map 'developer' role to 'system'
        if role == "developer":
            role = "system"

        # Convert content
        if isinstance(content, str):
            return {"role": role, "content": content}
        elif isinstance(content, list):
            # Extract text from content items
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "input_text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                elif isinstance(item, str):
                    text_parts.append(item)
            return {"role": role, "content": "\n".join(text_parts)}
        else:
            return {"role": role, "content": str(content) if content else ""}

    def to_responses_response(
        self,
        chat_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert Chat Completions response to Responses API format.

        Args:
            chat_response: Chat Completions API response.

        Returns:
            Responses API compatible response dict.
        """
        # Generate response ID
        chat_id = chat_response.get("id", "")
        if chat_id.startswith("chatcmpl-"):
            response_id = "resp_" + chat_id[9:]  # Remove "chatcmpl-" prefix
        else:
            response_id = "resp_" + str(uuid.uuid4())[:8]

        # Extract content with defensive check for empty choices
        choices = chat_response.get("choices", [])
        content_text = ""
        if choices:
            choice = choices[0]
            if "message" in choice:
                content_text = choice["message"].get("content", "")

        # Build output message
        output_message = {
            "id": "msg_" + str(uuid.uuid4())[:8],
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": content_text,
                }
            ],
        }

        # Extract usage
        usage = chat_response.get("usage", {})

        return {
            "id": response_id,
            "object": "response",
            "created_at": time.time(),
            "status": "completed",
            "model": chat_response.get("model", ""),
            "output": [output_message],
            "output_text": content_text,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    def to_responses_stream_event(
        self,
        chat_event: dict[str, Any],
        response_id: str,
        model: str,
    ) -> dict[str, Any] | None:
        """Convert Chat Completions stream event to Responses API event.

        Args:
            chat_event: Chat Completions SSE event data.
            response_id: The response ID for this stream.
            model: The model name.

        Returns:
            Responses API event dict, or None if event should be skipped.
        """
        choices = chat_event.get("choices", [])
        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        # Skip role-only events
        if "role" in delta and "content" not in delta and "reasoning_content" not in delta and not finish_reason:
            return None

        # Handle finish
        if finish_reason:
            return {
                "type": "response.output_text.done",
                "output_index": 0,
            }

        # Handle content delta - check both "content" and "reasoning_content"
        content = delta.get("content")
        # Some models (like qwen3.5-plus) use reasoning_content for thinking tokens
        reasoning_content = delta.get("reasoning_content")

        if content:
            return {
                "type": "response.output_text.delta",
                "delta": content,
                "output_index": 0,
            }
        elif reasoning_content:
            # Include reasoning content in the output
            return {
                "type": "response.output_text.delta",
                "delta": reasoning_content,
                "output_index": 0,
            }

        return None

    def create_completed_event(
        self,
        response_id: str,
        model: str,
        full_content: str,
        usage: dict[str, int],
    ) -> dict[str, Any]:
        """Create a response.completed event.

        Args:
            response_id: The response ID.
            model: The model name.
            full_content: The complete response content.
            usage: Token usage dict.

        Returns:
            response.completed event dict.
        """
        # Build output message
        output_message = {
            "id": "msg_" + str(uuid.uuid4())[:8],
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": full_content,
                }
            ],
        }

        response = {
            "id": response_id,
            "object": "response",
            "created_at": time.time(),
            "status": "completed",
            "model": model,
            "output": [output_message],
            "output_text": full_content,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

        return {
            "type": "response.completed",
            "response": response,
        }