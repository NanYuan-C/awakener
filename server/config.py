"""
Awakener - Configuration Manager
=================================
Handles loading and saving of application configuration from two sources:

1. config.yaml  - Non-sensitive settings (model, interval, paths, etc.)
2. .env         - Sensitive secrets (API keys)

The config manager provides a unified interface to read and write both files,
used by the REST API to allow web-based configuration management.

Usage:
    config = ConfigManager(project_dir="/path/to/awakener")
    settings = config.load()           # Returns merged config dict
    config.update({"agent": ...})      # Updates config.yaml
    config.set_api_key("DEEPSEEK_API_KEY", "sk-xxx")  # Updates .env
"""

import os
import yaml
from dotenv import dotenv_values
from typing import Any


# Default configuration values used when config.yaml is missing or incomplete.
# These ensure the application always has sensible defaults.
DEFAULTS = {
    "web": {
        "port": 8080,
        "host": "0.0.0.0",
    },
    "agent": {
        "home": "/home/agent",
        "model": "deepseek/deepseek-chat",
        "interval": 60,
        "max_tool_calls": 20,
        "shell_timeout": 30,
        "max_output_chars": 4000,
    },
}

# List of recognized API key environment variable names.
# These are the keys that can be managed through the web console.
KNOWN_API_KEYS = [
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
]


class ConfigManager:
    """
    Unified configuration manager for Awakener.

    Reads from config.yaml (settings) and .env (secrets), provides methods
    to update both through the web management console.

    Attributes:
        project_dir: Root directory of the Awakener project.
        config_path: Full path to config.yaml.
        env_path:    Full path to .env file.
    """

    def __init__(self, project_dir: str):
        """
        Initialize the config manager.

        Args:
            project_dir: Absolute path to the Awakener project root directory.
        """
        self.project_dir = project_dir
        self.config_path = os.path.join(project_dir, "config.yaml")
        self.env_path = os.path.join(project_dir, ".env")

    def load(self) -> dict:
        """
        Load and merge configuration from config.yaml with defaults.

        Missing values are filled from DEFAULTS. This ensures the application
        always has a complete configuration even if the YAML file is partial.

        Returns:
            A dictionary containing the full configuration.
        """
        config = _deep_copy(DEFAULTS)

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                _deep_merge(config, user_config)
            except (yaml.YAMLError, OSError) as e:
                # If config file is corrupted, fall back to defaults
                # and log the error (caller should handle this)
                config["_config_error"] = str(e)

        return config

    def save(self, config: dict) -> None:
        """
        Save configuration back to config.yaml.

        Saves the 'web', 'agent', and 'model' sections. Internal keys
        (prefixed with '_') are stripped before writing.

        Args:
            config: Configuration dictionary to save.
        """
        # Filter out internal keys, keep only known sections
        clean = {}
        for section in ["web", "agent", "model"]:
            if section in config:
                clean[section] = config[section]

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                clean,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def update(self, updates: dict) -> dict:
        """
        Partially update configuration and save.

        Merges the provided updates into the current config and writes
        the result back to config.yaml.

        Args:
            updates: Dictionary of settings to update (can be partial).

        Returns:
            The full updated configuration.
        """
        config = self.load()
        _deep_merge(config, updates)
        self.save(config)
        return config

    # -- API Key Management ---------------------------------------------------

    def get_api_keys(self) -> dict:
        """
        Load API keys from .env file.

        Returns a dictionary of key names to masked values. Only the first 6
        and last 4 characters are shown, the rest replaced with asterisks.
        Includes both known keys (KNOWN_API_KEYS) and any custom keys found
        in the .env file that end with '_API_KEY' or '_KEY'.

        Returns:
            Dict with 'keys' mapping key names to their masked values.
            Example: {"keys": {"DEEPSEEK_API_KEY": "sk-41****270b", ...}}
        """
        env_values = dotenv_values(self.env_path) if os.path.exists(self.env_path) else {}

        result = {}
        # Include all known keys
        for key_name in KNOWN_API_KEYS:
            value = env_values.get(key_name, "")
            result[key_name] = _mask_key(value) if value else ""

        # Include any additional custom keys from .env
        for key_name, value in env_values.items():
            if key_name not in result and (
                key_name.endswith("_API_KEY") or key_name.endswith("_KEY")
            ):
                result[key_name] = _mask_key(value) if value else ""

        return {"keys": result}

    def has_any_api_key(self) -> bool:
        """
        Check if at least one API key is configured.

        Returns:
            True if any API key has a non-empty value in .env.
        """
        env_values = dotenv_values(self.env_path) if os.path.exists(self.env_path) else {}
        return any(env_values.get(k) for k in KNOWN_API_KEYS)

    def set_api_key(self, key_name: str, value: str) -> None:
        """
        Set or update a single API key in the .env file.

        If the key already exists, its value is replaced.
        If it doesn't exist, it's appended to the file.

        Args:
            key_name: Environment variable name (e.g., "DEEPSEEK_API_KEY").
            value:    The API key value to store.
        """
        self._write_env_key(key_name, value)

    def set_api_keys(self, keys: dict[str, str]) -> None:
        """
        Set multiple API keys at once.
        Accepts both known and custom key names (any string ending with
        _API_KEY or _KEY, or any key from KNOWN_API_KEYS).

        Args:
            keys: Dict mapping key names to values.
        """
        for key_name, value in keys.items():
            if value:
                self._write_env_key(key_name, value)

    def delete_api_key(self, key_name: str) -> None:
        """
        Remove a single API key from the .env file.

        Args:
            key_name: Environment variable name to remove.

        Raises:
            KeyError: If the key is not found in the .env file.
        """
        if not os.path.exists(self.env_path):
            raise KeyError(f"API key '{key_name}' not found")

        with open(self.env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith(f"{key_name}="):
                found = True
            else:
                new_lines.append(line)

        if not found:
            raise KeyError(f"API key '{key_name}' not found")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _write_env_key(self, key_name: str, value: str) -> None:
        """
        Write a single key=value pair to the .env file.
        Internal helper used by set_api_key and set_api_keys.

        If the key already exists, its value is replaced in-place.
        If it doesn't exist, it's appended to the file.

        Args:
            key_name: Environment variable name.
            value:    The value to store.
        """
        lines = []
        if os.path.exists(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        found = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key_name}="):
                new_lines.append(f"{key_name}={value}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key_name}={value}\n")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    # -- Persona Management ---------------------------------------------------

    def get_prompts_dir(self) -> str:
        """Return the absolute path to the prompts directory."""
        return os.path.join(self.project_dir, "prompts")

    def list_personas(self) -> list[dict]:
        """
        List all available persona files from the prompts/ directory.

        Returns:
            List of dicts with 'name', 'filename', and 'preview' for each .md file.
            The preview contains the first ~200 characters of the file content.
            Example: [{"name": "default", "filename": "default.md", "preview": "..."}, ...]
        """
        prompts_dir = self.get_prompts_dir()
        personas = []

        if not os.path.isdir(prompts_dir):
            return personas

        for filename in sorted(os.listdir(prompts_dir)):
            if filename.endswith(".md"):
                name = filename[:-3]  # Remove .md extension
                preview = ""
                filepath = os.path.join(prompts_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        preview = f.read(200)
                except OSError:
                    pass
                personas.append({
                    "name": name,
                    "filename": filename,
                    "preview": preview,
                })

        return personas


# -- Helper Functions ---------------------------------------------------------

def _deep_copy(d: dict) -> dict:
    """Create a deep copy of a nested dictionary."""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            result[key] = _deep_copy(value)
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """
    Recursively merge 'override' into 'base' (in-place).

    For nested dicts, values are merged recursively.
    For all other types, override replaces base.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _mask_key(value: str) -> str:
    """
    Mask an API key for safe display.

    Shows first 6 and last 4 characters, replaces the middle with '****'.
    Keys shorter than 12 characters are fully masked.

    Args:
        value: The raw API key string.

    Returns:
        The masked key string. Example: "sk-41****270b"
    """
    if not value or len(value) < 12:
        return "****" if value else ""
    return f"{value[:6]}****{value[-4:]}"
