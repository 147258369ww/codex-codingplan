"""Tool calling support for Responses API."""

from dataclasses import dataclass
import uuid


@dataclass
class ToolCallState:
    """Streaming state for one upstream tool call index."""

    index: int
    item_id: str
    call_id: str
    name: str
    arguments: str = ""
    added_sent: bool = False
    done_sent: bool = False


def get_or_create_tool_call_state(
    tool_call_states: dict[int, ToolCallState],
    tool_call: dict,
) -> ToolCallState:
    """Return the state object for a tool call delta, creating one if needed."""
    index = tool_call.get("index", 0)
    function = tool_call.get("function") or {}

    state = tool_call_states.get(index)
    if state is None:
        state = ToolCallState(
            index=index,
            item_id="fc_" + str(uuid.uuid4())[:8],
            call_id=tool_call.get("id") or "call_" + str(uuid.uuid4())[:8],
            name=function.get("name", ""),
        )
        tool_call_states[index] = state
        return state

    if tool_call.get("id"):
        state.call_id = tool_call["id"]
    if function.get("name"):
        state.name = function["name"]
    return state


def build_function_call_item(state: ToolCallState) -> dict:
    """Build a Responses function_call output item from streaming state."""
    return {
        "id": state.item_id,
        "type": "function_call",
        "call_id": state.call_id,
        "name": state.name,
        "arguments": state.arguments,
    }
