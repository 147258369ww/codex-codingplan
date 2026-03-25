# codex-proxy/tests/test_config.py
"""Tests for configuration module."""

import pytest

from codex_proxy.config import (
    Config,
    ServerConfig,
    CodingPlanConfig,
    ConfigurationError,
    MissingRequiredSectionError,
    MissingEnvironmentVariableError,
)


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


# ==================== Error Scenario Tests ====================


def test_missing_required_section_server(tmp_path):
    """Test error when server section is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
  model: "test-model"
  timeout: 120
""")

    with pytest.raises(MissingRequiredSectionError) as exc_info:
        Config.load(str(config_file))

    assert "server" in str(exc_info.value)
    assert "Missing or empty required configuration section" in str(exc_info.value)


def test_missing_required_section_coding_plan(tmp_path):
    """Test error when coding_plan section is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  port: 9000
""")

    with pytest.raises(MissingRequiredSectionError) as exc_info:
        Config.load(str(config_file))

    assert "coding_plan" in str(exc_info.value)


def test_empty_required_section(tmp_path):
    """Test error when a required section is empty."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  port: 9000

coding_plan:
""")

    with pytest.raises(MissingRequiredSectionError) as exc_info:
        Config.load(str(config_file))

    assert "coding_plan" in str(exc_info.value)


def test_malformed_yaml(tmp_path):
    """Test error handling for malformed YAML."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  - invalid yaml structure
coding_plan:
  base_url: "test"
""")

    with pytest.raises(ConfigurationError) as exc_info:
        Config.load(str(config_file))

    assert "Failed to parse YAML" in str(exc_info.value)


def test_empty_yaml_file(tmp_path):
    """Test error when YAML file is empty."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")

    with pytest.raises(ConfigurationError) as exc_info:
        Config.load(str(config_file))

    assert "empty" in str(exc_info.value).lower()


def test_yaml_with_only_comments(tmp_path):
    """Test error when YAML file contains only comments."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
# This is a comment
# Another comment
""")

    with pytest.raises(ConfigurationError) as exc_info:
        Config.load(str(config_file))

    assert "empty" in str(exc_info.value).lower()


def test_yaml_not_a_mapping(tmp_path):
    """Test error when YAML content is not a mapping/dict."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
- item1
- item2
- item3
""")

    with pytest.raises(ConfigurationError) as exc_info:
        Config.load(str(config_file))

    assert "must contain a YAML mapping" in str(exc_info.value)


def test_missing_required_field_in_section(tmp_path):
    """Test error when a required field is missing from a section."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  # missing 'port' field

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
  model: "test-model"
  timeout: 120
""")

    with pytest.raises(ConfigurationError) as exc_info:
        Config.load(str(config_file))

    assert "missing required field" in str(exc_info.value).lower()


def test_missing_env_var_strict_mode(tmp_path, monkeypatch):
    """Test error in strict mode when env var is not set."""
    # Ensure the env var is not set
    monkeypatch.delenv("MISSING_API_KEY", raising=False)

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "127.0.0.1"
  port: 8080

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "${MISSING_API_KEY}"
  model: "test-model"
  timeout: 300
""")

    with pytest.raises(MissingEnvironmentVariableError) as exc_info:
        Config.load(str(config_file), strict_env_vars=True)

    assert "MISSING_API_KEY" in str(exc_info.value)
    assert "not set" in str(exc_info.value)


def test_missing_env_var_non_strict_mode_logs_warning(tmp_path, monkeypatch, caplog):
    """Test that missing env var logs warning in non-strict mode."""
    # Ensure the env var is not set
    monkeypatch.delenv("ANOTHER_MISSING_KEY", raising=False)

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "127.0.0.1"
  port: 8080

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "${ANOTHER_MISSING_KEY}"
  model: "test-model"
  timeout: 300
""")

    import logging
    with caplog.at_level(logging.WARNING):
        config = Config.load(str(config_file), strict_env_vars=False)

    # Should not raise, but should log warning
    assert config.coding_plan.api_key == ""

    # Check warning was logged
    assert any(
        "ANOTHER_MISSING_KEY" in record.message and "not set" in record.message
        for record in caplog.records
    ), f"Expected warning log not found. Got: {[r.message for r in caplog.records]}"


def test_missing_env_var_multiple_occurrences(tmp_path, monkeypatch):
    """Test error when multiple env vars are missing in strict mode."""
    monkeypatch.delenv("VAR1", raising=False)
    monkeypatch.delenv("VAR2", raising=False)

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "127.0.0.1"
  port: 8080

coding_plan:
  base_url: "${VAR1}"
  api_key: "${VAR2}"
  model: "test-model"
  timeout: 300
""")

    with pytest.raises(MissingEnvironmentVariableError) as exc_info:
        Config.load(str(config_file), strict_env_vars=True)

    # Should fail on the first missing var
    assert "VAR1" in str(exc_info.value)


def test_config_with_logging_defaults(tmp_path):
    """Test that logging section uses defaults when not specified."""
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
""")

    config = Config.load(str(config_file))

    assert config.logging.level == "INFO"
    assert "%(asctime)s" in config.logging.format