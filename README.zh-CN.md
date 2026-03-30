# Codex Proxy

将 OpenAI Codex CLI 的 Responses API 请求转换为阿里云通义编码助手 (Coding Plan) Chat Completions API 格式的代理服务，使 Codex CLI 能够对接通义编码助手后端。

## 快速导航

- [macOS 安装与使用](#macos)
- [Linux 安装与使用](#linux)
- [Windows 安装与使用](#windows)
- [配置说明](#配置说明)
- [架构概览](#架构概览)

## 前置条件

- Python >= 3.10
- 阿里云通义编码助手 API Key（通过环境变量 `CODING_PLAN_API_KEY` 设置）
- [Codex CLI](https://github.com/openai/codex)（需要使用代理的客户端）

---

## macOS

### 安装

```bash
# 克隆项目
git clone https://github.com/pane-zhi/codex-proxy.git
cd codex-proxy

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装（开发模式）
pip install -e ".[dev]"
```

### 配置

```bash
# 复制配置文件模板
cp config.example.yaml config.yaml

# 设置 API Key
export CODING_PLAN_API_KEY="你的API密钥"
```

### 启动服务

```bash
# 方式一：模块启动
python -m codex_proxy.main

# 方式二：命令行入口
codex-proxy

# 方式三：uvicorn 启动（自定义参数）
uvicorn codex_proxy.main:app --host 127.0.0.1 --port 8080
```

### 配合 Codex CLI 使用

```bash
# 将 Codex CLI 指向本地代理
export OPENAI_BASE_URL="http://127.0.0.1:8080"
codex
```

### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 单个测试文件
pytest tests/test_converter.py -v

# 单个测试用例
pytest tests/test_converter.py::TestConverterRequestConversion::test_convert_simple_string_input -v

# 带覆盖率
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

---

## Linux

### 安装

```bash
# 克隆项目
git clone https://github.com/pane-zhi/codex-proxy.git
cd codex-proxy

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装（开发模式）
pip install -e ".[dev]"
```

### 配置

```bash
# 复制配置文件模板
cp config.example.yaml config.yaml

# 设置 API Key
export CODING_PLAN_API_KEY="你的API密钥"

# 可选：写入 shell 配置持久化
echo 'export CODING_PLAN_API_KEY="你的API密钥"' >> ~/.bashrc
source ~/.bashrc
```

### 启动服务

```bash
# 方式一：模块启动
python -m codex_proxy.main

# 方式二：命令行入口
codex-proxy

# 方式三：后台运行
nohup codex-proxy > /dev/null 2>&1 &
```

### 配合 Codex CLI 使用

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8080"
codex
```

### 运行测试

```bash
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

---

## Windows

### 安装

```powershell
# 克隆项目
git clone https://github.com/pane-zhi/codex-proxy.git
cd codex-proxy

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装（开发模式）
pip install -e ".[dev]"
```

### 配置

```powershell
# 复制配置文件模板
copy config.example.yaml config.yaml

# 设置 API Key（当前会话）
$env:CODING_PLAN_API_KEY="你的API密钥"

# 可选：永久设置环境变量
[System.Environment]::SetEnvironmentVariable("CODING_PLAN_API_KEY", "你的API密钥", "User")
```

### 启动服务

```powershell
# 方式一：模块启动
python -m codex_proxy.main

# 方式二：命令行入口
codex-proxy
```

### 配合 Codex CLI 使用

```powershell
$env:OPENAI_BASE_URL="http://127.0.0.1:8080"
codex
```

### 运行测试

```powershell
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=codex_proxy --cov-report=html
```

---

## 配置说明

配置文件 `config.yaml` 支持 `${ENV_VAR}` 语法引用环境变量。完整示例：

```yaml
server:
  host: "127.0.0.1"
  port: 8080

coding_plan:
  base_url: "https://coding.dashscope.aliyuncs.com/v1"
  api_key: "${CODING_PLAN_API_KEY}"
  model: "qwen3.5-plus"
  timeout: 300
  model_mapping:
    # 将 Codex 使用的模型名映射为通义编码助手的模型名
    "gpt-5.4": "qwen3.5-plus"
    "gpt-5": "qwen3.5-plus"
    "gpt-4.1": "qwen3.5-plus"
    "o4-mini": "qwen3.5-plus"

logging:
  console_level: "INFO"
  file_level: "DEBUG"
  payload_max_chars: 4000
```

### 模型映射

`model_mapping` 将 Codex CLI 发送的模型名称映射为通义编码助手实际使用的模型。当请求中的模型名不在映射表中时，将直接透传给上游 API。

## 架构概览

```
Codex CLI 请求 (Responses API)
    │
    ▼
/v1/responses 端点
    │
    ├─ Converter.to_chat_completions_request()  ── 格式转换
    │
    ▼
CodingPlanClient.chat()  ── 转发至通义编码助手
    │
    ├─ Converter.to_responses_response()  ── 格式转换回 Responses API
    │
    ▼
Codex CLI 响应 (Responses API)
```

核心转换逻辑：

- `input` 字符串/列表 → `messages` 数组；`instructions` → system 消息
- `developer` 角色 → `system` 角色
- 上游 `reasoning_content` 合并到输出文本
- 工具调用 (`function_call` / `function_call_output`) 双向转换
- 流式响应生成完整的 SSE 事件序列（包括 `response.created`、文本增量、工具调用参数增量、`response.completed` 等）

## 健康检查

```bash
curl http://127.0.0.1:8080/health
# 返回: {"status": "ok"}
```

## 日志

- 控制台输出：精简摘要格式，带 ANSI 颜色（可通过 `NO_COLOR` 环境变量禁用）
- 文件日志：保存在项目根目录 `logs/` 下，按天轮转，保留 7 天

## 许可证

MIT
