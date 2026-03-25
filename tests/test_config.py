# codex-proxy/tests/test_config.py
"""Tests for configuration module."""

import pytest

from codex_proxy.config import Config, ServerConfig, CodingPlanConfig


def test_load_config_from_file(tmp_path):
    """Test loading config from YAML file."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  port: 9000

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
  model: "test-model"
  timeout: 120

logging:
  level: "DEBUG"
""")

    config = Config.load(str(config_file))

    assert config.server.host == "0.0.0.0"
    assert config.server.port == 9000
    assert config.coding_plan.base_url == "https://api.example.com/v1"
    assert config.coding_plan.api_key == "test-key"
    assert config.coding_plan.model == "test-model"
    assert config.coding_plan.timeout == 120


def test_load_config_with_env_var(tmp_path, monkeypatch):
    """Test config with environment variable substitution."""
    monkeypatch.setenv("TEST_API_KEY", "env-secret-key")

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "127.0.0.1"
  port: 8080

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "${TEST_API_KEY}"
  model: "test-model"
  timeout: 300
""")

    config = Config.load(str(config_file))
    assert config.coding_plan.api_key == "env-secret-key"


def test_load_config_file_not_found():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        Config.load("/nonexistent/config.yaml")