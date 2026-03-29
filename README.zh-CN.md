# Codex Proxy 中文说明

> 本文档为中文说明文档，英文版请参见 `README.md`。

## 项目简介

Codex Proxy 是一个代理服务，用于将 OpenAI Codex 使用的 Responses API 适配到阿里云百炼 Coding Plan 使用的 Chat Completions API。

它的作用是作为中间适配层，让 Codex CLI 或其他依赖 Responses API 的工具，可以通过本代理与 Coding Plan 后端进行交互。

## 功能特性

- 将 OpenAI Responses API 请求转换为 Chat Completions API 请求
- 支持流式与非流式响应
- 支持函数 / 工具调用格式转换
- 支持配置文件中的环境变量替换
- 提供 `/health` 健康检查接口
- 提供控制台摘要日志与文件详细日志两类日志输出

## 环境要求

- Python 3.10 或更高版本

## 快速开始

1. 进入项目目录并安装依赖：

```bash
cd codex-proxy
pip install -e .
```

如果你需要开发依赖：

```bash
pip install -e ".[dev]"
```

2. 复制示例配置文件：

```bash
cp config.example.yaml config.yaml
```

3. 设置环境变量：

```bash
export CODING_PLAN_API_KEY="your-api-key-here"
```

4. 启动服务：

```bash
python -m codex_proxy.main
```

## 各系统使用方法

### Windows

推荐使用 PowerShell。

1. 进入项目目录并安装依赖：

```powershell
cd codex-proxy
pip install -e .
```

如果你需要开发依赖：

```powershell
pip install -e ".[dev]"
```

2. 复制配置文件：

```powershell
Copy-Item config.example.yaml config.yaml
```

3. 设置环境变量：

```powershell
$env:CODING_PLAN_API_KEY="your-api-key-here"
```

4. 启动服务：

```powershell
python -m codex_proxy.main
```

5. 运行测试：

```powershell
pytest tests/ -v
```

### macOS

推荐使用终端中的 `bash` 或 `zsh`。

1. 安装依赖：

```bash
cd codex-proxy
pip install -e .
```

如果你需要开发依赖：

```bash
pip install -e ".[dev]"
```

2. 复制配置文件：

```bash
cp config.example.yaml config.yaml
```

3. 设置环境变量：

```bash
export CODING_PLAN_API_KEY="your-api-key-here"
```

4. 启动服务：

```bash
python -m codex_proxy.main
```

5. 运行测试：

```bash
pytest tests/ -v
```

### Linux

推荐使用 `bash`。

1. 安装依赖：

```bash
cd codex-proxy
pip install -e .
```

如果你需要开发依赖：

```bash
pip install -e ".[dev]"
```

2. 复制配置文件：

```bash
cp config.example.yaml config.yaml
```

3. 设置环境变量：

```bash
export CODING_PLAN_API_KEY="your-api-key-here"
```

4. 启动服务：

```bash
python -m codex_proxy.main
```

5. 运行测试：

```bash
pytest tests/ -v
```

## 配置说明

1. 复制示例配置文件：

```bash
cp config.example.yaml config.yaml
```

2. 设置 `CODING_PLAN_API_KEY` 环境变量。

3. 根据需要修改 `config.yaml`。

### 配置项说明

| 分组 | 配置项 | 说明 | 默认值 |
|------|--------|------|--------|
| `server` | `host` | 服务监听地址 | `127.0.0.1` |
| `server` | `port` | 服务端口 | `8080` |
| `coding_plan` | `base_url` | Coding Plan API 基础地址 | `https://coding.dashscope.aliyuncs.com/v1` |
| `coding_plan` | `api_key` | API Key，支持 `${ENV_VAR}` 语法 | 必填 |
| `coding_plan` | `model` | 默认使用的模型名 | `qwen3.5-plus` |
| `coding_plan` | `timeout` | 请求超时时间（秒） | `300` |
| `logging` | `level` | 旧版统一日志级别回退值 | `INFO` |
| `logging` | `console_level` | 控制台摘要日志级别 | `INFO` |
| `logging` | `file_level` | 文件诊断日志级别 | `DEBUG` |
| `logging` | `payload_max_chars` | 日志中 payload 截断前保留的最大字符数 | `4000` |
| `logging` | `format` | 文件日志格式字符串 | 标准格式 |

## Codex 配置示例

你可以修改 `~/.codex/config.toml`，让 Codex 通过本代理访问后端：

```toml
base_url = "http://127.0.0.1:8080/v1"
model = "qwen-coder-plus"

[model_providers.coding_plan_proxy]
name = "coding_plan_proxy"
base_url = "http://127.0.0.1:8080/v1"
env_key = "CODING_PLAN_API_KEY"
wire_api = "responses"
```

## 日志说明

本代理会输出两类日志：

- 控制台日志：简洁的请求摘要日志，适合开发时快速观察
- 文件日志：详细诊断日志，默认写入 `logs/codex-proxy.log`

你可以通过共享的 `request_id` 将控制台日志与文件日志中的同一次请求对应起来。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | `GET` | 健康检查接口，返回 `{"status": "ok"}` |
| `/v1/responses` | `POST` | Responses API 主入口 |

## 测试方法

运行全部测试：

```bash
pytest tests/ -v
```

运行覆盖率测试：

```bash
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

## API 格式转换说明

### 请求转换

本代理会将 OpenAI Responses API 请求转换为 Chat Completions API 请求，主要包括：

- 将 `input` 转换为 `messages` 数组
- 将 `instructions` 转换为 system message
- 将历史 `function_call` 转换为 assistant `tool_calls`
- 将 `function_call_output` 转换为 Chat 的 `tool` message
- 将 `tools` 转换为 Chat `tools` 定义
- 在存在时透传 `tool_choice` 和 `parallel_tool_calls`
- 保留 `stream` 标志

### 响应转换

- 非流式响应：将 assistant `tool_calls` 转回 Responses `function_call` 项
- 非流式响应：同时保留文本消息与工具调用项
- 流式响应：将文本增量和工具调用参数增量转换为 Responses SSE 事件
- 流式工具调用完成时发出 `response.function_call_arguments.done` 和 `response.output_item.done`

## 错误处理

本代理会尽量保持错误输出友好且兼容：

- 将来自 Coding Plan 的 API 错误转换为 Responses API 风格错误
- 流式请求中的错误会在 `[DONE]` 之前作为错误事件发送
- 内部异常会返回 500，并附带描述性错误信息

## 许可证

MIT License
