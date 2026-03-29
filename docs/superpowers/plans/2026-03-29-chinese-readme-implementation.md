# Chinese README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `README.zh-CN.md` that gives Chinese-speaking users a complete, practical guide to installing, configuring, running, and understanding this project across Windows, macOS, and Linux.

**Architecture:** Keep the English `README.md` unchanged and create a parallel Chinese document with a closely aligned structure. Reuse the current repository facts, config fields, commands, endpoints, and logging behavior, then add a dedicated cross-platform usage section with system-appropriate command examples.

**Tech Stack:** Markdown, existing project docs, Python project commands, PowerShell, bash/zsh

---

### Task 1: Create the standalone Chinese README

**Files:**
- Create: `README.zh-CN.md`
- Reference: `README.md`

- [ ] **Step 1: Draft the Chinese README with the approved chapter structure**

Create `README.zh-CN.md` with this content structure and concrete headings:

```markdown
# Codex Proxy 中文说明

> 本文档为中文说明文档，英文版请参见 `README.md`。

## 项目简介
## 功能特性
## 环境要求
## 快速开始
## 各系统使用方法
### Windows
### macOS
### Linux
## 配置说明
## Codex 配置示例
## 日志说明
## API 接口
## 测试方法
## API 格式转换说明
### 请求转换
### 响应转换
## 错误处理
## 许可证
```

- [ ] **Step 2: Fill in the shared project sections from the current English README**

Translate and adapt the factual content from `README.md` into concise Chinese for these sections:

```markdown
## 项目简介

Codex Proxy 是一个代理服务，用于将 OpenAI Codex 使用的 Responses API 适配到阿里云百炼 Coding Plan 使用的 Chat Completions API。

## 功能特性

- 将 Responses API 请求转换为 Chat Completions API 请求
- 支持流式与非流式响应
- 支持函数 / 工具调用格式转换
- 支持配置中的环境变量替换
- 提供 `/health` 健康检查接口

## 环境要求

- Python 3.10 或更高版本
```

- [ ] **Step 3: Add the quick start section with copy-paste-ready commands**

Write the quick start section with concrete commands:

```markdown
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
```

- [ ] **Step 4: Verify the new README file exists and contains all required headings**

Run: `rg -n "^## |^### " README.zh-CN.md`
Expected: output contains all approved sections, including `Windows` / `macOS` / `Linux`.

- [ ] **Step 5: Commit**

```bash
git add README.zh-CN.md
git commit -m "docs: add chinese readme"
```

### Task 2: Add system-specific usage instructions and consistency verification

**Files:**
- Modify: `README.zh-CN.md`
- Reference: `README.md`
- Reference: `config.example.yaml`

- [ ] **Step 1: Add Windows usage instructions with PowerShell commands**

Expand the `Windows` section in `README.zh-CN.md` with concrete PowerShell examples:

```markdown
### Windows

推荐使用 PowerShell：

```powershell
cd codex-proxy
pip install -e .
Copy-Item config.example.yaml config.yaml
$env:CODING_PLAN_API_KEY="your-api-key-here"
python -m codex_proxy.main
```

运行测试：

```powershell
pytest tests/ -v
```
```

- [ ] **Step 2: Add macOS and Linux usage instructions with shell commands**

Expand the `macOS` and `Linux` sections with concrete shell examples:

```markdown
### macOS

```bash
cd codex-proxy
pip install -e .
cp config.example.yaml config.yaml
export CODING_PLAN_API_KEY="your-api-key-here"
python -m codex_proxy.main
```

```bash
pytest tests/ -v
```

### Linux

```bash
cd codex-proxy
pip install -e .
cp config.example.yaml config.yaml
export CODING_PLAN_API_KEY="your-api-key-here"
python -m codex_proxy.main
```

```bash
pytest tests/ -v
```
```

- [ ] **Step 3: Add the remaining Chinese sections so the file is self-sufficient**

Ensure `README.zh-CN.md` includes these concrete sections adapted from current repo behavior:

```markdown
## 配置说明
- 说明 `server`、`coding_plan`、`logging` 配置项
- 保留当前日志字段：`level`、`console_level`、`file_level`、`payload_max_chars`、`format`

## Codex 配置示例
- 提供与英文 README 对应的 `~/.codex/config.toml` 示例

## 日志说明
- 说明控制台输出为摘要日志
- 说明 `logs/codex-proxy.log` 为详细诊断日志
- 说明可通过共享的 `request_id` 对照两类日志

## API 接口
- `/health`
- `/v1/responses`

## 测试方法
- `pytest tests/ -v`
- `pytest tests/ -v --cov=codex_proxy --cov-report=html`

## API 格式转换说明
- 请求转换
- 响应转换

## 错误处理
- 上游 API 错误转换
- 流式错误事件
- 内部错误返回
```

- [ ] **Step 4: Verify the Chinese README stays consistent with the current repository**

Run these checks:

Run: `rg -n "console_level|file_level|payload_max_chars|/health|/v1/responses|CODING_PLAN_API_KEY" README.zh-CN.md`
Expected: output includes current config keys, endpoints, and env var names.

Run: `sed -n '1,260p' README.zh-CN.md`
Expected: the document is complete Chinese content, contains the platform sections, and does not claim unsupported deployment modes like Docker or systemd.

- [ ] **Step 5: Commit**

```bash
git add README.zh-CN.md
git commit -m "docs: complete chinese usage guide"
```
