# Chinese README Design

## Summary

Add a standalone Chinese documentation file named `README.zh-CN.md` for this repository.

The new document should be a complete Chinese user-facing guide rather than a short pointer page. It should preserve the existing English `README.md` and provide a parallel Chinese reading experience for users who prefer Chinese.

## Goals

- Create a standalone Chinese README without replacing or mixing into the English README
- Cover the same core project information as the existing English README
- Add practical usage instructions for Windows, macOS, and Linux
- Keep the structure aligned enough with the English README to make future maintenance manageable
- Prefer copy-paste-ready commands over abstract descriptions

## Non-Goals

- Rewriting the English `README.md`
- Adding deployment guides for Docker, systemd, Homebrew, WSL, or other platform variants not already documented by the project
- Changing application behavior or configuration format
- Writing separate platform-specific files beyond `README.zh-CN.md`

## Output File

- Create `README.zh-CN.md`

The file should begin with a short note that this is the Chinese documentation and that the English version remains available in `README.md`.

## Audience

The target reader is a Chinese-speaking developer who wants to:

- understand what the project does
- install dependencies
- configure the proxy
- run it locally
- connect Codex to it
- understand logs, tests, and request conversion behavior

The document should be practical and direct, not marketing-heavy.

## Content Strategy

The Chinese README should be complete enough that a reader does not need to open `README.md` for routine setup and usage.

It should still stay faithful to the actual repository state and avoid introducing unsupported setup paths.

## Proposed Structure

The document should use this chapter order:

1. 项目简介
2. 功能特性
3. 环境要求
4. 快速开始
5. 各系统使用方法
6. 配置说明
7. Codex 配置示例
8. 日志说明
9. API 接口
10. 测试方法
11. API 格式转换说明
12. 错误处理
13. 许可证

## System-Specific Coverage

The “各系统使用方法” section should be split into:

- Windows
- macOS
- Linux

Each system section should include practical commands for:

- entering the project directory
- installing dependencies
- copying `config.example.yaml` to `config.yaml`
- setting `CODING_PLAN_API_KEY`
- starting the server
- running tests

## Platform Command Rules

### Windows

Use PowerShell-style commands and examples.

Examples should match the project’s actual workflow, such as:

- `Copy-Item` for copying config
- `$env:CODING_PLAN_API_KEY="..."`
- Python and pip commands that are reasonable for PowerShell users

### macOS and Linux

Use `bash`/`zsh` style commands.

Examples should use standard shell syntax such as:

- `cp config.example.yaml config.yaml`
- `export CODING_PLAN_API_KEY="..."`

## Relationship to Existing README

The Chinese README should mirror the English README’s current factual content where appropriate, including:

- project purpose
- feature list
- Python requirement
- installation methods
- configuration table
- running methods
- Codex configuration example
- logging behavior
- testing commands
- request/response conversion behavior
- error handling summary

Where the Chinese README adds more detail, it should mainly be in:

- Chinese wording and explanations
- system-specific usage instructions
- localized command notes

## Accuracy Constraints

The document must remain grounded in current repository behavior:

- use the current package and script names
- use the current config fields, including logging fields
- use the current endpoints
- reflect current logging behavior after the recent logging improvements
- avoid promising support for tools or deployment modes not present in the repo

## Writing Style

- Clear, practical, and concise Chinese
- Prefer direct instructions over long explanation
- Commands should be easy to copy
- Preserve technical identifiers in English where appropriate, such as file names, env vars, endpoint paths, and config keys
- Keep terminology consistent across sections

## Verification Expectations

Before implementation is considered complete, the resulting `README.zh-CN.md` should be checked for:

- consistency with the existing `README.md`
- correctness of commands by platform style
- consistency with current config and logging behavior
- absence of unsupported setup claims

## Success Criteria

The work is successful when:

- `README.zh-CN.md` exists as a standalone Chinese document
- it covers the project end-to-end for Chinese-speaking users
- it includes Windows, macOS, and Linux usage instructions
- it stays aligned with the project’s real behavior and current configuration
- it does not require modifying the English README to remain useful
