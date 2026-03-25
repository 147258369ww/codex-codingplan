"""Configuration management for Codex Proxy."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


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
    def load(cls, path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file.

        Args:
            path: Path to configuration file.

        Returns:
            Config instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        # Substitute environment variables
        raw_config = cls._substitute_env_vars(raw_config)

        return cls(
            server=ServerConfig(**raw_config.get("server", {})),
            coding_plan=CodingPlanConfig(**raw_config.get("coding_plan", {})),
            logging=LoggingConfig(**raw_config.get("logging", {})),
        )

    @staticmethod
    def _substitute_env_vars(obj):
        """Recursively substitute ${VAR} with environment variable values."""
        if isinstance(obj, dict):
            return {k: Config._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Config._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            pattern = r"\$\{([^}]+)\}"
            matches = re.findall(pattern, obj)
            for var_name in matches:
                var_value = os.environ.get(var_name, "")
                obj = obj.replace(f"${{{var_name}}}", var_value)
            return obj
        return obj