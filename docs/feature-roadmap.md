# 功能扩展规划文档

> 本文档描述 Codex Proxy 需要新增的功能，以完整支持 OpenAI Responses API 规范。

---

## 缺失功能总览

| 功能 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| 工具调用完整流程 | P0 | 缺失 | `function_call` 输出 + `function_call_output` 输入 |
| `tool_choice` 参数 | P1 | 缺失 | 控制工具调用行为 |
| `parallel_tool_calls` 参数 | P1 | 缺失 | 并行工具调用 |
| 结构化输出 (`text.format`) | P2 | 缺失 | 替代 `response_format` |
| `reasoning` 输出类型 | P2 | 缺失 | 推理模型返回推理过程 |
| `reasoning` 参数 | P3 | 缺失 | 推理模型配置 |
| `store` 参数 | P4 | 缺失 | 响应存储控制 |
| 内置工具支持 | P4 | 缺失 | `web_search`, `file_search`, `code_interpreter` 等 |
| `include` 参数 | P4 | 缺失 | 请求额外字段 |
| `annotations` 字段 | P4 | 缺失 | 输出文本标注 |

---

## 一、工具调用完整支持

### 1.1 概述

当前实现仅将 `tools` 参数透传给上游 API，但缺少完整的工具调用流程：

```
请求 tools → 模型返回 function_call → 执行工具 → 返回 function_call_output → 继续对话
```

### 1.2 请求参数扩展

#### 1.2.1 `tool_choice` - 工具选择策略

| 值 | 说明 | Chat Completions 映射 |
|----|------|----------------------|
| `auto` | 自动决定是否调用工具（默认） | `tool_choice: "auto"` |
| `none` | 不调用任何工具 | `tool_choice: "none"` |
| `required` | 必须调用至少一个工具 | `tool_choice: "required"` |
| `{"type": "function", "function": {"name": "xxx"}}` | 强制调用指定工具 | `tool_choice: {"type": "function", "function": {"name": "xxx"}}` |

**实现位置**: `models.py` → `ResponsesRequest.tool_choice`

```python
tool_choice: Union[Literal["auto", "none", "required"], dict[str, Any]] | None = None
```

#### 1.2.2 `parallel_tool_calls` - 并行工具调用

| 值 | 说明 |
|----|------|
| `true` | 允许一次调用多个工具（默认） |
| `false` | 每次最多调用一个工具 |

**实现位置**: `models.py` → `ResponsesRequest.parallel_tool_calls`

```python
parallel_tool_calls: bool | None = None
```

### 1.3 输出类型扩展

#### 1.3.1 `FunctionCall` - 工具调用请求

当模型决定调用工具时，响应中的 `output` 数组会包含此类型：

```python
class FunctionCall(BaseModel):
    """工具调用请求"""

    type: Literal["function_call"] = "function_call"
    id: str                          # 调用唯一标识，如 "fc_123"
    call_id: str                     # 用于关联 function_call_output
    name: str                        # 工具名称
    arguments: str                   # JSON 格式的参数
```

**示例**:
```json
{
  "type": "function_call",
  "id": "fc_abc123",
  "call_id": "call_xyz789",
  "name": "get_weather",
  "arguments": "{\"location\": \"San Francisco\"}"
}
```

#### 1.3.2 `FunctionCallOutput` - 工具执行结果

客户端执行工具后，需要将结果作为 `input` 发送：

```python
class FunctionCallOutput(BaseModel):
    """工具执行结果"""

    type: Literal["function_call_output"] = "function_call_output"
    call_id: str                     # 对应的 function_call.call_id
    output: str                      # 工具执行结果（通常是 JSON 字符串）
```

**示例**:
```json
{
  "type": "function_call_output",
  "call_id": "call_xyz789",
  "output": "{\"temperature\": 68, \"condition\": \"Sunny\"}"
}
```

### 1.4 输入处理扩展

#### 1.4.1 `InputContent` 类型扩展

```python
# 当前
InputContent = Union[InputTextContent, InputImageContent, InputRefusalContent, OutputTextContent, str]

# 扩展后
InputContent = Union[
    InputTextContent,
    InputImageContent,
    InputRefusalContent,
    OutputTextContent,
    FunctionCall,           # 新增：历史工具调用
    FunctionCallOutput,     # 新增：历史工具结果
    str
]
```

### 1.5 转换逻辑扩展

#### 1.5.1 请求转换 (`converter.py`)

**Chat Completions 格式差异**:

| Responses API | Chat Completions |
|---------------|------------------|
| `input` 中含 `function_call` | `messages` 中 `role: "assistant", tool_calls: [...]` |
| `input` 中含 `function_call_output` | `messages` 中 `role: "tool", tool_call_id: "...", content: "..."` |

**转换伪代码**:

```python
def _convert_message(self, msg: Any) -> dict[str, Any]:
    # ... 现有逻辑 ...

    # 处理 function_call 类型
    if msg.get("type") == "function_call":
        return {
            "role": "assistant",
            "tool_calls": [{
                "id": msg["id"],
                "type": "function",
                "function": {
                    "name": msg["name"],
                    "arguments": msg["arguments"]
                }
            }]
        }

    # 处理 function_call_output 类型
    if msg.get("type") == "function_call_output":
        return {
            "role": "tool",
            "tool_call_id": msg["call_id"],
            "content": msg["output"]
        }

    # ... 其他类型处理 ...
```

#### 1.5.2 响应转换 (`converter.py`)

**非流式响应**:

```python
def to_responses_response(self, chat_response: dict) -> dict:
    output = []

    for choice in chat_response.get("choices", []):
        message = choice.get("message", {})

        # 处理普通文本
        if message.get("content"):
            output.append({
                "id": "msg_xxx",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": message["content"]}]
            })

        # 处理工具调用
        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            output.append({
                "type": "function_call",
                "id": tc["id"],
                "call_id": tc["id"],  # 或生成新的
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"]
            })

    return {"output": output, ...}
```

### 1.6 流式事件扩展

#### 1.6.1 新增事件类型

| 事件类型 | 说明 | 触发时机 |
|----------|------|----------|
| `response.function_call.added` | 工具调用开始 | 模型决定调用工具 |
| `response.function_call.arguments.delta` | 参数增量 | 流式输出工具参数 |
| `response.function_call.arguments.done` | 参数输出完成 | 工具参数输出完毕 |

#### 1.6.2 事件格式

```json
// response.function_call.added
{
  "type": "response.function_call.added",
  "item_id": "fc_abc123",
  "output_index": 0,
  "function_call": {
    "id": "fc_abc123",
    "call_id": "call_xyz789",
    "name": "get_weather"
  }
}

// response.function_call.arguments.delta
{
  "type": "response.function_call.arguments.delta",
  "item_id": "fc_abc123",
  "output_index": 0,
  "delta": "{\"loc"
}

// response.function_call.arguments.done
{
  "type": "response.function_call.arguments.done",
  "item_id": "fc_abc123",
  "output_index": 0,
  "arguments": "{\"location\": \"San Francisco\"}"
}
```

### 1.7 实现任务清单

- [ ] **models.py**: 添加 `tool_choice`, `parallel_tool_calls` 字段到 `ResponsesRequest`
- [ ] **models.py**: 添加 `FunctionCall`, `FunctionCallOutput` 模型
- [ ] **models.py**: 扩展 `InputContent` 联合类型
- [ ] **converter.py**: 实现 `function_call` → `tool_calls` 转换
- [ ] **converter.py**: 实现 `function_call_output` → `tool` message 转换
- [ ] **converter.py**: 响应中提取 `tool_calls` 转换为 `function_call` 输出
- [ ] **router.py**: 流式响应中处理 `tool_calls` delta
- [ ] **tests**: 添加工具调用相关测试用例

---

## 二、结构化输出支持

### 2.1 概述

Responses API 使用 `text.format` 替代 Chat Completions 的 `response_format`。

### 2.2 请求参数

```python
class TextFormat(BaseModel):
    """输出格式配置"""

    type: Literal["json_schema", "json_object"] = "json_object"
    json_schema: dict[str, Any] | None = None  # 当 type="json_schema" 时必填
    strict: bool = False


class TextConfig(BaseModel):
    """文本输出配置"""

    format: TextFormat | None = None


class ResponsesRequest(BaseModel):
    # ... 现有字段 ...

    text: TextConfig | None = None
```

### 2.3 格式对比

| Responses API | Chat Completions |
|---------------|------------------|
| `text: {format: {type: "json_object"}}` | `response_format: {type: "json_object"}` |
| `text: {format: {type: "json_schema", json_schema: {...}, strict: true}}` | `response_format: {type: "json_schema", json_schema: {...}, strict: true}` |

### 2.4 转换逻辑

```python
def to_chat_completions_request(self, req: ResponsesRequest, model: str) -> dict:
    request = {...}

    # 转换 text.format → response_format
    if req.text and req.text.format:
        request["response_format"] = req.text.format.model_dump(exclude_none=True)

    return request
```

### 2.5 实现任务清单

- [ ] **models.py**: 添加 `TextFormat`, `TextConfig` 模型
- [ ] **models.py**: 添加 `text` 字段到 `ResponsesRequest`
- [ ] **converter.py**: 实现 `text.format` → `response_format` 转换
- [ ] **tests**: 添加结构化输出测试用例

---

## 三、推理模型支持

### 3.1 概述

支持 OpenAI o1/o3/GPT-5 等推理模型的特殊参数和输出格式。

**重要**: 推理模型在响应中会返回 `reasoning` 类型的 Item，包含模型的推理过程。

### 3.2 输出类型扩展

#### 3.2.1 `ReasoningItem` - 推理过程输出

```python
class ReasoningItem(BaseModel):
    """推理过程输出"""

    id: str
    type: Literal["reasoning"] = "reasoning"
    content: list[dict[str, Any]] = []  # 推理内容片段
    summary: list[dict[str, Any]] = []  # 推理摘要
    status: Literal["in_progress", "completed"] = "completed"
```

**响应示例**:
```json
{
  "output": [
    {
      "id": "rs_68af4030baa48193b0b43b4c2a176a1a",
      "type": "reasoning",
      "content": [],
      "summary": []
    },
    {
      "id": "msg_68af40337e58819392e935fb404414d0",
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "实际回复内容..."
        }
      ]
    }
  ]
}
```

#### 3.2.2 `OutputMessage` 扩展

```python
class OutputMessage(BaseModel):
    """输出消息"""

    id: str
    type: Literal["message"] = "message"
    status: Literal["in_progress", "completed"] = "completed"
    role: Literal["assistant"] = "assistant"
    content: list[OutputContent]
```

### 3.3 请求参数

```python
class ReasoningEffort(BaseModel):
    """推理配置"""

    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    summary: Literal["detailed", "auto", "concise"] | None = None


class ResponsesRequest(BaseModel):
    # ... 现有字段 ...

    reasoning: ReasoningEffort | None = None
```

### 3.4 Chat Completions 映射

Chat Completions API 不直接支持 `reasoning` 参数和输出类型。

**处理策略**:
1. 请求端：透传 `reasoning.effort` 给支持的上游模型
2. 响应端：
   - 将 `reasoning_content`（如 DeepSeek R1）封装为 `reasoning` Item
   - 或忽略，仅在最终输出中保留文本内容

### 3.5 实现任务清单

- [ ] **models.py**: 添加 `ReasoningItem` 模型
- [ ] **models.py**: 添加 `ReasoningEffort` 模型
- [ ] **models.py**: 添加 `reasoning` 字段到 `ResponsesRequest`
- [ ] **models.py**: 更新 `OutputMessage` 添加 `status` 字段
- [ ] **models.py**: 更新 `ResponsesResponse.output` 支持 `ReasoningItem`
- [ ] **converter.py**: 处理 `reasoning_content` → `reasoning` Item 转换
- [ ] **converter.py**: 透传 `reasoning` 参数（如果上游支持）
- [ ] **tests**: 添加推理配置测试用例

---

## 四、内置工具支持

### 4.1 概述

Responses API 原生支持 OpenAI 内置工具，这些工具在 Chat Completions API 中不可用或需要自行实现。

### 4.2 内置工具列表

| 工具类型 | 说明 | Chat Completions |
|----------|------|------------------|
| `web_search` | 网络搜索 | 不支持 |
| `file_search` | 文件检索 | 不支持 |
| `computer_use` | 电脑操作 | 不支持 |
| `code_interpreter` | 代码执行 | 不支持 |
| `image_generation` | 图像生成 | 不支持 |
| `local_shell` | 本地 Shell | 不支持 |
| `mcp` | 远程 MCP 服务器 | 不支持 |

### 4.3 使用方式

```json
{
  "model": "gpt-5",
  "input": "What is the current president of France?",
  "tools": [{"type": "web_search"}]
}
```

### 4.4 实现策略

由于 Coding Plan API 不支持这些内置工具，有两种处理方式：

1. **忽略内置工具**: 过滤掉 `web_search` 等内置工具类型，只保留 `function` 类型
2. **返回错误**: 检测到内置工具时返回不支持的错误

**推荐**: 方案 1，静默忽略以保持兼容性。

```python
# 在 converter.py 中过滤内置工具
BUILTIN_TOOLS = {"web_search", "file_search", "computer_use", "code_interpreter", "image_generation", "local_shell", "mcp"}

def filter_tools(tools: list[dict]) -> list[dict]:
    return [t for t in tools if t.get("type") == "function" and t.get("type") not in BUILTIN_TOOLS]
```

---

## 五、其他参数支持

### 4.1 `store` - 响应存储

```python
store: bool | None = None  # 默认 true
```

用于控制是否存储响应以供后续检索。当前 Codex Proxy 不实现存储功能，可忽略或透传。

### 4.2 `allowed_tools` - 工具白名单

```python
allowed_tools: list[str] | None = None
```

限制本次请求可用的工具子集。

**Chat Completions 无直接对应**，需在转换时过滤 `tools`。

### 4.3 `include` - 额外字段

```python
include: list[str] | None = None  # 如 ["file_search_call.results"]
```

用于请求额外字段。当前实现不涉及这些功能。

---

## 六、实现优先级

| 优先级 | 功能 | 原因 |
|--------|------|------|
| P0 | 工具调用完整流程 | Codex CLI 核心功能，无此功能无法正常工作 |
| P1 | `tool_choice`, `parallel_tool_calls` | 工具调用必需参数 |
| P2 | 结构化输出 | 常用功能，影响范围小 |
| P3 | 推理模型支持 | 仅特定模型需要 |
| P4 | 其他参数 | 可选功能 |

---

## 七、测试计划

### 6.1 工具调用测试

```python
def test_function_call_in_input():
    """测试 input 中包含 function_call 的转换"""
    pass

def test_function_call_output_in_input():
    """测试 input 中包含 function_call_output 的转换"""
    pass

def test_response_with_tool_calls():
    """测试响应中包含 tool_calls 的转换"""
    pass

def test_streaming_function_call():
    """测试流式工具调用事件"""
    pass

def test_tool_choice_parameters():
    """测试 tool_choice 参数转换"""
    pass

def test_parallel_tool_calls():
    """测试 parallel_tool_calls 参数"""
    pass
```

### 6.2 结构化输出测试

```python
def test_json_object_format():
    """测试 json_object 格式转换"""
    pass

def test_json_schema_format():
    """测试 json_schema 格式转换"""
    pass

def test_strict_mode():
    """测试 strict 模式"""
    pass
```

### 6.3 推理模型测试

```python
def test_reasoning_item_in_output():
    """测试响应中包含 reasoning 类型的 output"""
    pass

def test_reasoning_content_conversion():
    """测试 reasoning_content 转换为 reasoning Item"""
    pass

def test_reasoning_effort_parameter():
    """测试 reasoning.effort 参数透传"""
    pass
```

### 6.4 内置工具测试

```python
def test_builtin_tools_filtered():
    """测试内置工具被正确过滤"""
    pass

def test_mixed_tools():
    """测试混合工具（function + 内置）的处理"""
    pass
```

---

## 八、兼容性说明

### 8.1 上游 API 兼容性

| 功能 | Coding Plan API | 备注 |
|------|-----------------|------|
| `tools` | 支持 | 已实现 |
| `tool_choice` | 部分支持 | 需确认具体格式 |
| `tool_calls` 响应 | 部分支持 | 需确认返回格式 |
| `response_format` | 支持 | 已实现 |
| `reasoning` 参数 | 不支持 | 可能需要忽略 |
| `reasoning_content` | 部分支持 | qwen3.5-plus 等模型支持 |
| 内置工具 (`web_search` 等) | 不支持 | 需过滤掉 |
| `text.format` | 不支持 | 转换为 `response_format` |

### 8.2 向后兼容

所有新增字段均为可选（`| None = None`），不影响现有请求格式。

---

## 九、参考资料

- [OpenAI Responses API - Vercel](https://vercel.com/docs/ai-gateway/sdks-and-apis/responses)
- [Migrate to the Responses API - OpenAI](https://developers.openai.com/api/docs/guides/migrate-to-responses/)
- [Structured model outputs - OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs/)
- [Function calling guide - OpenAI](https://platform.openai.com/docs/guides/function-calling)