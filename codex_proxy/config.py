"""Configuration management for Codex Proxy."""

import os
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass


class MissingRequiredSectionError(ConfigurationError):
    """Raised when a required configuration section is missing or empty."""
    pass


class MissingEnvironmentVariableError(ConfigurationError):
    """Raised when a required environment variable is not set."""
    pass


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str
    port: int


@dataclass
class CodingPlanConfig:
    """Coding Plan API configuration."""
    base_url: str
    api_key: str
    model: str
    timeout: int
    model_mapping: dict[str, str] = None  # Map request model names to actual model names

    def __post_init__(self):
        if self.model_mapping is None:
            self.model_mapping = {}

    def resolve_model(self, requested_model: str) -> str:
        """Resolve a requested model name to the actual model name.

        Args:
            requested_model: The model name from the request.

        Returns:
            The actual model name to use.
        """
        if requested_model in self.model_mapping:
            return self.model_mapping[requested_model]
        return requested_model or self.model


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    """Main configuration container."""
    server: ServerConfig
    coding_plan: CodingPlanConfig
    logging: LoggingConfig

    @classmethod
    def load(cls, path: str = "config.yaml", strict_env_vars: bool = False) -> "Config":
        """Load configuration from YAML file.

        Args:
            path: Path to configuration file.
            strict_env_vars: If True, raise error when env var is not set.
                           If False, log warning and use empty string.

        Returns:
            Config instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ConfigurationError: If YAML parsing fails or required sections are missing.
            MissingEnvironmentVariableError: If strict_env_vars=True and env var is not set.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Failed to parse YAML configuration file '{path}': {e}"
            ) from e

        if raw_config is None:
            raise ConfigurationError(
                f"Configuration file '{path}' is empty or contains only comments"
            )

        if not isinstance(raw_config, dict):
            raise ConfigurationError(
                f"Configuration file '{path}' must contain a YAML mapping, "
                f"got {type(raw_config).__name__}"
            )

        # Substitute environment variables
        try:
            raw_config = cls._substitute_env_vars(raw_config, strict_env_vars)
        except MissingEnvironmentVariableError:
            raise

        # Validate required sections
        required_sections = ["server", "coding_plan"]
        missing_sections = [s for s in required_sections if s not in raw_config or not raw_config[s]]
        if missing_sections:
            raise MissingRequiredSectionError(
                f"Missing or empty required configuration section(s): {', '.join(missing_sections)}. "
                f"Please ensure these sections are defined in '{path}'."
            )

        try:
            return cls(
                server=ServerConfig(**raw_config["server"]),
                coding_plan=CodingPlanConfig(**raw_config["coding_plan"]),
                logging=LoggingConfig(**raw_config.get("logging", {})),
            )
        except TypeError as e:
            missing_fields = str(e).split("missing")[1] if "missing" in str(e) else str(e)
            raise ConfigurationError(
                f"Invalid configuration: missing required field(s){missing_fields}"
            ) from e

    @staticmethod
    def _substitute_env_vars(obj: Any, strict: bool = False) -> Any:
        """Recursively substitute ${VAR} with environment variable values.

        Args:
            obj: Object to process (dict, list, or str).
            strict: If True, raise error when env var is not set.
                   If False, log warning and use empty string.

        Returns:
            Processed object with env vars substituted.

        Raises:
            MissingEnvironmentVariableError: If strict=True and env var is not set.
        """
        if isinstance(obj, dict):
            return {k: Config._substitute_env_vars(v, strict) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Config._substitute_env_vars(item, strict) for item in obj]
        elif isinstance(obj, str):
            pattern = r"\$\{([^}]+)\}"
            matches = re.findall(pattern, obj)
            for var_name in matches:
                var_value = os.environ.get(var_name)
                if var_value is None:
                    if strict:
                        raise MissingEnvironmentVariableError(
                            f"Environment variable '{var_name}' is not set but is required "
                            f"in configuration value '{obj}'"
                        )
                    else:
                        logger.warning(
                            "Environment variable '%s' is not set, replacing with empty string "
                            "in configuration value '%s'",
                            var_name,
                            obj
                        )
                        var_value = ""
                obj = obj.replace(f"${{{var_name}}}", var_value)
            return obj
        return obj